"""Record live model turns and replay them later.

A replay run is a labelled re-execution: the browser, verification and report are real, but the
model's decisions come from a transcript recorded during an earlier live run. Its ``model_id`` is
``replay:<recorded model>`` and reports state that it is a replay. Replay never claims to measure
model quality.

Transcript format (JSON)::

    {"format": "reprolab-model-transcript/v1", "model": "qwen3:8b", "recorded_at": "...",
     "turns": [{"assistant_content": [...], "stop_reason": "tool_use", "usage": {...}}]}
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reprolab.agent.model_client import ModelClient, ModelTurn, ModelUnavailable, ToolCall, Usage

FORMAT = "reprolab-model-transcript/v1"


def _turn_from_record(record: dict[str, Any], model_id: str) -> ModelTurn:
    content = list(record.get("assistant_content") or [])
    calls = [
        ToolCall(str(b["id"]), str(b["name"]), dict(b.get("input") or {}))
        for b in content
        if b.get("type") == "tool_use"
    ]
    text = "\n".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
    u = record.get("usage") or {}
    usage = Usage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_tokens=int(u.get("cache_read_tokens", 0)),
        cache_write_tokens=int(u.get("cache_write_tokens", 0)),
    )
    stop = str(record.get("stop_reason") or ("tool_use" if calls else "end_turn"))
    return ModelTurn(content, calls, text, stop, usage, model_id, None)


@dataclass
class ReplayModelClient:
    turns: list[dict[str, Any]]
    recorded_model: str
    model_id: str = field(init=False)
    calls: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.model_id = f"replay:{self.recorded_model}"

    @classmethod
    def from_file(cls, path: Path) -> ReplayModelClient:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelUnavailable(
                "REPLAY_INVALID", f"Cannot read replay transcript: {exc}"
            ) from exc
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ModelUnavailable("REPLAY_INVALID", f"Transcript format must be {FORMAT!r}.")
        turns = data.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ModelUnavailable("REPLAY_INVALID", "Transcript has no turns.")
        return cls(turns, str(data.get("model") or "unknown"))

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn:
        if self.calls >= len(self.turns):
            text = "(replay transcript exhausted)"
            return ModelTurn([{"type": "text", "text": text}], [], text, "end_turn", Usage(),
                             self.model_id)  # fmt: skip
        record = self.turns[self.calls]
        self.calls += 1
        return _turn_from_record(record, self.model_id)


class RecordingModelClient:
    """Wraps a live client and appends each turn to a transcript file after every call."""

    def __init__(self, inner: ModelClient, path: Path) -> None:
        self._inner = inner
        self._path = path
        self.model_id = inner.model_id
        self._data: dict[str, Any] = {
            "format": FORMAT,
            "model": inner.model_id,
            "recorded_at": datetime.now(UTC).isoformat(),
            "turns": [],
        }

    def complete(
        self, system: str, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelTurn:
        turn = self._inner.complete(system, messages, tools)
        self._data["model"] = turn.model or self.model_id
        self._data["turns"].append(
            {
                "assistant_content": turn.assistant_content,
                "stop_reason": turn.stop_reason,
                "usage": turn.usage.as_dict(),
            }
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        return turn
