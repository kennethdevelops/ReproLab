"""``ModelClient`` for any OpenAI-compatible ``/v1/chat/completions`` endpoint.

Works with Ollama, LM Studio, vLLM, llama.cpp server, OpenAI, Gemini (OpenAI endpoint), Groq,
OpenRouter and similar. The agent keeps its history in Anthropic content-block form; this module
translates that history to chat-completions messages on each call and translates the response
back, so the rest of the agent is provider-neutral.

Uses ``httpx`` directly: no extra SDK dependency, and the request body stays visible here.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from reprolab.agent.model_client import ModelTurn, ModelUnavailable, ToolCall, Usage
from reprolab.config.settings import Settings

_PROBE_TOOL = {
    "name": "report_ready",
    "description": "Call this tool to confirm you can use tools.",
    "input_schema": {
        "type": "object",
        "properties": {"ready": {"type": "boolean"}},
        "required": ["ready"],
        "additionalProperties": False,
    },
}


def to_openai_tools(tools: Sequence[dict[str, Any]], strict: bool) -> list[dict[str, Any]]:
    out = []
    for t in tools:
        fn: dict[str, Any] = {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t["input_schema"],
        }
        if strict:
            fn["strict"] = True
        out.append({"type": "function", "function": fn})
    return out


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def to_openai_messages(system: str, messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate Anthropic-style history (text/tool_use/tool_result blocks) to chat messages."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        content = msg["content"]
        if msg["role"] == "assistant":
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {"role": "assistant", "content": _text_of(blocks) or None}
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue
        if isinstance(content, str):
            out.append({"role": "user", "content": content})
            continue
        texts = []
        for block in content:
            if block.get("type") == "tool_result":
                body = block.get("content", "")
                text = body if isinstance(body, str) else _text_of(body)
                if block.get("is_error"):
                    text = f"ERROR: {text}"
                out.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": text})
            elif block.get("type") == "text":
                texts.append(str(block.get("text", "")))
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        # Invalid JSON goes to server-side validation, which reports it to the model as an error.
        return {"__invalid_json__": str(raw)[:2000]}
    return value if isinstance(value, dict) else {"__invalid_json__": str(raw)[:2000]}


_STOP_MAP = {"tool_calls": "tool_use", "function_call": "tool_use", "stop": "end_turn",
             "length": "max_tokens", "content_filter": "refusal"}  # fmt: skip


def parse_response(body: dict[str, Any], fallback_model: str) -> ModelTurn:
    choices = body.get("choices") or []
    if not choices:
        raise ModelUnavailable("PROVIDER_BAD_RESPONSE", "Provider response has no choices.")
    choice = choices[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = raw.get("function") or {}
        call_id = raw.get("id") or f"call_{uuid.uuid4().hex[:12]}"
        args = _parse_arguments(fn.get("arguments"))
        calls.append(ToolCall(call_id, str(fn.get("name", "")), args))
        content.append(
            {"type": "tool_use", "id": call_id, "name": fn.get("name", ""), "input": args}
        )
    if message.get("refusal"):
        content.append({"type": "text", "text": str(message["refusal"])})
        stop = "refusal"
    else:
        stop = _STOP_MAP.get(str(choice.get("finish_reason")), "end_turn")
        if calls:
            stop = "tool_use"
    u = body.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    usage = Usage(
        input_tokens=max(int(u.get("prompt_tokens") or 0) - int(cached), 0),
        output_tokens=int(u.get("completion_tokens") or 0),
        cache_read_tokens=int(cached),
    )
    return ModelTurn(
        assistant_content=content,
        tool_calls=calls,
        text=text,
        stop_reason=stop,
        usage=usage,
        model=str(body.get("model") or fallback_model),
        request_id=body.get("id"),
    )


class OpenAICompatibleModelClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        if not settings.llm_base_url:
            raise ModelUnavailable("PROVIDER_NOT_CONFIGURED", "LLM_BASE_URL is not set.")
        if not settings.llm_model:
            raise ModelUnavailable("PROVIDER_NOT_CONFIGURED", "LLM_MODEL is not set.")
        self.model_id = settings.llm_model
        self._max_tokens = settings.llm_max_tokens_per_call
        self._strict = settings.llm_strict_tools
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key is not None:
            headers["Authorization"] = f"Bearer {settings.llm_api_key.get_secret_value()}"
        self._http = httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers=headers,
            timeout=settings.llm_timeout_seconds,
            transport=transport,
        )

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": to_openai_messages(system, messages),
            "max_tokens": self._max_tokens,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = to_openai_tools(tools, self._strict)
            payload["tool_choice"] = "auto"
        try:
            response = self._http.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise ModelUnavailable("PROVIDER_TIMEOUT", "Provider did not answer in time.") from exc
        except httpx.HTTPError as exc:
            raise ModelUnavailable("PROVIDER_UNREACHABLE", "Could not reach the provider.") from exc
        status = response.status_code
        if status == 401:
            raise ModelUnavailable("PROVIDER_AUTH_FAILED", "Provider rejected the API key.")
        if status == 403:
            raise ModelUnavailable("PROVIDER_PERMISSION_DENIED", "Provider denied access.")
        if status == 404:
            raise ModelUnavailable(
                "PROVIDER_MODEL_NOT_FOUND", f"Model {self.model_id!r} or endpoint not found."
            )
        if status == 429:
            raise ModelUnavailable("PROVIDER_RATE_LIMITED", "Provider rate limit reached.")
        if 400 <= status < 500:
            raise ModelUnavailable(
                "PROVIDER_BAD_REQUEST", f"Provider rejected request: {response.text[:300]}"
            )
        if status >= 400:
            raise ModelUnavailable(
                "PROVIDER_ERROR", f"Provider error HTTP {status}: {response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ModelUnavailable("PROVIDER_BAD_RESPONSE", "Provider returned non-JSON.") from exc
        return parse_response(body, self.model_id)


def check_tool_support(client: Any) -> tuple[bool, str]:
    """Ask the model to call one probe tool. Returns (supported, detail)."""
    try:
        turn = client.complete(
            "You are a connectivity check. Always answer by calling the provided tool.",
            [{"role": "user", "content": "Call report_ready with ready=true."}],
            [_PROBE_TOOL],
        )
    except ModelUnavailable as exc:
        return False, f"{exc.code}: {exc}"
    if any(c.name == "report_ready" for c in turn.tool_calls):
        return True, f"{turn.model} returned a tool call."
    return False, f"{turn.model} answered without a tool call (stop_reason={turn.stop_reason})."
