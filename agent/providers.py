"""Isolated LLM provider interfaces and implementations."""

from __future__ import annotations

import json
from typing import Protocol

import httpx

from schemas.domain import EvidenceStatement, Intent, TaskManifest


class LLMProvider(Protocol):
    async def classify_intent(self, message: str) -> Intent: ...

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None: ...

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]: ...

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]: ...


class OpenAIProvider:
    """Optional provider using the official Responses API through a single adapter."""

    def __init__(self, api_key: str, model: str = "gpt-5-mini", timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def _request(self, instructions: str, message: str) -> str:
        payload = {"model": self.model, "instructions": instructions, "input": message}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        texts = [
            part.get("text", "")
            for output in body.get("output", [])
            for part in output.get("content", [])
            if part.get("type") == "output_text"
        ]
        return "".join(texts)

    async def classify_intent(self, message: str) -> Intent:
        value = await self._request(
            "Return exactly one supported ThermoEqui intent enum value. Do not calculate numbers.",
            message,
        )
        return Intent(value.strip())

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None:
        context = previous.model_dump_json() if previous else "null"
        value = await self._request(
            "Return only a TaskManifest JSON object or null. Never invent components or parameters. "
            f"Previous manifest: {context}",
            message,
        )
        return None if value.strip() == "null" else TaskManifest.model_validate_json(value)

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]:
        value = await self._request(
            "Answer concise thermodynamics knowledge questions without fabricating numerical data. "
            "Prefix every paragraph with Knowledge:, Inference:, or Warning:.",
            message,
        )
        return [EvidenceStatement(category="Knowledge", text=value)]

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]:
        value = await self._request(
            "Interpret only the supplied tool JSON. Preserve failures and warnings; do not add numbers.",
            json.dumps(result),
        )
        return [EvidenceStatement(category="Inference", text=value)]


class DeepSeekProvider:
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

    async def _request(self, instructions: str, message: str, *, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": message},
            ],
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("DeepSeek response did not contain assistant content") from error
        if not isinstance(content, str) or not content.strip():
            raise ValueError("DeepSeek response contained empty assistant content")
        return content

    async def classify_intent(self, message: str) -> Intent:
        value = await self._request(
            "Return exactly one supported ThermoEqui intent enum value. Do not calculate numbers.",
            message,
        )
        return Intent(value.strip())

    async def formulate_task(self, message: str, previous: TaskManifest | None = None) -> TaskManifest | None:
        context = previous.model_dump_json() if previous else "null"
        value = await self._request(
            "Return only a TaskManifest JSON object or null. Never invent components or parameters. "
            f"Previous manifest: {context}",
            message,
            json_mode=True,
        )
        return None if value.strip() == "null" else TaskManifest.model_validate_json(value)

    async def answer_with_evidence(self, message: str) -> list[EvidenceStatement]:
        value = await self._request(
            "Answer concise thermodynamics knowledge questions without fabricating numerical data. "
            "Prefix every paragraph with Knowledge:, Inference:, or Warning:.",
            message,
        )
        return [EvidenceStatement(category="Knowledge", text=value)]

    async def interpret_result(self, result: dict[str, object]) -> list[EvidenceStatement]:
        value = await self._request(
            "Interpret only the supplied tool JSON. Preserve failures and warnings; do not add numbers.",
            json.dumps(result),
        )
        return [EvidenceStatement(category="Inference", text=value)]
