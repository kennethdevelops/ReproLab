"""Provider-neutral model layer: OpenAI-compatible translation, replay, recording, prices."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from reprolab.agent import model_client as mc
from reprolab.agent import openai_compatible as oc
from reprolab.agent.model_client import ModelUnavailable, StubModelClient, Usage, build_model_client
from reprolab.agent.openai_compatible import (
    OpenAICompatibleModelClient,
    check_tool_support,
    parse_response,
    to_openai_messages,
    to_openai_tools,
)
from reprolab.agent.replay import RecordingModelClient, ReplayModelClient
from reprolab.agent.tool_specs import all_tools
from reprolab.config.settings import Settings


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


HISTORY: list[dict[str, Any]] = [
    {"role": "user", "content": "Investigate."},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Opening."},
        {"type": "tool_use", "id": "c1", "name": "open_page", "input": {"path": "/shop"}},
    ]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok"}]},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "c2", "name": "go_back", "input": {}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c2", "content": "blocked", "is_error": True},
    ]},
]  # fmt: skip


def test_history_translates_to_chat_messages() -> None:
    out = to_openai_messages("SYS", HISTORY)
    assert out[0] == {"role": "system", "content": "SYS"}
    assert out[1] == {"role": "user", "content": "Investigate."}
    assert out[2]["content"] == "Opening."
    assert out[2]["tool_calls"][0]["function"] == {
        "name": "open_page",
        "arguments": '{"path": "/shop"}',
    }
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}
    assert out[4]["content"] is None
    assert out[5]["content"] == "ERROR: blocked"


def test_tools_translate_and_strict_is_opt_in() -> None:
    tools = to_openai_tools(all_tools(), strict=False)
    assert all(t["type"] == "function" and "strict" not in t["function"] for t in tools)
    assert tools[0]["function"]["parameters"]["additionalProperties"] is False
    assert all(t["function"]["strict"] for t in to_openai_tools(all_tools(), strict=True))


def _client(handler: Any, **kw: Any) -> OpenAICompatibleModelClient:
    s = _settings(llm_provider="openai_compatible", llm_base_url="http://llm.test/v1",
                  llm_model="qwen3:8b", **kw)  # fmt: skip
    return OpenAICompatibleModelClient(s, transport=httpx.MockTransport(handler))


def test_complete_parses_tool_calls_and_usage() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "req-1", "model": "qwen3:8b",
            "choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
                {"id": "t1", "type": "function",
                 "function": {"name": "open_page", "arguments": '{"path": "/cart"}'}},
                {"id": "t2", "type": "function", "function": {"name": "click", "arguments": "{bad"}},
            ]}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30,
                      "prompt_tokens_details": {"cached_tokens": 20}},
        })  # fmt: skip

    turn = _client(handler, llm_api_key="sk-x").complete("SYS", HISTORY, all_tools())
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-x"
    assert seen["body"]["tool_choice"] == "auto"
    assert seen["body"]["model"] == "qwen3:8b"
    assert [c.name for c in turn.tool_calls] == ["open_page", "click"]
    assert turn.tool_calls[0].input == {"path": "/cart"}
    assert "__invalid_json__" in turn.tool_calls[1].input
    assert turn.stop_reason == "tool_use"
    assert turn.request_id == "req-1"
    u = turn.usage
    assert (u.input_tokens, u.cache_read_tokens, u.output_tokens) == (100, 20, 30)
    # The returned assistant content round-trips through the translator.
    again = to_openai_messages("S", [{"role": "assistant", "content": turn.assistant_content}])
    assert again[1]["tool_calls"][0]["id"] == "t1"


def test_no_api_key_sends_no_auth_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "stop", "message": {"content": "hi"}}]}
        )

    turn = _client(handler).complete("S", [{"role": "user", "content": "x"}], [])
    assert turn.stop_reason == "end_turn"
    assert turn.text == "hi"
    assert turn.model == "qwen3:8b"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "PROVIDER_AUTH_FAILED"),
        (404, "PROVIDER_MODEL_NOT_FOUND"),
        (429, "PROVIDER_RATE_LIMITED"),
        (400, "PROVIDER_BAD_REQUEST"),
        (500, "PROVIDER_ERROR"),
    ],
)
def test_http_errors_map_to_model_unavailable(status: int, code: str) -> None:
    client = _client(lambda r: httpx.Response(status, text="nope"))
    with pytest.raises(ModelUnavailable) as exc:
        client.complete("S", [{"role": "user", "content": "x"}], [])
    assert exc.value.code == code


def test_unreachable_server() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ModelUnavailable) as exc:
        _client(handler).complete("S", [{"role": "user", "content": "x"}], [])
    assert exc.value.code == "PROVIDER_UNREACHABLE"


def test_tool_support_check() -> None:
    assert check_tool_support(StubModelClient([[("report_ready", {"ready": True})]]))[0]
    ok, detail = check_tool_support(StubModelClient([[]]))
    assert not ok
    assert "without a tool call" in detail


def test_factory_requires_base_url_and_rejects_unknown() -> None:
    with pytest.raises(ModelUnavailable, match="LLM_BASE_URL"):
        build_model_client(_settings(llm_provider="openai_compatible"))
    with pytest.raises(ModelUnavailable) as exc:
        build_model_client(_settings(llm_provider="nope"))
    assert exc.value.code == "PROVIDER_NOT_SUPPORTED"
    assert not _settings(llm_provider="openai_compatible").llm_configured
    assert _settings(llm_provider="openai_compatible", llm_base_url="http://x/v1").llm_configured


def test_record_then_replay(tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    live = StubModelClient(
        [[("open_page", {"path": "/shop"})], [("go_back", {})]], model_id="qwen3:8b"
    )
    rec = RecordingModelClient(live, path)
    first = [rec.complete("S", [], []), rec.complete("S", [], [])]

    replay = build_model_client(_settings(llm_provider="replay", llm_replay_path=path))
    assert isinstance(replay, ReplayModelClient)
    assert replay.model_id == "replay:qwen3:8b"
    again = [replay.complete("S", [], []) for _ in range(3)]
    assert [t.tool_calls[0].input for t in again[:2]] == [t.tool_calls[0].input for t in first]
    assert again[2].tool_calls == []
    assert "exhausted" in again[2].text
    assert Usage(input_tokens=10**6).cost_usd(replay.model_id) == 0.0


def test_replay_rejects_bad_transcript(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "other"}', encoding="utf-8")
    with pytest.raises(ModelUnavailable) as exc:
        ReplayModelClient.from_file(bad)
    assert exc.value.code == "REPLAY_INVALID"


def test_prices_file_extends_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc, "PRICES_PER_MTOK", dict(mc.PRICES_PER_MTOK))
    assert Usage(input_tokens=10**6).cost_usd("gpt-x") is None  # unknown model: not estimated
    prices = tmp_path / "p.json"
    prices.write_text(json.dumps({"gpt-x": {"input": 1.5, "output": 6}}), encoding="utf-8")
    mc.load_prices_file(prices)
    assert Usage(input_tokens=10**6, output_tokens=10**6).cost_usd("gpt-x") == pytest.approx(7.5)
    prices.write_text(json.dumps({"gpt-y": {"input": 1}}), encoding="utf-8")
    with pytest.raises(ModelUnavailable):
        mc.load_prices_file(prices)


def test_blank_env_values_mean_unset() -> None:
    s = _settings(llm_prices_file="", llm_record_path=" ", llm_api_key="", test_runner_url="")
    assert s.llm_prices_file is None and s.llm_record_path is None
    assert s.llm_api_key is None and s.test_runner_url is None


def test_gemini_thought_signature_round_trips() -> None:
    extra = {"google": {"thought_signature": "sig-abc"}}
    body = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c9", "type": "function", "extra_content": extra,
         "function": {"name": "open_page", "arguments": '{"path": "/"}'}},
    ]}}]}  # fmt: skip
    turn = parse_response(body, "gemini")
    history = [{"role": "user", "content": "Go."},
               {"role": "assistant", "content": turn.assistant_content}]  # fmt: skip
    sent = to_openai_messages("SYS", history)[2]["tool_calls"][0]
    assert sent["extra_content"] == extra
    plain = to_openai_messages("SYS", HISTORY)[2]["tool_calls"][0]
    assert "extra_content" not in plain


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(oc, "_sleep", slept.append)
    return slept


def test_transient_errors_are_retried_then_succeed(_no_retry_sleep: list[float]) -> None:
    answers = [httpx.Response(503, text="busy"), httpx.Response(429, headers={"retry-after": "2"}),
               httpx.Response(200, json={"choices": [{"message": {"content": "hi"},
                                                      "finish_reason": "stop"}]})]  # fmt: skip
    client = _client(lambda r: answers.pop(0))
    turn = client.complete("S", [{"role": "user", "content": "x"}], [])
    assert turn.text == "hi"
    assert _no_retry_sleep == [5.0, 2.0]


def test_retries_are_bounded(_no_retry_sleep: list[float]) -> None:
    calls = []
    client = _client(lambda r: calls.append(1) or httpx.Response(503, text="busy"))
    with pytest.raises(ModelUnavailable) as exc:
        client.complete("S", [{"role": "user", "content": "x"}], [])
    assert exc.value.code == "PROVIDER_ERROR"
    assert len(calls) == 4


def test_client_errors_are_not_retried() -> None:
    calls = []
    client = _client(lambda r: calls.append(1) or httpx.Response(400, text="bad"))
    with pytest.raises(ModelUnavailable):
        client.complete("S", [{"role": "user", "content": "x"}], [])
    assert len(calls) == 1


def _tool_use_failed() -> httpx.Response:
    return httpx.Response(400, json={"error": {"code": "tool_use_failed", "message": "bad tool"}})


def test_invalid_tool_call_is_corrected_and_retried() -> None:
    seen: list[dict[str, Any]] = []
    answers = [_tool_use_failed(), httpx.Response(200, json={
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})]  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return answers.pop(0)

    turn = _client(handler).complete("S", [{"role": "user", "content": "x"}], [])
    assert turn.text == "ok"
    assert len(seen) == 2
    assert "does not exist" in seen[1]["messages"][-1]["content"]


def test_invalid_tool_call_fixes_are_bounded() -> None:
    calls = []
    client = _client(lambda r: calls.append(1) or _tool_use_failed())
    with pytest.raises(ModelUnavailable) as exc:
        client.complete("S", [{"role": "user", "content": "x"}], [])
    assert exc.value.code == "PROVIDER_BAD_REQUEST"
    assert len(calls) == 3
