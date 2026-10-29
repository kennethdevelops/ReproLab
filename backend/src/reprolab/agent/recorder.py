"""Run recording: steps, events and evidence. The DB implementation is the durable record;
the in-memory one lets agent logic be tested without a database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import func, select

from reprolab.artifacts.store import ArtifactStore
from reprolab.db.models import AgentStep, EvidenceAsset, Investigation, InvestigationEvent
from reprolab.db.session import session_scope
from reprolab.observability.redaction import redact_value


class Recorder(Protocol):
    investigation_id: uuid.UUID

    def step(
        self,
        node: str,
        tool: str | None,
        redacted_input: dict[str, Any],
        summary: str,
        ok: bool,
        time_ms: int,
        usage: dict[str, Any] | None = None,
    ) -> int: ...

    def event(self, type_: str, data: dict[str, Any]) -> int: ...

    def evidence(
        self, type_: str, label: str, ext: str, data: bytes, step_sequence: int | None
    ) -> uuid.UUID: ...

    def cancel_requested(self) -> bool: ...

    def set_status(self, status: str) -> None: ...


@dataclass
class MemoryRecorder:
    store: ArtifactStore
    investigation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    steps: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    cancel_flag: bool = False

    def step(self, node, tool, redacted_input, summary, ok, time_ms, usage=None):  # type: ignore[no-untyped-def]
        self.steps.append({"sequence": len(self.steps) + 1, "node": node, "tool": tool,
                           "input": redact_value(redacted_input), "summary": summary, "ok": ok})  # fmt: skip
        return len(self.steps)

    def event(self, type_, data):  # type: ignore[no-untyped-def]
        self.events.append({"sequence": len(self.events) + 1, "type": type_, "data": data})
        return len(self.events)

    def evidence(self, type_, label, ext, data, step_sequence):  # type: ignore[no-untyped-def]
        stored = self.store.put_bytes(self.investigation_id, ext, data)
        evidence_id = uuid.uuid4()
        self.evidence_items.append({"id": evidence_id, "type": type_, "label": label,
                                    "key": stored.storage_key, "step": step_sequence})  # fmt: skip
        return evidence_id

    def cancel_requested(self) -> bool:
        return self.cancel_flag

    def set_status(self, status: str) -> None:
        self.statuses.append(status)


class DbRecorder:
    """Each call commits immediately so progress survives worker crashes and is visible to SSE."""

    def __init__(self, investigation_id: uuid.UUID, store: ArtifactStore) -> None:
        self.investigation_id = investigation_id
        self.store = store
        with session_scope() as db:
            self._step_seq = (
                db.scalar(
                    select(func.coalesce(func.max(AgentStep.sequence), 0)).where(
                        AgentStep.investigation_id == investigation_id
                    )
                )
                or 0
            )

    def step(
        self,
        node: str,
        tool: str | None,
        redacted_input: dict[str, Any],
        summary: str,
        ok: bool,
        time_ms: int,
        usage: dict[str, Any] | None = None,
    ) -> int:
        self._step_seq += 1
        with session_scope() as db:
            db.add(
                AgentStep(
                    investigation_id=self.investigation_id,
                    sequence=self._step_seq,
                    node=node,
                    tool=tool,
                    redacted_input=redact_value(redacted_input),
                    output_summary=summary,
                    ok=ok,
                    time_ms=time_ms,
                    usage=usage or {},
                )
            )
        return self._step_seq

    def event(self, type_: str, data: dict[str, Any]) -> int:
        return append_event(self.investigation_id, type_, data)

    def evidence(
        self, type_: str, label: str, ext: str, data: bytes, step_sequence: int | None
    ) -> uuid.UUID:
        stored = self.store.put_bytes(self.investigation_id, ext, data)
        with session_scope() as db:
            asset = EvidenceAsset(
                investigation_id=self.investigation_id,
                type=type_,
                label=label,
                storage_key=stored.storage_key,
                mime_type=stored.mime_type,
                sha256=stored.sha256,
                size=stored.size,
                step_sequence=step_sequence,
            )
            db.add(asset)
            db.flush()
            asset_id = asset.id
        self.event(
            "evidence.created", {"evidence_id": str(asset_id), "type": type_, "label": label}
        )
        return asset_id

    def cancel_requested(self) -> bool:
        with session_scope() as db:
            return bool(
                db.scalar(
                    select(Investigation.cancel_requested).where(
                        Investigation.id == self.investigation_id
                    )
                )
            )

    def set_status(self, status: str) -> None:
        with session_scope() as db:
            inv = db.get(Investigation, self.investigation_id)
            if inv is not None and inv.status != status:
                inv.status = status


def append_event(investigation_id: uuid.UUID, type_: str, data: dict[str, Any]) -> int:
    """Append an ordered event. Sequence assigned under a row lock on the investigation."""
    with session_scope() as db:
        db.execute(
            select(Investigation.id).where(Investigation.id == investigation_id).with_for_update()
        )
        seq = (
            db.scalar(
                select(func.coalesce(func.max(InvestigationEvent.sequence), 0)).where(
                    InvestigationEvent.investigation_id == investigation_id
                )
            )
            or 0
        ) + 1
        db.add(
            InvestigationEvent(
                investigation_id=investigation_id, sequence=seq, type=type_, data=redact_value(data)
            )
        )
    return seq
