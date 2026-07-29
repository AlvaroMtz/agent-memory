"""ConsentProvider port — abstract interface for consent storage and validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from agent_memory.context import TenantContext
from agent_memory.domain.consent import ConsentGrant, ConsentRecord


@runtime_checkable
class ConsentProvider(Protocol):
    """Port for consent storage and validation.

    The canonical implementation is backed by the same PostgreSQL store.
    Separate interface to allow different consent backends.
    """

    async def get_active_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str,
        purpose: str,
    ) -> ConsentRecord | None:
        """Get the currently active consent for a subject and purpose."""
        ...

    async def grant_consent(
        self,
        grant: ConsentGrant,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Grant consent for a subject and purpose."""
        ...

    async def revoke_consent(
        self,
        consent_id: UUID,
        *,
        context: TenantContext,
    ) -> ConsentRecord:
        """Revoke a previously granted consent."""
        ...

    async def list_consent(
        self,
        *,
        tenant_id: str,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[ConsentRecord]:
        """List consent records."""
        ...


class ConsentProviderFactory(Protocol):
    """Factory for creating ConsentProvider instances."""

    def create(self, **kwargs) -> ConsentProvider: ...
