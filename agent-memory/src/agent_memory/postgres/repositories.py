"""Repository layer for PostgreSQL backend.

Provides:
- MemoryRepository: CRUD operations for memories and memory versions
- ConsentRepository: CRUD and active-consent lookup
- AuditRepository: append-only audit log

All repositories accept an AsyncSession and domain models,
converting between ORM models and domain models internally.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from agent_memory.domain.audit import AuditEvent, AuditQuery
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.exceptions import (
    ConsentNotFoundError,
    MemoryNotFoundError,
    TenantIsolationError,
)
from agent_memory.postgres.models import (
    AuditLogModel,
    ConsentModel,
    MemoryModel,
    MemoryVersionModel,
)


# ── Helpers ───────────────────────────────────────────────────────────────────────


def _ensure_tenant_match(model_tenant: str, context_tenant: str) -> None:
    """Verify that the model's tenant matches the context tenant."""
    if model_tenant != context_tenant:
        raise TenantIsolationError(
            f"Tenant mismatch: expected '{model_tenant}' but context has '{context_tenant}'"
        )


# ── MemoryRepository ──────────────────────────────────────────────────────────────


class MemoryRepository:
    """Repository for MemoryRecord and MemoryVersion persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── ORM ↔ Domain conversion ──────────────────────────────────────────────────

    @staticmethod
    def _orm_to_memory(orm: MemoryModel) -> MemoryRecord:
        return MemoryRecord(
            id=orm.id,
            tenant_id=orm.tenant_id,
            subject_id=orm.subject_id,
            purpose=orm.purpose,
            memory_type=orm.memory_type,  # type: ignore[arg-type]
            subject_key=orm.subject_key,
            predicate=orm.predicate,
            status=orm.status,  # type: ignore[arg-type]
            current_version=orm.current_version,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def _memory_to_orm(record: MemoryRecord) -> MemoryModel:
        return MemoryModel(
            id=record.id,
            tenant_id=record.tenant_id,
            subject_id=record.subject_id,
            purpose=record.purpose,
            memory_type=record.memory_type,
            subject_key=record.subject_key,
            predicate=record.predicate,
            status=record.status,
            current_version=record.current_version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _orm_to_version(orm: MemoryVersionModel) -> MemoryVersion:
        return MemoryVersion(
            memory_id=orm.memory_id,
            version=orm.version,
            value=orm.value,
            searchable_summary=orm.searchable_summary,
            confidence=orm.confidence,
            sensitivity=orm.sensitivity,  # type: ignore[arg-type]
            source_type=orm.source_type,  # type: ignore[arg-type]
            evidence_text=orm.evidence_text,
            source_message_id=orm.source_message_id,
            supersedes_memory_id=orm.supersedes_memory_id,
            consent_id=orm.consent_id,
            created_at=orm.created_at,
        )

    @staticmethod
    def _version_to_orm(version: MemoryVersion) -> MemoryVersionModel:
        return MemoryVersionModel(
            memory_id=version.memory_id,
            version=version.version,
            value=version.value,
            searchable_summary=version.searchable_summary,
            confidence=version.confidence,
            sensitivity=version.sensitivity,
            source_type=version.source_type,
            evidence_text=version.evidence_text,
            source_message_id=version.source_message_id,
            supersedes_memory_id=version.supersedes_memory_id,
            consent_id=version.consent_id,
            created_at=version.created_at,
        )

    # ── Operations ───────────────────────────────────────────────────────────────

    async def save(
        self,
        record: MemoryRecord,
        version: MemoryVersion,
    ) -> MemoryRecord:
        """Save a new memory record with its first version."""
        # Persist the memory record
        orm_memory = self._memory_to_orm(record)
        self.session.add(orm_memory)

        # Persist the first version
        orm_version = self._version_to_orm(version)
        self.session.add(orm_version)

        await self.session.flush()
        return record

    async def get(
        self,
        memory_id: UUID,
        *,
        tenant_id: str,
    ) -> MemoryRecord | None:
        """Get a memory record by ID, scoped to tenant."""
        stmt = select(MemoryModel).where(
            MemoryModel.id == memory_id,
            MemoryModel.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._orm_to_memory(orm)

    async def list(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str | None = None,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memory records matching the given filters."""
        conditions = [
            MemoryModel.tenant_id == tenant_id,
            MemoryModel.subject_id == subject_id,
        ]
        if purpose is not None:
            conditions.append(MemoryModel.purpose == purpose)
        if memory_type is not None:
            conditions.append(MemoryModel.memory_type == memory_type)
        if status is not None:
            conditions.append(MemoryModel.status == status)

        stmt = (
            select(MemoryModel)
            .where(*conditions)
            .order_by(MemoryModel.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [self._orm_to_memory(o) for o in orms]

    async def add_version(
        self,
        memory_id: UUID,
        version: MemoryVersion,
        *,
        tenant_id: str,
    ) -> MemoryVersion:
        """Add a new version to an existing memory record.

        Updates the memory's current_version.
        """
        # Verify memory exists and belongs to tenant
        memory = await self.get(memory_id, tenant_id=tenant_id)
        if memory is None:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")

        # Persist the new version
        orm_version = self._version_to_orm(version)
        self.session.add(orm_version)

        # Update the memory's current_version
        stmt = (
            update(MemoryModel)
            .where(
                MemoryModel.id == memory_id,
                MemoryModel.tenant_id == tenant_id,
            )
            .values(
                current_version=version.version,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return version

    async def update_status(
        self,
        memory_id: UUID,
        status: str,
        *,
        tenant_id: str,
    ) -> None:
        """Update the status of a memory record."""
        stmt = (
            update(MemoryModel)
            .where(
                MemoryModel.id == memory_id,
                MemoryModel.tenant_id == tenant_id,
            )
            .values(
                status=status,
                updated_at=datetime.now(timezone.utc),
            )
        )
        result = await self.session.execute(stmt)
        if result.rowcount == 0:
            raise MemoryNotFoundError(f"Memory {memory_id} not found")
        await self.session.flush()


# ── ConsentRepository ─────────────────────────────────────────────────────────────


class ConsentRepository:
    """Repository for ConsentRecord persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _orm_to_consent(orm: ConsentModel) -> ConsentRecord:
        return ConsentRecord(
            id=orm.id,
            tenant_id=orm.tenant_id,
            subject_id=orm.subject_id,
            actor_id=orm.actor_id,
            purpose=orm.purpose,
            allow_write=orm.allow_write,
            allow_read=orm.allow_read,
            allowed_memory_types=set(orm.allowed_memory_types or []),
            allowed_sensitivity=set(orm.allowed_sensitivity or []),
            version=orm.version,
            revoked_at=orm.revoked_at,
            expires_at=orm.expires_at,
            retention_days=orm.retention_days,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def _consent_to_orm(record: ConsentRecord) -> ConsentModel:
        return ConsentModel(
            id=record.id,
            tenant_id=record.tenant_id,
            subject_id=record.subject_id,
            actor_id=record.actor_id,
            purpose=record.purpose,
            allow_write=record.allow_write,
            allow_read=record.allow_read,
            allowed_memory_types=list(record.allowed_memory_types),
            allowed_sensitivity=list(record.allowed_sensitivity),
            version=record.version,
            revoked_at=record.revoked_at,
            expires_at=record.expires_at,
            retention_days=record.retention_days,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    async def save(self, record: ConsentRecord) -> ConsentRecord:
        """Save a new consent record."""
        orm = self._consent_to_orm(record)
        self.session.add(orm)
        await self.session.flush()
        return record

    async def get(self, consent_id: UUID, *, tenant_id: str) -> ConsentRecord | None:
        """Get a consent record by ID."""
        stmt = select(ConsentModel).where(
            ConsentModel.id == consent_id,
            ConsentModel.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._orm_to_consent(orm)

    async def get_active(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str,
    ) -> ConsentRecord | None:
        """Get the active (non-revoked, non-expired) consent for a subject/purpose."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(ConsentModel)
            .where(
                ConsentModel.tenant_id == tenant_id,
                ConsentModel.subject_id == subject_id,
                ConsentModel.purpose == purpose,
                ConsentModel.revoked_at.is_(None),
                or_(
                    ConsentModel.expires_at.is_(None),
                    ConsentModel.expires_at > now,
                ),
            )
            .order_by(ConsentModel.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return self._orm_to_consent(orm)

    async def revoke(
        self,
        consent_id: UUID,
        *,
        tenant_id: str,
    ) -> ConsentRecord:
        """Revoke a consent record."""
        stmt = select(ConsentModel).where(
            ConsentModel.id == consent_id,
            ConsentModel.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            raise ConsentNotFoundError(f"Consent {consent_id} not found")

        orm.revoked_at = datetime.now(timezone.utc)
        orm.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return self._orm_to_consent(orm)

    async def list(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        """List consent records."""
        conditions = [ConsentModel.tenant_id == tenant_id]
        if subject_id is not None:
            conditions.append(ConsentModel.subject_id == subject_id)

        stmt = (
            select(ConsentModel)
            .where(*conditions)
            .order_by(ConsentModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [self._orm_to_consent(o) for o in orms]


# ── AuditRepository ───────────────────────────────────────────────────────────────


class AuditRepository:
    """Append-only repository for audit events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _orm_to_event(orm: AuditLogModel) -> AuditEvent:
        return AuditEvent(
            id=orm.id,
            tenant_id=orm.tenant_id,
            actor_id=orm.actor_id,
            action=orm.action,  # type: ignore[arg-type]
            memory_type=orm.memory_type,
            resource_type=(
                orm.details.get("resource_type")
                if orm.details and "resource_type" in orm.details
                else None
            ),
            resource_id=(
                orm.details.get("resource_id")
                if orm.details and "resource_id" in orm.details
                else None
            ),
            outcome=(
                orm.details.get("outcome", "allowed")
                if orm.details
                else "allowed"
            ),
            reason=orm.details.get("reason") if orm.details else None,
            metadata=orm.details.get("metadata", {}) if orm.details else {},
            created_at=orm.created_at,
        )

    @staticmethod
    def _event_to_orm(event: AuditEvent) -> AuditLogModel:
        details: dict[str, Any] = {}
        if event.resource_type:
            details["resource_type"] = event.resource_type
        if event.resource_id:
            details["resource_id"] = event.resource_id
        if event.outcome != "allowed" or event.reason:
            details["outcome"] = event.outcome
        if event.reason:
            details["reason"] = event.reason
        if event.metadata:
            details["metadata"] = event.metadata

        return AuditLogModel(
            id=event.id,
            tenant_id=event.tenant_id,
            actor_id=event.actor_id,
            action=event.action,
            memory_type=event.resource_type,
            details=details if details else None,
            created_at=event.created_at,
        )

    async def append(self, event: AuditEvent) -> AuditEvent:
        """Append an audit event."""
        orm = self._event_to_orm(event)
        self.session.add(orm)
        await self.session.flush()
        return event

    async def query(self, query: AuditQuery) -> list[AuditEvent]:
        """Query the audit log."""
        conditions = [AuditLogModel.tenant_id == query.tenant_id]
        if query.actor_id is not None:
            conditions.append(AuditLogModel.actor_id == query.actor_id)
        if query.action is not None:
            conditions.append(AuditLogModel.action == query.action)
        if query.outcome is not None:
            conditions.append(AuditLogModel.details["outcome"].astext == query.outcome)
        if query.from_date is not None:
            conditions.append(AuditLogModel.created_at >= query.from_date)
        if query.to_date is not None:
            conditions.append(AuditLogModel.created_at <= query.to_date)

        stmt = (
            select(AuditLogModel)
            .where(*conditions)
            .order_by(AuditLogModel.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )
        result = await self.session.execute(stmt)
        orms = result.scalars().all()
        return [self._orm_to_event(o) for o in orms]

    async def count(self, query: AuditQuery) -> int:
        """Count audit events matching the query."""
        conditions = [AuditLogModel.tenant_id == query.tenant_id]
        if query.actor_id is not None:
            conditions.append(AuditLogModel.actor_id == query.actor_id)
        if query.action is not None:
            conditions.append(AuditLogModel.action == query.action)
        if query.outcome is not None:
            conditions.append(AuditLogModel.details["outcome"].astext == query.outcome)
        if query.from_date is not None:
            conditions.append(AuditLogModel.created_at >= query.from_date)
        if query.to_date is not None:
            conditions.append(AuditLogModel.created_at <= query.to_date)

        stmt = select(func.count(AuditLogModel.id)).where(*conditions)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0