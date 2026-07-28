"""Basic usage example — extract memory candidates from text.

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
    client = MemoryClient(backend, extractor=extractor)

    context = MemoryContext(
        tenant_id="t1",
        subject_id="user-1",
        actor_id="assistant-1",
        purpose="general",
    )

    # The RuleBasedExtractor uses Spanish regex patterns
    candidates = await client.remember("Prefiero respuestas cortas.", context)
    print(f"Extracted {len(candidates)} memory candidate(s):")
    for c in candidates:
        print(f"  type={c.memory_type}, pred={c.predicate}, val={c.value}")
        print(f"      confidence={c.confidence}, source={c.source_message_id}")

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())