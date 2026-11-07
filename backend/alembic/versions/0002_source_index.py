"""Repository index: source documents, chunks (FTS + pgvector), retrieval events.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("repo_snapshots", sa.Column("citation_base_url", sa.String(500)))

    op.create_table(
        "source_documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "snapshot_id",
            UUID,
            sa.ForeignKey("repo_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("language", sa.String(30), nullable=False),
        sa.Column("content_sha", sa.String(64), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("line_count", sa.Integer, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.UniqueConstraint("snapshot_id", "path"),
    )
    op.create_index("ix_source_documents_snapshot_id", "source_documents", ["snapshot_id"])

    op.create_table(
        "source_chunks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "document_id",
            UUID,
            sa.ForeignKey("source_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            UUID,
            sa.ForeignKey("repo_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("symbol", sa.String(200)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("search_text", sa.Text, nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('english', search_text)", persisted=True),
        ),
        sa.Column("embedding", Vector()),
        sa.CheckConstraint("start_line >= 1 AND end_line >= start_line", name="ck_chunk_lines"),
    )
    op.create_index("ix_source_chunks_document_id", "source_chunks", ["document_id"])
    op.create_index("ix_source_chunks_snapshot_id", "source_chunks", ["snapshot_id"])
    op.create_index("ix_source_chunks_content_hash", "source_chunks", ["content_hash"])
    op.create_index(
        "ix_source_chunks_search_vector", "source_chunks", ["search_vector"], postgresql_using="gin"
    )
    # No ANN (HNSW) index yet: the column has no fixed dimension because it depends on the
    # embedding model, and per-snapshot exact scans are fast at demo scale (ADR-0003).

    op.create_table(
        "retrieval_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("investigation_id", UUID, sa.ForeignKey("investigations.id", ondelete="CASCADE")),
        sa.Column(
            "snapshot_id",
            UUID,
            sa.ForeignKey("repo_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("chunk_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("rankings", JSONB, nullable=False, server_default="{}"),
        sa.Column("timing_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_retrieval_events_investigation_id", "retrieval_events", ["investigation_id"]
    )
    op.create_index("ix_retrieval_events_snapshot_id", "retrieval_events", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("retrieval_events")
    op.drop_table("source_chunks")
    op.drop_table("source_documents")
    op.drop_column("repo_snapshots", "citation_base_url")
