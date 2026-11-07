from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from reprolab.api.deps import DbSession
from reprolab.api.errors import ApiError
from reprolab.config.settings import get_settings
from reprolab.db.enums import IndexStatus
from reprolab.db.models import Project, RepoSnapshot
from reprolab.indexing.chunker import CHUNKER_VERSION
from reprolab.indexing.embeddings import get_embedder
from reprolab.indexing.pipeline import source_for_project
from reprolab.indexing.sources import SourceError
from reprolab.retrieval.search import RetrievalError, current_snapshot, read_source, search

router = APIRouter(prefix="/projects", tags=["projects"])


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    commit_sha: str
    ref: str | None
    status: str
    embed_model: str
    indexed_at: datetime | None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    repo_url: str | None
    repo_ref: str | None
    test_origin: str
    mode: str
    created_at: datetime
    current_snapshot: SnapshotOut | None = None


def _to_out(db: Session, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    snapshot = current_snapshot(db, project.id)
    out.current_snapshot = SnapshotOut.model_validate(snapshot) if snapshot else None
    return out


@router.get("", response_model=list[ProjectOut])
def list_projects(db: DbSession) -> list[ProjectOut]:
    query = select(Project).order_by(Project.created_at)
    if get_settings().is_public_demo:
        query = query.where(Project.mode == "demo")
    return [_to_out(db, p) for p in db.scalars(query)]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, db: DbSession) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None or (get_settings().is_public_demo and project.mode != "demo"):
        raise ApiError(404, "PROJECT_NOT_FOUND", "Project not found.")
    return _to_out(db, project)


# --- Repository index -------------------------------------------------------------------------


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str | None = Field(default=None, max_length=200)


class IndexStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    commit_sha: str
    ref: str | None
    source_kind: str
    status: str
    embed_model: str
    embed_dim: int | None
    parser_version: str
    progress: dict[str, Any]
    error: str | None
    citation_base_url: str | None
    created_at: datetime
    indexed_at: datetime | None


class IndexAccepted(BaseModel):
    index_job_id: uuid.UUID
    status: str
    commit_sha: str


def _celery_enqueue_index(snapshot_id: uuid.UUID) -> None:
    from reprolab.workers.tasks import index_project

    index_project.delay(str(snapshot_id))


# Indirection so tests can run indexing inline without a broker.
enqueue_index: list[Callable[[uuid.UUID], None]] = [_celery_enqueue_index]


def _visible_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or (get_settings().is_public_demo and project.mode != "demo"):
        raise ApiError(404, "PROJECT_NOT_FOUND", "Project not found.")
    return project


@router.post("/{project_id}/index", status_code=202, response_model=IndexAccepted)
def start_index(
    project_id: uuid.UUID, db: DbSession, body: IndexRequest | None = None
) -> IndexAccepted:
    settings = get_settings()
    if settings.is_public_demo:
        raise ApiError(403, "INDEXING_DISABLED", "Indexing is operator-only in the public demo.")
    project = _visible_project(db, project_id)
    ref = (body.ref if body else None) or project.repo_ref
    try:
        resolved = source_for_project(project, settings).resolve(ref)
    except SourceError as exc:
        raise ApiError(422, exc.code, str(exc)) from exc
    embed_model = get_embedder(settings).model_id
    snap = db.scalars(
        select(RepoSnapshot).where(
            RepoSnapshot.project_id == project.id,
            RepoSnapshot.commit_sha == resolved.commit_sha,
            RepoSnapshot.embed_model == embed_model,
            RepoSnapshot.parser_version == CHUNKER_VERSION,
        )
    ).first()
    retryable = (IndexStatus.FAILED.value, IndexStatus.CANCELLED.value)
    if snap is not None and snap.status not in retryable:
        # Idempotent: the same snapshot is already ready or in progress.
        return IndexAccepted(index_job_id=snap.id, status=snap.status, commit_sha=snap.commit_sha)
    if snap is None:
        snap = RepoSnapshot(
            project_id=project.id,
            commit_sha=resolved.commit_sha,
            ref=resolved.ref,
            source_kind=resolved.source_kind,
            embed_model=embed_model,
            parser_version=CHUNKER_VERSION,
            status=IndexStatus.PENDING.value,
            progress={},
            citation_base_url=resolved.blob_url_prefix,
        )
        db.add(snap)
    else:
        snap.status = IndexStatus.PENDING.value
        snap.error = None
    db.commit()
    try:
        enqueue_index[0](snap.id)
    except Exception as exc:
        snap.status = IndexStatus.FAILED.value
        snap.error = "Job broker unavailable."
        db.commit()
        raise ApiError(503, "BROKER_UNAVAILABLE", "The job queue is unavailable.") from exc
    db.refresh(snap)
    return IndexAccepted(index_job_id=snap.id, status=snap.status, commit_sha=snap.commit_sha)


@router.get("/{project_id}/index", response_model=list[IndexStatusOut])
def index_status(project_id: uuid.UUID, db: DbSession) -> list[IndexStatusOut]:
    project = _visible_project(db, project_id)
    rows = db.scalars(
        select(RepoSnapshot)
        .where(RepoSnapshot.project_id == project.id)
        .order_by(RepoSnapshot.created_at.desc())
        .limit(10)
    )
    return [IndexStatusOut.model_validate(r) for r in rows]


class HitOut(BaseModel):
    chunk_id: uuid.UUID
    path: str
    kind: str
    start_line: int
    end_line: int
    symbol: str | None
    excerpt: str
    score: float
    ranks: dict[str, int]
    citation_url: str | None


class SearchOut(BaseModel):
    snapshot_id: uuid.UUID
    commit_sha: str
    strategy: str
    query: str
    timing_ms: int
    hits: list[HitOut]
    candidates: dict[str, list[dict[str, Any]]]


def _ready_snapshot(db: Session, project: Project) -> RepoSnapshot:
    snap = current_snapshot(db, project.id)
    if snap is None:
        raise ApiError(409, "NOT_INDEXED", "This project has no ready repository index.")
    return snap


DocKind = Literal["source", "test", "documentation", "configuration"]


@router.get("/{project_id}/search", response_model=SearchOut)
def search_project(
    project_id: uuid.UUID,
    db: DbSession,
    q: str = Query(min_length=1, max_length=500),
    strategy: Literal["lexical", "vector", "hybrid"] = "hybrid",
    top_k: int = Query(default=6, ge=1, le=20),
    kind: Annotated[list[DocKind] | None, Query()] = None,
) -> SearchOut:
    settings = get_settings()
    project = _visible_project(db, project_id)
    snap = _ready_snapshot(db, project)
    embedder = get_embedder(settings) if strategy != "lexical" else None
    try:
        result = search(
            db,
            snap,
            q,
            strategy,
            embedder,
            top_k=top_k,
            candidates=settings.retrieval_candidates,
            rrf_k=settings.retrieval_rrf_k,
            kinds=list(kind) if kind else None,
        )
    except RetrievalError as exc:
        raise ApiError(409, exc.code, str(exc)) from exc
    return SearchOut(
        snapshot_id=result.snapshot_id,
        commit_sha=result.commit_sha,
        strategy=result.strategy,
        query=result.query,
        timing_ms=result.timing_ms,
        candidates=result.candidates,
        hits=[HitOut(**vars(h)) for h in result.hits],
    )


class SourceOut(BaseModel):
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    commit_sha: str


@router.get("/{project_id}/source", response_model=SourceOut)
def read_project_source(
    project_id: uuid.UUID,
    db: DbSession,
    path: str = Query(min_length=1, max_length=500),
    start_line: int = Query(default=1, ge=1),
    end_line: int = Query(default=200, ge=1),
) -> SourceOut:
    project = _visible_project(db, project_id)
    snap = _ready_snapshot(db, project)
    try:
        excerpt = read_source(db, snap, path, start_line, end_line)
    except RetrievalError as exc:
        status = 404 if exc.code == "SOURCE_NOT_FOUND" else 422
        raise ApiError(status, exc.code, str(exc)) from exc
    return SourceOut(**vars(excerpt))
