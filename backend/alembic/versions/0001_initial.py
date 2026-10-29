"""Initial schema: projects, snapshots, investigations, events, steps, evidence, findings, tests.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TS = sa.DateTime(timezone=True)


def _created() -> sa.Column[sa.DateTime]:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "projects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("repo_url", sa.String(500)),
        sa.Column("repo_ref", sa.String(200)),
        sa.Column("test_origin", sa.String(500), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("description", sa.Text),
        _created(),
    )

    op.create_table(
        "repo_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "project_id", UUID, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("ref", sa.String(200)),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("embed_model", sa.String(200), nullable=False),
        sa.Column("embed_dim", sa.Integer),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text),
        _created(),
        sa.Column("indexed_at", TS),
        sa.UniqueConstraint("project_id", "commit_sha", "embed_model", "parser_version"),
    )
    op.create_index("ix_repo_snapshots_project_id", "repo_snapshots", ["project_id"])
    op.create_index("ix_repo_snapshots_status", "repo_snapshots", ["status"])

    op.create_table(
        "investigations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "project_id", UUID, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("snapshot_id", UUID, sa.ForeignKey("repo_snapshots.id", ondelete="SET NULL")),
        sa.Column("bug_report", sa.Text, nullable=False),
        sa.Column("start_path", sa.String(500), nullable=False),
        sa.Column("viewport", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rag_mode", sa.String(20), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("limits", JSONB, nullable=False, server_default="{}"),
        sa.Column("usage", JSONB, nullable=False, server_default="{}"),
        sa.Column("result", JSONB),
        sa.Column("status_reason", sa.Text),
        sa.Column("cancel_requested", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("client_key", sa.String(100)),
        _created(),
        sa.Column("started_at", TS),
        sa.Column("completed_at", TS),
    )
    op.create_index("ix_investigations_project_id", "investigations", ["project_id"])
    op.create_index("ix_investigations_status", "investigations", ["status"])
    op.create_index("ix_investigations_client_key", "investigations", ["client_key"])

    op.create_table(
        "investigation_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "investigation_id",
            UUID,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        _created(),
        sa.UniqueConstraint("investigation_id", "sequence"),
    )
    op.create_index(
        "ix_investigation_events_investigation_id", "investigation_events", ["investigation_id"]
    )

    op.create_table(
        "agent_steps",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "investigation_id",
            UUID,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("node", sa.String(60), nullable=False),
        sa.Column("tool", sa.String(60)),
        sa.Column("redacted_input", JSONB, nullable=False, server_default="{}"),
        sa.Column("output_summary", sa.Text),
        sa.Column("ok", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("time_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("usage", JSONB, nullable=False, server_default="{}"),
        _created(),
        sa.UniqueConstraint("investigation_id", "sequence"),
    )
    op.create_index("ix_agent_steps_investigation_id", "agent_steps", ["investigation_id"])

    op.create_table(
        "evidence_assets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "investigation_id",
            UUID,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("step_sequence", sa.Integer),
        _created(),
    )
    op.create_index("ix_evidence_assets_investigation_id", "evidence_assets", ["investigation_id"])

    op.create_table(
        "findings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "investigation_id",
            UUID,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("verification_status", sa.String(30), nullable=False),
        sa.Column("citations", JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_ids", JSONB, nullable=False, server_default="[]"),
        _created(),
    )
    op.create_index("ix_findings_investigation_id", "findings", ["investigation_id"])

    op.create_table(
        "generated_tests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "investigation_id",
            UUID,
            sa.ForeignKey("investigations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("test_spec_json", JSONB, nullable=False),
        sa.Column("source_code", sa.Text, nullable=False),
        sa.Column("validation_state", sa.String(30), nullable=False),
        sa.Column("buggy_result", JSONB),
        sa.Column("fixed_result", JSONB),
        _created(),
    )
    op.create_index("ix_generated_tests_investigation_id", "generated_tests", ["investigation_id"])


def downgrade() -> None:
    for table in (
        "generated_tests",
        "findings",
        "evidence_assets",
        "agent_steps",
        "investigation_events",
        "investigations",
        "repo_snapshots",
        "projects",
    ):
        op.drop_table(table)
