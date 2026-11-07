"""Narrow model interface (spec §4 "LLM implementation rule").

The agent only needs: send system + messages + tools, get back tool calls, text and usage.
Providers (``LLM_PROVIDER``): ``anthropic`` (official SDK), ``openai_compatible`` (any
``/v1/chat/completions`` server: Ollama, LM Studio, OpenAI, Gemini, Groq, OpenRouter, ...) and
``replay`` (a recorded transcript, labelled as such in reports). ``StubModelClient`` replays
scripted turns for offline tests and never makes a network call.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import anthropic

from reprolab.config.settings import Settings

# USD per million tokens. Estimates for reporting only; provider invoices are authoritative.
PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
    "stub": {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_write": 0.0},
}


class ModelUnavailable(Exception):
    """Provider not configured or unreachable; the run ends as ``blocked``/``failed``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    def cost_usd(self, model: str) -> float | None:
        """Estimated USD, or ``None`` when the model has no known price ("not estimated")."""
        if model.startswith("replay:"):
            return 0.0
        price = PRICES_PER_MTOK.get(model)
        if price is None:
            return None
        return round(
            (
                self.input_tokens * price["input"]
                + self.output_tokens * price["output"]
                + self.cache_read_tokens * price["cache_read"]
                + self.cache_write_tokens * price["cache_write"]
            )
            / 1_000_000,
            6,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
        }


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelTurn:
    """One model response. ``assistant_content`` is replayed verbatim into the history."""

    assistant_content: list[Any]
    tool_calls: list[ToolCall]
    text: str
    stop_reason: str
    usage: Usage
    model: str
    request_id: str | None = None


class ModelClient(Protocol):
    model_id: str

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn: ...


class AnthropicModelClient:
    def __init__(self, settings: Settings) -> None:
        if settings.anthropic_api_key is None:
            raise ModelUnavailable("PROVIDER_NOT_CONFIGURED", "ANTHROPIC_API_KEY is not set.")
        self.model_id = settings.llm_model
        self._effort = settings.llm_effort
        self._max_tokens = settings.llm_max_tokens_per_call
        self._fallback = settings.llm_refusal_fallback
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=120.0, max_retries=2
        )

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn:
        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": list(messages),
            "tools": list(tools),
            "tool_choice": {"type": "auto"},
            "output_config": {"effort": self._effort},
            # Caches tools + system + history prefix; each loop turn re-reads it.
            "cache_control": {"type": "ephemeral"},
        }
        if self._fallback:
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        try:
            response = self._client.beta.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise ModelUnavailable(
                "PROVIDER_AUTH_FAILED", "Provider rejected the API key."
            ) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ModelUnavailable("PROVIDER_PERMISSION_DENIED", "Provider denied access.") from exc
        except anthropic.RateLimitError as exc:
            raise ModelUnavailable("PROVIDER_RATE_LIMITED", "Provider rate limit reached.") from exc
        except anthropic.BadRequestError as exc:
            raise ModelUnavailable(
                "PROVIDER_BAD_REQUEST", f"Provider rejected request: {exc.message}"
            ) from exc
        except anthropic.APIStatusError as exc:
            raise ModelUnavailable(
                "PROVIDER_ERROR", f"Provider error HTTP {exc.status_code}."
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ModelUnavailable("PROVIDER_UNREACHABLE", "Could not reach the provider.") from exc

        tool_calls: list[ToolCall] = []
        texts: list[str] = []
        for block in response.content:
            if block.type == "tool_use":
                raw = block.input if isinstance(block.input, dict) else json.loads(str(block.input))
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=raw))
            elif block.type == "text":
                texts.append(block.text)
        u = response.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        return ModelTurn(
            assistant_content=[b.model_dump(exclude_none=True) for b in response.content],
            tool_calls=tool_calls,
            text="\n".join(texts),
            stop_reason=response.stop_reason or "unknown",
            usage=usage,
            model=response.model,
            request_id=getattr(response, "_request_id", None),
        )


ScriptFn = Callable[[Sequence[dict[str, Any]]], list[tuple[str, dict[str, Any]]]]


@dataclass
class StubModelClient:
    """Deterministic scripted model. Each turn emits the next list of (tool_name, input) calls.

    ``script`` entries may also be callables receiving the message history, so a test can make
    decisions based on real tool results (e.g. quote text the browser actually returned).
    """

    script: list[list[tuple[str, dict[str, Any]]] | ScriptFn]
    model_id: str = "stub"
    calls: int = field(default=0, init=False)

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn:
        if self.calls >= len(self.script):
            return ModelTurn(
                [{"type": "text", "text": "(script exhausted)"}],
                [],
                "(script exhausted)",
                "end_turn",
                Usage(),
                self.model_id,
            )
        entry = self.script[self.calls]
        self.calls += 1
        planned = entry(messages) if callable(entry) else entry
        content: list[Any] = []
        calls: list[ToolCall] = []
        for i, (name, args) in enumerate(planned):
            call_id = f"stub_{self.calls}_{i}"
            content.append({"type": "tool_use", "id": call_id, "name": name, "input": args})
            calls.append(ToolCall(call_id, name, args))
        usage = Usage(input_tokens=100, output_tokens=20)
        return ModelTurn(
            content, calls, "", "tool_use" if calls else "end_turn", usage, self.model_id
        )


def load_prices_file(path: Path) -> None:
    """Merge an operator price table into ``PRICES_PER_MTOK`` (USD per million tokens)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelUnavailable(
            "PRICES_FILE_INVALID", f"Cannot read LLM_PRICES_FILE: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ModelUnavailable("PRICES_FILE_INVALID", "LLM_PRICES_FILE must be a JSON object.")
    for model, price in data.items():
        if not isinstance(price, dict) or not {"input", "output"} <= price.keys():
            raise ModelUnavailable(
                "PRICES_FILE_INVALID", f"Price for {model!r} needs 'input' and 'output'."
            )
        p: dict[str, Any] = price
        PRICES_PER_MTOK[str(model)] = {
            "input": float(p["input"]),
            "output": float(p["output"]),
            "cache_read": float(p.get("cache_read", p["input"])),
            "cache_write": float(p.get("cache_write", p["input"])),
        }


def build_model_client(settings: Settings) -> ModelClient:
    if settings.llm_prices_file is not None:
        load_prices_file(settings.llm_prices_file)
    client: ModelClient
    if settings.llm_provider == "anthropic":
        client = AnthropicModelClient(settings)
    elif settings.llm_provider == "openai_compatible":
        from reprolab.agent.openai_compatible import OpenAICompatibleModelClient

        client = OpenAICompatibleModelClient(settings)
    elif settings.llm_provider == "replay":
        from reprolab.agent.replay import ReplayModelClient

        if settings.llm_replay_path is None:
            raise ModelUnavailable("PROVIDER_NOT_CONFIGURED", "LLM_REPLAY_PATH is not set.")
        return ReplayModelClient.from_file(settings.llm_replay_path)
    else:
        client = _unsupported(settings)
    if settings.llm_record_path is not None:
        from reprolab.agent.replay import RecordingModelClient

        client = RecordingModelClient(client, settings.llm_record_path)
    return client


def _unsupported(settings: Settings) -> ModelClient:
    if settings.llm_provider == "stub" and not settings.is_public_demo:
        raise ModelUnavailable(
            "STUB_REQUIRES_SCRIPT", "The stub provider is only usable from tests with a script."
        )
    raise ModelUnavailable(
        "PROVIDER_NOT_SUPPORTED", f"Unknown LLM_PROVIDER {settings.llm_provider!r}."
    )
