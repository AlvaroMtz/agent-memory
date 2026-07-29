"""Multi-tenant isolation example — two tenants cannot see each other's memories.

Run: python examples/multi_tenant/multi_tenant.py
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

    tenant_a = MemoryContext(
        tenant_id="tenant-a",
        subject_id="user-1",
        actor_id="assistant-1",
        purpose="general",
    )
    tenant_b = MemoryContext(
        tenant_id="tenant-b",
        subject_id="user-1",
        actor_id="assistant-1",
        purpose="general",
    )

    async with client:
        for context in (tenant_a, tenant_b):
            await client.grant_consent(
                context,
                memory_types=["preference"],
                sensitivity="public",
                allow_read=True,
                allow_write=True,
            )
        messages_a = [
            {"id": "msg-1", "role": "user", "content": "Prefiero respuestas cortas."},
        ]
        messages_b = [
            {"id": "msg-1", "role": "user", "content": "Prefiero respuestas largas."},
        ]

        result_a = await client.remember(context=tenant_a, messages=messages_a)
        print(f"Tenant A remembered {result_a.count} memories")

        result_b = await client.remember(context=tenant_b, messages=messages_b)
        print(f"Tenant B remembered {result_b.count} memories")

        # Each tenant retrieves — no overlap
        r_a = await client.retrieve("respuestas", tenant_a)
        print(f"\nTenant A sees {len(r_a.results)} results")
        for mem in r_a.results:
            print(f"  {mem.predicate}: {mem.value}")

        r_b = await client.retrieve("respuestas", tenant_b)
        print(f"Tenant B sees {len(r_b.results)} results")
        for mem in r_b.results:
            print(f"  {mem.predicate}: {mem.value}")

    print("\nDone")


if __name__ == "__main__":
    asyncio.run(main())
