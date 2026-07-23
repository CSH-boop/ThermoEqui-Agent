"""Isolated LLM provider interfaces and implementations."""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from schemas.domain import EvidenceStatement, Intent, TaskManifest


class LLMProvider(Protocol):
    async def classify_intent(self, message: str) -> Intent: ...

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None: ...

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]: ...

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]: ...


class LLMProviderError(RuntimeError):
    """Sanitized external-provider failure safe for API responses and logs."""

    def __init__(self, provider: str, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        detail = f" with status {status_code}" if status_code is not None else ""
        super().__init__(f"{provider} API request failed{detail}.")


_NUMERIC_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
_EXTERNAL_REFERENCE = re.compile(r"https?://|doi\s*:|10\.\d{4,9}/", re.IGNORECASE)
_WITHHELD_TEXT = "外部模型输出因包含未经确定性工具证实的数值或引用而被扣留。"


class _DeepSeekMessage(BaseModel):
    content: str


class _DeepSeekChoice(BaseModel):
    message: _DeepSeekMessage


class _DeepSeekChatCompletion(BaseModel):
    choices: list[_DeepSeekChoice] = Field(min_length=1)


def _contains_ungrounded_claim(text: str, grounded_source: str | None = None) -> bool:
    if _EXTERNAL_REFERENCE.search(text):
        return True
    allowed_numbers = set(_NUMERIC_TOKEN.findall(grounded_source or ""))
    return any(token not in allowed_numbers for token in _NUMERIC_TOKEN.findall(text))


class ConstrainedLLMProvider:
    """Shared orchestration behavior; subclasses implement only their HTTP transport."""

    async def _request(
        self,
        instructions: str,
        message: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 1024,
    ) -> str:
        raise NotImplementedError

    async def classify_intent(self, message: str) -> Intent:
        value = await self._request(
            "Return exactly one supported ThermoEqui intent enum value. Do not calculate numbers.",
            message,
            max_tokens=32,
        )
        return Intent(value.strip())

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None:
        context = previous.model_dump_json() if previous else "null"
        value = await self._request(
            "Return only a TaskManifest JSON object or null. Never invent components or parameters. "
            f"Previous manifest: {context}",
            message,
            json_mode=True,
            max_tokens=2048,
        )
        return None if value.strip() == "null" else TaskManifest.model_validate_json(value)

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]:
        value = await self._request(
            "Answer concise thermodynamics knowledge questions without fabricating numerical data or citations. "
            "Do not cite any source. Prefix every paragraph with Knowledge:, Inference:, or Warning:.",
            message,
        )
        if _contains_ungrounded_claim(value):
            return [EvidenceStatement(category="Warning", text=_WITHHELD_TEXT)]
        return [EvidenceStatement(category="Knowledge", text=value)]

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]:
        grounded_source = json.dumps(result, ensure_ascii=False)
        value = await self._request(
            "Interpret only the supplied tool JSON. Preserve failures and warnings; do not add numbers or citations.",
            grounded_source,
        )
        if _contains_ungrounded_claim(value, grounded_source):
            return [EvidenceStatement(category="Warning", text=_WITHHELD_TEXT)]
        return [EvidenceStatement(category="Inference", text=value)]


class OpenAIProvider(ConstrainedLLMProvider):
    """Optional provider using the official Responses API through a single adapter."""

    def __init__(self, api_key: str, model: str = "gpt-5-mini", timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def _request(
        self,
        instructions: str,
        message: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": message,
            "max_output_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise LLMProviderError("OpenAI", error.response.status_code) from None
            except httpx.RequestError:
                raise LLMProviderError("OpenAI") from None
            body = response.json()
        texts = [
            part.get("text", "")
            for output in body.get("output", [])
            for part in output.get("content", [])
            if part.get("type") == "output_text"
        ]
        return "".join(texts)


class DeepSeekProvider(ConstrainedLLMProvider):
    """DeepSeek Chat Completions adapter with the same constrained LLM role."""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def _request(
        self,
        instructions: str,
        message: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": message},
            ],
            "stream": False,
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            try:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise LLMProviderError("DeepSeek", error.response.status_code) from None
            except httpx.RequestError:
                raise LLMProviderError("DeepSeek") from None
            completion = _DeepSeekChatCompletion.model_validate(response.json())
        content = completion.choices[0].message.content
        if not content.strip():
            raise ValueError("DeepSeek response contained empty assistant content")
        return content
