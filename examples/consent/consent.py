"""Consent example — demonstrate consent lifecycle with the MemoryClient.

Shows: grant consent → remember with consent → revoke → blocked write.

Run: python examples/consent/consent.py
"""

import asyncio

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor


async def main():
    backend = InMemoryBackend()
    extractor = RuleBasedExtractor()
    client = MemoryClient(backend, extractor, consent=backend)

    context = MemoryContext(
        tenant_id="tenant-a",
        subject_id="user-1",
        actor_id="assistant-1",
        purpose="example",
    )

    async with client:
        # Grant consent for the subject
        record = await client.grant_consent(
            context,
            memory_types=["preference"],
            sensitivity="public",
            allow_read=True,
            allow_write=True,
        )
        print(f"Consent granted: {record.id}")
        print(f"  allowed_memory_types: {record.allowed_memory_types}")
        print(f"  allowed_sensitivity: {record.allowed_sensitivity}")

        # Remember with consent — should work
        messages = [
            {"id": "msg-1", "role": "user", "content": "Prefiero respuestas cortas."},
        ]
        result = await client.remember(context=context, messages=messages)
        print(f"\nRemembered {result.count} memory/memories after consent")

        # Revoke consent
        revoked = await client.revoke_consent("user-1", context)
        print(f"\nConsent revoked: {revoked.revoked_at}")

        # Try to remember again — should be blocked
        result2 = await client.remember(context=context, messages=messages)
        print(f"\nAfter revoke: {result2.count} memories persisted (0 = blocked by consent)")

    print("\nDone")


if __name__ == "__main__":
    asyncio.run(main())
