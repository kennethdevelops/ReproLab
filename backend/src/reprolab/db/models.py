"""SQLAlchemy models. Schema changes go through Alembic migrations only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    repo_url: Mapped[str | None] = mapped_column(String(500))
    repo_ref: Mapped[str | None] = mapped_column(String(200))
    test_origin: Mapped[str] = mapped_column(String(500))
    mode: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    snapshots: Mapped[list[RepoSnapshot]] = relationship(back_populates="project")


class RepoSnapshot(Base):
    __tablename__ = "repo_snapshots"
    __table_args__ = (
        UniqueConstraint("project_id", "commit_sha", "embed_model", "parser_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(200))
    source_kind: Mapped[str] = mapped_column(String(20))  # local_snapshot | github
    embed_model: Mapped[str] = mapped_column(String(200))
    embed_dim: Mapped[int | None] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), index=True)
    progress: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Canonical citation URL prefix at this commit (GitHub blob URL); None for local snapshots.
    citation_base_url: Mapped[str | None] = mapped_column(String(500))

    project: Mapped[Project] = relationship(back_populates="snapshots")


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (UniqueConstraint("snapshot_id", "path"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20))  # source | test | documentation | configuration
    language: Mapped[str] = mapped_column(String(30))
    content_sha: Mapped[str] = mapped_column(String(64))
    # Full text is kept so read_source_file can serve only indexed material.
    content: Mapped[str] = mapped_column(Text)
    line_count: Mapped[int] = mapped_column(Integer)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)


class SourceChunk(Base):
    __tablename__ = "source_chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    # Denormalised so every query can be scoped to one snapshot without a join.
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), index=True
    )
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    search_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', search_text)", persisted=True)
    )
    # Dimension varies with the embedding model; it is tracked on the snapshot (embed_dim).
    embedding: Mapped[list[float] | None] = mapped_column(Vector())


class RetrievalEvent(Base):
    __tablename__ = "retrieval_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    chunk_ids: Mapped[list[Any]] = mapped_column(default=list)
    rankings: Mapped[dict[str, Any]] = mapped_column(default=dict)
    timing_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created_at()


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repo_snapshots.id", ondelete="SET NULL")
    )
    bug_report: Mapped[str] = mapped_column(Text)
    start_path: Mapped[str] = mapped_column(String(500))
    viewport: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)
    rag_mode: Mapped[str] = mapped_column(String(20))
    model_id: Mapped[str] = mapped_column(String(200))
    limits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column()
    status_reason: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    retry_count: Mapped[int] = mapped_column(default=0)
    client_key: Mapped[str | None] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestigationEvent(Base):
    """Ordered, persisted progress events; the SSE stream replays these."""

    __tablename__ = "investigation_events"
    __table_args__ = (UniqueConstraint("investigation_id", "sequence"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("investigation_id", "sequence"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(60))
    tool: Mapped[str | None] = mapped_column(String(60))
    redacted_input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output_summary: Mapped[str | None] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(default=True)
    time_ms: Mapped[int] = mapped_column(Integer, default=0)
    usage: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class EvidenceAsset(Base):
    __tablename__ = "evidence_assets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30))  # screenshot | trace | console | network | test
    label: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    step_sequence: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30))  # observation | hypothesis | recommendation
    statement: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(30))
    citations: Mapped[list[Any]] = mapped_column(default=list)
    evidence_ids: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = _created_at()


class GeneratedTest(Base):
    __tablename__ = "generated_tests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    test_spec_json: Mapped[dict[str, Any]] = mapped_column()
    source_code: Mapped[str] = mapped_column(Text)
    validation_state: Mapped[str] = mapped_column(String(30))
    buggy_result: Mapped[dict[str, Any] | None] = mapped_column()
    fixed_result: Mapped[dict[str, Any] | None] = mapped_column()
    created_at: Mapped[datetime] = _created_at()
