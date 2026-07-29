"""SQLAlchemy 2.0 async ORM models for agent-memory PostgreSQL storage.

All tables include tenant_id for Row-Level Security (RLS) enforcement.
Uses Mapped annotations with the 2.0-style declarative base.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all agent-memory PostgreSQL models."""

    @property
    def _table_args_prefix(self) -> dict:
        return {"schema": "agent_memory"}


class MemoryModel(Base):
    """A memory record — the aggregate root for a memory's lifecycle."""

    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        index=True,
    )
    purpose: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    memory_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    subject_key: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    predicate: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="candidate",
        index=True,
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationship
    versions: Mapped[list[MemoryVersionModel]] = relationship(
        back_populates="memory",
        cascade="all, delete-orphan",
        order_by="MemoryVersionModel.version",
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryModel id={self.id} tenant={self.tenant_id} "
            f"subject={self.subject_id} type={self.memory_type} "
            f"status={self.status} version={self.current_version}>"
        )


class MemoryVersionModel(Base):
    """An immutable version of a memory — append-only."""

    __tablename__ = "memory_versions"

    id: Mapped[int] = mapped_column(
        Integer,
        autoincrement=True,  # synthetic PK for Alembic happiness
    )
    memory_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    value: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )
    searchable_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(128),
        nullable=True,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    sensitivity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="internal",
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="user_explicit",
    )
    evidence_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        default=None,
    )
    supersedes_memory_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    consent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_memory_versions"),
        {"sqlite_autoincrement": True},
    )

    # Relationship
    memory: Mapped[MemoryModel] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return (
            f"<MemoryVersionModel memory_id={self.memory_id} "
            f"version={self.version} confidence={self.confidence}>"
        )


class ConsentModel(Base):
    """A stored consent record — versioned and immutable in core attributes."""

    __tablename__ = "consent"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    purpose: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    allow_write: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    allow_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    allowed_memory_types: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    allowed_sensitivity: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    retention_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return (
            f"<ConsentModel id={self.id} tenant={self.tenant_id} "
            f"subject={self.subject_id} purpose={self.purpose} "
            f"version={self.version}>"
        )


class AuditLogModel(Base):
    """Append-only audit log — every operation is auditable."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        default=None,
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLogModel id={self.id} tenant={self.tenant_id} "
            f"actor={self.actor_id} action={self.action}>"
        )
