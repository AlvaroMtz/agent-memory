"""Basic usage example — persist memory candidates from text.

The RuleBasedExtractor identifies structured preferences and semantic
facts using Spanish-language patterns.

Run: python examples/basic/basic.py
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
        await client.grant_consent(
            context,
            memory_types=["preference"],
            sensitivity="public",
            allow_read=True,
            allow_write=True,
        )
        messages = [
            {"id": "msg-1", "role": "user", "content": "Prefiero respuestas cortas."},
        ]
        result = await client.remember(context=context, messages=messages)
        print(f"Persisted {result.count} memory/memories")
        print(f"  Encrypted: {result.encrypted}")
        if result.audit_id:
            print(f"  Audit ID: {result.audit_id}")
        for m in result.memories:
            print(f"  memory_id={m.id}, type={m.memory_type}, pred={m.predicate}")

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
