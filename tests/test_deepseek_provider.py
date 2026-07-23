"""Behavioral tests for the DeepSeek provider at its public LLM interface."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import yaml

from agent.orchestrator import ConversationOrchestrator, DeterministicProvider
from agent.providers import DeepSeekProvider, LLMProviderError, LLMProviderOutputError
from apps.api.main import configured_provider
from schemas.domain import Intent, TaskManifest


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
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["messages"][1] == {  # type: ignore[index]
        "role": "user",
        "content": "NRTL 和 Peng-Robinson 有什么区别？",
    }
    system_prompt = payload["messages"][0]["content"]  # type: ignore[index]
    assert all(intent_value.value in system_prompt for intent_value in Intent)
    assert "Never return NONE" in system_prompt
    assert payload["stream"] is False
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 32


@pytest.mark.asyncio
async def test_deepseek_provider_normalizes_json_fenced_intent() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"intent":"MODEL_SELECTION_QA"}\n```',
                        }
                    }
                ]
            },
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    intent = await provider.classify_intent("NRTL 和 Peng-Robinson 有什么区别？")

    assert intent == Intent.MODEL_SELECTION_QA


def test_api_configuration_selects_deepseek_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")

    provider = configured_provider()

    assert isinstance(provider, DeepSeekProvider)
    assert provider.model == "deepseek-v4-pro"
    assert provider.base_url == "https://api.deepseek.com"


def test_api_configuration_without_deepseek_key_falls_back_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    provider = configured_provider()

    assert isinstance(provider, DeterministicProvider)


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
    messages = captured_payload["messages"]
    assert isinstance(messages, list)
    system_prompt = messages[0]["content"]
    assert '"calculation_type"' in system_prompt
    assert '"model_name"' in system_prompt
    assert "model_name may be null" in system_prompt
    assert "Never calculate equilibrium numbers" in system_prompt


@pytest.mark.asyncio
async def test_deepseek_provider_rejects_tool_outside_allowlist() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"tool_name":"python_shell"}'}}]},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )
    task = TaskManifest.model_validate(
        {
            "equilibrium_type": "VLE",
            "calculation_type": "isobaric_vle",
            "components": [{"component_id": "benzene", "name": "Benzene"}],
            "conditions": {"pressure_kPa": 101.325},
        }
    )

    with pytest.raises(LLMProviderOutputError):
        await provider.select_tool(
            "计算汽液平衡",
            task,
            [{"name": "phase_equilibrium", "description": "Deterministic phase equilibrium"}],
        )


@pytest.mark.asyncio
async def test_deepseek_provider_withholds_ungrounded_numbers_and_citations() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "预测汽化率为 .5，根据 NIST Chemistry WebBook。",
                        }
                    }
                ]
            },
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    statements = await provider.answer_with_evidence("解释苯和甲苯的汽液平衡")

    assert statements[0].category == "Warning"
    assert ".5" not in statements[0].text
    assert "NIST" not in statements[0].text


@pytest.mark.asyncio
async def test_deepseek_provider_rejects_malformed_response_schema() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"unexpected": "shape"}]})

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(LLMProviderOutputError):
        await provider.classify_intent("解释 NRTL")


@pytest.mark.asyncio
async def test_deepseek_provider_rejects_empty_assistant_content() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "   "}}]},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(LLMProviderOutputError):
        await provider.classify_intent("解释 NRTL")


@pytest.mark.asyncio
async def test_deepseek_provider_sanitizes_remote_api_errors() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "server-secret-detail"}},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    with pytest.raises(LLMProviderError) as captured:
        await provider.classify_intent("解释 NRTL")

    assert captured.value.provider == "DeepSeek"
    assert captured.value.status_code == 401
    assert "test-key" not in str(captured.value)
    assert "server-secret-detail" not in str(captured.value)


def test_compose_forwards_deepseek_configuration_to_api() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["api"]["environment"]

    assert environment["DEEPSEEK_API_KEY"] == "${DEEPSEEK_API_KEY:-}"
    assert environment["DEEPSEEK_MODEL"] == "${DEEPSEEK_MODEL:-deepseek-v4-flash}"
    assert environment["DEEPSEEK_BASE_URL"] == "${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"


@pytest.mark.asyncio
async def test_deepseek_orchestration_uses_real_engine_and_receives_validated_result() -> None:
    task_payload = {
        "equilibrium_type": "VLE",
        "calculation_type": "isobaric_vle",
        "components": [
            {"component_id": "benzene", "name": "Benzene", "cas_number": "71-43-2"},
            {"component_id": "toluene", "name": "Toluene", "cas_number": "108-88-3"},
        ],
        "conditions": {"pressure_kPa": 101.325},
        "model_name": "Ideal/Raoult",
    }
    responses = [
        "EQUILIBRIUM_CALCULATION",
        json.dumps(task_payload),
        json.dumps({"tool_name": "phase_equilibrium"}),
        "计算结果已通过确定性验证。",
    ]
    requests: list[dict[str, object]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": responses[len(requests) - 1]}}]},
        )

    provider = DeepSeekProvider(
        api_key="test-key",
        transport=httpx.MockTransport(respond),
    )

    response = await ConversationOrchestrator(provider).chat("计算苯-甲苯在101.325 kPa下的T-x-y曲线")

    assert response.calculation is not None
    assert len(response.calculation.result.points) == 21
    assert response.calculation.validation.overall_status in {"passed", "warning"}
    tool_selection_input = json.loads(requests[2]["messages"][1]["content"])  # type: ignore[index]
    assert tool_selection_input["available_tools"][0]["name"] == "phase_equilibrium"
    interpretation_input = json.loads(requests[3]["messages"][1]["content"])  # type: ignore[index]
    assert len(interpretation_input["result"]["points"]) == 21
    assert interpretation_input["validation"]["overall_status"] in {"passed", "warning"}
