"""Custom provider example — demonstrate plugging in a custom MemoryExtractor.

Run: python examples/custom_provider/custom_provider.py
"""

import asyncio

from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.ports.extractor import MemoryExtractor
from agent_memory.providers.in_memory_backend import InMemoryBackend


class SimpleExtractor(MemoryExtractor):
    """A trivial extractor that produces a single preference per message."""

    async def extract(
        self,
        messages: list[dict],
        subject_id: str,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        for msg in messages:
            content = msg.get("content", "")
            normalized = content.lower()
            if "like" in normalized or "prefer" in normalized:
                candidates.append(
                    MemoryCandidate(
                        memory_type="preference",
                        subject_key="topic",
                        predicate="likes" if "like" in normalized else "prefers",
                        value=content,
                        source_message_id=msg.get("id", ""),
                        evidence_text=content,
                        source_role=msg.get("role", "user"),
                        confidence=0.8,
                    )
                )
        return candidates


async def main():
    backend = InMemoryBackend()
    extractor = SimpleExtractor()
    client = MemoryClient(backend, extractor, consent=backend)

    context = MemoryContext(
        tenant_id="default",
        subject_id="user-1",
        actor_id="agent-1",
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
            {"id": "m1", "role": "user", "content": "I like dark mode."},
            {"id": "m2", "role": "user", "content": "I prefer short responses."},
        ]
        result = await client.remember(context=context, messages=messages)
        print(f"Persisted {result.count} memories:")
        for m in result.memories:
            print(f"  id={m.id}  type={m.memory_type}  pred={m.predicate}")

        # Retrieve
        retrieval = await client.retrieve("dark mode", context)
        print(f"\nRetrieved {len(retrieval.results)} memory/memories for 'dark mode'")

    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
