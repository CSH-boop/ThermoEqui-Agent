"""Behavioral tests for the DeepSeek provider at its public LLM interface."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.providers import DeepSeekProvider
from apps.api.main import configured_provider
from schemas.domain import Intent


@pytest.mark.asyncio
async def test_deepseek_provider_classifies_intent_through_chat_completions() -> None:
    captured: dict[str, object] = {}

    async def respond(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "MODEL_SELECTION_QA"}}]},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        transport=httpx.MockTransport(respond),
    )

    intent = await provider.classify_intent("NRTL 和 Peng-Robinson 有什么区别？")

    assert intent == Intent.MODEL_SELECTION_QA
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "deepseek-v4-flash",
        "messages": [
            {
                "role": "system",
                "content": "Return exactly one supported ThermoEqui intent enum value. Do not calculate numbers.",
            },
            {"role": "user", "content": "NRTL 和 Peng-Robinson 有什么区别？"},
        ],
        "stream": False,
        "thinking": {"type": "disabled"},
    }


def test_api_configuration_selects_deepseek_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")

    provider = configured_provider()

    assert isinstance(provider, DeepSeekProvider)
    assert provider.model == "deepseek-v4-pro"
    assert provider.base_url == "https://api.deepseek.com"


@pytest.mark.asyncio
async def test_deepseek_provider_requests_json_mode_for_task_manifests() -> None:
    captured_payload: dict[str, object] = {}
    manifest = {
        "equilibrium_type": "VLE",
        "calculation_type": "isobaric_vle",
        "components": [{"component_id": "benzene", "name": "Benzene"}],
        "conditions": {"pressure_kPa": 101.325},
    }

    async def respond(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(manifest)}}]},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    task = await provider.formulate_task("计算苯在常压下的汽液平衡")

    assert task is not None
    assert task.calculation_type == "isobaric_vle"
    assert captured_payload["response_format"] == {"type": "json_object"}
