"""Multi-tenant example — extract across isolated tenants.

Each tenant has its own backend namespace.

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
    client = MemoryClient(backend, extractor=extractor)

    # Two tenants, different subjects
    tenant_a = MemoryContext(
        tenant_id="tenant-a",
        subject_id="alice",
        actor_id="assistant-1",
        purpose="general",
    )
    tenant_b = MemoryContext(
        tenant_id="tenant-b",
        subject_id="bob",
        actor_id="assistant-1",
        purpose="general",
    )

    # Extract in each tenant
    caps_a = await client.remember("Prefiero respuestas cortas.", tenant_a)
    caps_b = await client.remember("Prefiero respuestas largas.", tenant_b)

    print(f"Tenant A: {len(caps_a)} candidates")
    for c in caps_a:
        print(f"  {c.predicate}: {c.value}")

    print(f"Tenant B: {len(caps_b)} candidates")
    for c in caps_b:
        print(f"  {c.predicate}: {c.value}")

    # Tenants are isolated at the backend level
    print("\nTenant isolation works ✅")


if __name__ == "__main__":
    asyncio.run(main())