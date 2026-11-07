from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reprolab.api.deps import DbSession
from reprolab.api.errors import ApiError
from reprolab.artifacts.store import ArtifactStore
from reprolab.config.settings import Settings, get_settings
from reprolab.db.enums import TERMINAL_INVESTIGATION_STATUSES, InvestigationStatus
from reprolab.db.models import (
    AgentStep,
    EvidenceAsset,
    Finding,
    Investigation,
    InvestigationEvent,
    Project,
)
from reprolab.db.session import session_scope
from reprolab.reports.report import render_markdown
from reprolab.retrieval.search import current_snapshot

router = APIRouter(tags=["investigations"])

ACTIVE_STATUSES = [s.value for s in InvestigationStatus if not s.is_terminal]


class Viewport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(ge=320, le=2560)
    height: int = Field(ge=320, le=1600)


class StartInvestigation(BaseModel):
    """Callers cannot set policy fields (origins, limits, prompts, model); those are server-side."""

    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID
    bug_report: str = Field(min_length=10)
    start_path: str = Field(default="/", max_length=300)
    rag_mode: Literal["none", "lexical", "vector", "hybrid"] = "none"
    viewport: Viewport | None = None

    @field_validator("start_path")
    @classmethod
    def _relative_path(cls, v: str) -> str:
        if not v.startswith("/") or v.startswith("//") or "://" in v or "\\" in v:
            raise ValueError("start_path must be a path on the project's test origin, e.g. /shop")
        if any(ord(c) < 32 for c in v):
            raise ValueError("control characters are not allowed")
        return v


class StartAccepted(BaseModel):
    investigation_id: uuid.UUID
    status: str
    events_path: str


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    snapshot_id: uuid.UUID | None
    bug_report: str
    start_path: str
    viewport: dict[str, Any]
    status: str
    status_reason: str | None
    rag_mode: str
    model_id: str
    limits: dict[str, Any]
    usage: dict[str, Any]
    result: dict[str, Any] | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence: int
    node: str
    tool: str | None
    redacted_input: dict[str, Any]
    output_summary: str | None
    ok: bool
    time_ms: int
    usage: dict[str, Any]
    created_at: datetime


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    label: str
    mime_type: str
    sha256: str
    size: int
    step_sequence: int | None
    created_at: datetime


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    statement: str
    verification_status: str
    citations: list[Any]


class InvestigationDetail(InvestigationOut):
    steps: list[StepOut]
    evidence: list[EvidenceOut]
    findings: list[FindingOut]


Enqueue = Callable[[uuid.UUID], None]


def _celery_enqueue(investigation_id: uuid.UUID) -> None:
    from reprolab.workers.tasks import run_investigation

    run_investigation.delay(str(investigation_id))


# Indirection so tests can run jobs inline without a broker.
enqueue_investigation: list[Enqueue] = [_celery_enqueue]


def _limits(settings: Settings) -> dict[str, Any]:
    return {
        "max_browser_steps": settings.max_browser_steps,
        "max_model_calls": settings.max_model_calls,
        "max_seconds": settings.max_investigation_seconds,
        "max_input_tokens": settings.max_input_tokens_per_run,
        "max_output_tokens": settings.max_output_tokens_per_run,
        "max_cost_usd": settings.max_run_cost_usd,
        "max_retrieval_calls": settings.max_retrieval_calls,
    }


@router.post("/investigations", status_code=202, response_model=StartAccepted)
def start_investigation(body: StartInvestigation, request: Request, db: DbSession) -> StartAccepted:
    settings = get_settings()
    if len(body.bug_report) > settings.max_bug_report_chars:
        raise ApiError(
            422,
            "BUG_REPORT_TOO_LONG",
            f"Bug report exceeds {settings.max_bug_report_chars} characters.",
        )
    project = db.get(Project, body.project_id)
    if project is None or (settings.is_public_demo and project.mode != "demo"):
        raise ApiError(404, "PROJECT_NOT_FOUND", "Project not found.")
    snapshot_id = None
    if body.rag_mode != "none":
        snapshot = current_snapshot(db, project.id)
        if snapshot is None:
            raise ApiError(
                422,
                "RAG_INDEX_MISSING",
                "This project has no ready repository index. Index it first or use rag_mode 'none'.",
            )
        snapshot_id = snapshot.id
    active = db.scalar(
        select(func.count())
        .select_from(Investigation)
        .where(Investigation.status.in_(ACTIVE_STATUSES))
    )
    if (active or 0) >= settings.max_queued_investigations:
        raise ApiError(
            429, "QUEUE_FULL", "Too many investigations are queued or running. Try again later."
        )

    inv = Investigation(
        project_id=project.id,
        snapshot_id=snapshot_id,
        bug_report=body.bug_report,
        start_path=body.start_path,
        viewport=body.viewport.model_dump() if body.viewport else {"width": 1365, "height": 768},
        status=InvestigationStatus.QUEUED.value,
        rag_mode=body.rag_mode,
        model_id=settings.llm_model,
        limits=_limits(settings),
        client_key=request.client.host if request.client else None,
    )
    db.add(inv)
    db.flush()
    db.add(
        InvestigationEvent(
            investigation_id=inv.id, sequence=1, type="investigation.queued", data={}
        )
    )
    db.commit()  # persist before enqueueing so the worker always finds the row
    try:
        enqueue_investigation[0](inv.id)
    except Exception as exc:
        inv.status = InvestigationStatus.FAILED.value
        inv.status_reason = "Job broker unavailable; the investigation was not started."
        db.commit()
        raise ApiError(503, "BROKER_UNAVAILABLE", "The job queue is unavailable.") from exc
    return StartAccepted(
        investigation_id=inv.id,
        status=inv.status,
        events_path=f"/api/v1/investigations/{inv.id}/events",
    )


def _get(db: Session, investigation_id: uuid.UUID) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise ApiError(404, "INVESTIGATION_NOT_FOUND", "Investigation not found.")
    if get_settings().is_public_demo:
        project = db.get(Project, inv.project_id)
        if project is None or project.mode != "demo":
            raise ApiError(404, "INVESTIGATION_NOT_FOUND", "Investigation not found.")
    return inv


@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(
    db: DbSession, project_id: uuid.UUID | None = None, limit: int = Query(default=20, ge=1, le=100)
) -> list[InvestigationOut]:
    query = select(Investigation).order_by(Investigation.created_at.desc()).limit(limit)
    if project_id:
        query = query.where(Investigation.project_id == project_id)
    return [InvestigationOut.model_validate(i) for i in db.scalars(query)]


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetail)
def read_investigation(investigation_id: uuid.UUID, db: DbSession) -> InvestigationDetail:
    inv = _get(db, investigation_id)
    steps = db.scalars(
        select(AgentStep).where(AgentStep.investigation_id == inv.id).order_by(AgentStep.sequence)
    )
    evidence = db.scalars(
        select(EvidenceAsset)
        .where(EvidenceAsset.investigation_id == inv.id)
        .order_by(EvidenceAsset.created_at)
    )
    findings = db.scalars(
        select(Finding).where(Finding.investigation_id == inv.id).order_by(Finding.created_at)
    )
    return InvestigationDetail(
        **InvestigationOut.model_validate(inv).model_dump(),
        steps=[StepOut.model_validate(s) for s in steps],
        evidence=[EvidenceOut.model_validate(e) for e in evidence],
        findings=[FindingOut.model_validate(f) for f in findings],
    )


@router.post("/investigations/{investigation_id}/cancel", response_model=InvestigationOut)
def cancel_investigation(investigation_id: uuid.UUID, db: DbSession) -> InvestigationOut:
    inv = _get(db, investigation_id)
    if inv.status not in {s.value for s in TERMINAL_INVESTIGATION_STATUSES}:
        inv.cancel_requested = True
    return InvestigationOut.model_validate(inv)


@router.get("/investigations/{investigation_id}/artifacts", response_model=list[EvidenceOut])
def list_artifacts(investigation_id: uuid.UUID, db: DbSession) -> list[EvidenceOut]:
    inv = _get(db, investigation_id)
    rows = db.scalars(
        select(EvidenceAsset)
        .where(EvidenceAsset.investigation_id == inv.id)
        .order_by(EvidenceAsset.created_at)
    )
    return [EvidenceOut.model_validate(r) for r in rows]


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: uuid.UUID, db: DbSession) -> FileResponse:
    asset = db.get(EvidenceAsset, artifact_id)
    if asset is None:
        raise ApiError(404, "ARTIFACT_NOT_FOUND", "Artifact not found.")
    _get(db, asset.investigation_id)  # applies the same visibility rules as the run
    store = ArtifactStore(get_settings().artifacts_dir)
    try:
        path = store.path_for(asset.storage_key)
    except ValueError as exc:
        raise ApiError(404, "ARTIFACT_NOT_FOUND", "Artifact not found.") from exc
    if not path.is_file():
        raise ApiError(404, "ARTIFACT_NOT_FOUND", "Artifact file is no longer available.")
    ext = path.suffix
    filename = f"{asset.type}-{asset.id.hex[:8]}{ext}"
    disposition = "inline" if asset.mime_type == "image/png" else "attachment"
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=filename,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"},
    )


@router.get("/investigations/{investigation_id}/regression-test.spec.ts")
def regression_test_code(investigation_id: uuid.UUID, db: DbSession) -> PlainTextResponse:
    rt = (_get(db, investigation_id).result or {}).get("regression_test") or {}
    if not rt.get("code"):
        raise ApiError(404, "TEST_NOT_AVAILABLE", "No regression test was generated for this run.")
    return PlainTextResponse(rt["code"], media_type="text/plain; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="reprolab-{investigation_id}.spec.ts"',
        "X-Content-Type-Options": "nosniff",
    })  # fmt: skip


@router.get("/investigations/{investigation_id}/regression-test.json")
def regression_test_spec(investigation_id: uuid.UUID, db: DbSession) -> dict[str, Any]:
    rt = (_get(db, investigation_id).result or {}).get("regression_test") or {}
    if not rt.get("spec"):
        raise ApiError(404, "TEST_NOT_AVAILABLE", "No regression-test spec exists for this run.")
    return {"status": rt["status"], "reason": rt["reason"], "spec": rt["spec"],
            "validation": rt.get("validation")}  # fmt: skip


@router.get("/investigations/{investigation_id}/report.md", response_class=PlainTextResponse)
def report_markdown(investigation_id: uuid.UUID, db: DbSession) -> PlainTextResponse:
    inv = _get(db, investigation_id)
    if inv.result is None:
        raise ApiError(409, "REPORT_NOT_READY", "The investigation has no result yet.")
    project = db.get(Project, inv.project_id)
    steps = db.scalars(
        select(AgentStep).where(AgentStep.investigation_id == inv.id).order_by(AgentStep.sequence)
    )
    evidence = db.scalars(select(EvidenceAsset).where(EvidenceAsset.investigation_id == inv.id))
    md = render_markdown(
        title=f"Investigation {inv.id}",
        project_name=project.name if project else "unknown",
        bug_report=inv.bug_report,
        result=inv.result,
        steps=[
            {
                "sequence": s.sequence,
                "node": s.node,
                "tool": s.tool,
                "ok": s.ok,
                "summary": s.output_summary,
            }
            for s in steps
        ],
        evidence=[{"type": e.type, "label": e.label, "sha256": e.sha256} for e in evidence],
        snapshot_sha=None,
    )
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")


SSE_POLL_SECONDS = 0.5
SSE_MAX_SECONDS = 15 * 60


@router.get("/investigations/{investigation_id}/events")
async def stream_events(
    investigation_id: uuid.UUID,
    request: Request,
    last_event_id: str | None = Header(default=None),
    after: int | None = Query(default=None, ge=0),
) -> StreamingResponse:
    """Server-sent events replayed from the persisted event log; reconnect with Last-Event-ID."""
    with session_scope() as db:
        _get(db, investigation_id)
    cursor = 0
    if after is not None:
        cursor = after
    elif last_event_id is not None and last_event_id.isdigit():
        cursor = int(last_event_id)

    def fetch(after_seq: int) -> tuple[list[InvestigationEvent], bool]:
        with session_scope() as db:
            rows = list(db.scalars(
                select(InvestigationEvent)
                .where(InvestigationEvent.investigation_id == investigation_id, InvestigationEvent.sequence > after_seq)
                .order_by(InvestigationEvent.sequence).limit(200)
            ))  # fmt: skip
            status = db.scalar(
                select(Investigation.status).where(Investigation.id == investigation_id)
            )
            done = status is not None and InvestigationStatus(status).is_terminal
            return rows, done

    async def gen() -> AsyncIterator[str]:
        nonlocal cursor
        yield "retry: 2000\n\n"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + SSE_MAX_SECONDS
        idle_ticks = 0
        while loop.time() < deadline:
            if await request.is_disconnected():
                return
            rows, done = await asyncio.to_thread(fetch, cursor)
            for row in rows:
                cursor = row.sequence
                payload = json.dumps({"sequence": row.sequence, "type": row.type, "data": row.data,
                                      "created_at": row.created_at.isoformat()})  # fmt: skip
                yield f"id: {row.sequence}\nevent: {row.type}\ndata: {payload}\n\n"
            if done and not rows:
                yield "event: stream.end\ndata: {}\n\n"
                return
            idle_ticks = 0 if rows else idle_ticks + 1
            if idle_ticks and idle_ticks % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(SSE_POLL_SECONDS)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
