"""Consent management example — save, query, and revoke consent.

Consent is stored as versioned records in the backend.

Run: python examples/consent/consent.py
"""

import asyncio
from uuid import uuid4

from agent_memory.context import TenantContext
from agent_memory.domain.consent import ConsentRecord
from agent_memory.exceptions import ConsentNotFoundError
from agent_memory.providers.in_memory_backend import InMemoryBackend


async def main():
    backend = InMemoryBackend()
    subject_id = "user-1"
    tenant_id = "t1"
    ctx = TenantContext(tenant_id=tenant_id, actor_id="admin")

    # Create and save a consent record
    record = ConsentRecord(
        id=uuid4(),
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose="general",
        actor_id="admin",
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public"},
        allow_read=True,
        allow_write=False,
        current_version=1,
        is_revoked=False,
    )
    await backend.save_consent(record, context=ctx)
    print(f"Consent saved: {record.id}")

    # Query active consent
    active = await backend.get_active_consent(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose="general",
    )
    print(f"Active after save: {active is not None}")

    # Revoke consent
    await backend.revoke_consent(record.id, context=ctx)
    print("Consent revoked")

    # Verify — get_active_consent skips revoked records
    active = await backend.get_active_consent(
        tenant_id=tenant_id,
        subject_id=subject_id,
        purpose="general",
    )
    print(f"Active after revoke: {active is not None}")

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())