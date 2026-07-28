"""Initial migration: create all four core tables.

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create memories, memory_versions, consent, and audit_log tables."""

    # ── memories ──────────────────────────────────────────────────────────────────
    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("subject_id", sa.String(256), nullable=False, index=True),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False, index=True),
        sa.Column("subject_key", sa.String(256), nullable=False),
        sa.Column("predicate", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="candidate", index=True),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── memory_versions ───────────────────────────────────────────────────────────
    op.create_table(
        "memory_versions",
        sa.Column("id", sa.Integer, autoincrement=True),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("searchable_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("sensitivity", sa.String(32), nullable=False, server_default="internal"),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="user_explicit"),
        sa.Column("evidence_text", sa.Text, nullable=True),
        sa.Column("source_message_id", sa.String(256), nullable=True),
        sa.Column("supersedes_memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("consent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_versions"),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_memory_versions_memory_id",
        "memory_versions",
        ["memory_id"],
    )

    # ── consent ───────────────────────────────────────────────────────────────────
    op.create_table(
        "consent",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("subject_id", sa.String(256), nullable=False, index=True),
        sa.Column("actor_id", sa.String(256), nullable=False),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("allow_write", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allow_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("allowed_memory_types", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("allowed_sensitivity", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_days", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── audit_log ─────────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("actor_id", sa.String(256), nullable=False),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("memory_type", sa.String(32), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Additional indexes ────────────────────────────────────────────────────────
    op.create_index("ix_memories_tenant_subject", "memories", ["tenant_id", "subject_id"])
    op.create_index("ix_consent_tenant_subject_purpose", "consent", ["tenant_id", "subject_id", "purpose"])
    op.create_index("ix_audit_log_tenant_action", "audit_log", ["tenant_id", "action"])


def downgrade() -> None:
    """Drop all four tables in reverse dependency order."""

    op.drop_table("memory_versions")
    op.drop_table("memories")
    op.drop_table("consent")
    op.drop_table("audit_log")