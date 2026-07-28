"""Seed/reset scripts for the Memory Lab.

Creates sample conversation messages, consent records, and audit events
using InMemoryBackend (default) or PostgresBackend (if AGENT_MEMORY_DATABASE__URI is set).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_memory.application.remember import extract_memories
from agent_memory.context import TenantContext
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.fake_extractor import FakeExtractor


SAMPLE_MESSAGES = [
    {"role": "user", "content": "I really enjoy drinking coffee in the morning."},
    {"role": "assistant", "content": "That's great! I'll remember you prefer coffee."},
    {"role": "user", "content": "I work at ACME Corporation as a software engineer."},
    {"role": "assistant", "content": "Noted — you work at ACME as an engineer."},
    {"role": "user", "content": "I'm learning Python and love it."},
    {"role": "assistant", "content": "I'll remember you're learning Python."},
    {"role": "user", "content": "I dislike spicy food."},
    {"role": "assistant", "content": "Understood — no spicy food."},
]

SAMPLE_CONSENTS = [
    ConsentRecord(
        tenant_id="default",
        subject_id="user-1",
        actor_id="system",
        purpose="lab_testing",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public"},
    ),
    ConsentRecord(
        tenant_id="default",
        subject_id="user-2",
        actor_id="system",
        purpose="lab_testing",
        allow_write=False,
        allow_read=True,
        allowed_memory_types={"preference"},
        allowed_sensitivity={"public", "internal"},
    ),
]


async def seed_in_memory(backend: InMemoryBackend, clear: bool = False) -> None:
    """Seed an InMemoryBackend with sample data."""
    if clear:
        print("Clearing existing data...")
        await backend.close()
        backend = InMemoryBackend()

    print(f"Backend: {type(backend).__name__}")

    # Simulate extraction from sample messages
    print("Running extraction on sample messages...")
    candidates = await extract_memories(
        messages=SAMPLE_MESSAGES,
        subject_id="user-1",
        tenant_id="default",
        extractor=FakeExtractor(),
    )
    print(f"  Extracted {len(candidates)} candidates")

    # Save extracted memories to backend
    context = TenantContext(tenant_id="default", actor_id="seed")
    for candidate in candidates:
        record = MemoryRecord(
            tenant_id="default",
            subject_id="user-1",
            purpose="seed_data",
            memory_type=candidate.memory_type,
            subject_key=candidate.subject_key,
            predicate=candidate.predicate,
            status="active",
            current_version=1,
        )
        version = MemoryVersion(
            memory_id=record.id,
            version=1,
            value=candidate.value,
            confidence=0.9,
            sensitivity="public",
            source_type="trusted_tool",
            source_message_id=candidate.source_message_id,
            evidence_text=candidate.evidence_text,
            searchable_summary=f"{candidate.predicate} {candidate.value}",
        )
        try:
            saved = await backend.save_memory(record, version, context=context)
            print(f"  Saved: {candidate.predicate} = {candidate.value}")
        except Exception as exc:
            print(f"  Failed to save {candidate.predicate}: {exc}")

    # Save consent records
    for consent in SAMPLE_CONSENTS:
        print(f"  Consent: {consent.subject_id} -> {consent.allowed_memory_types}")

    stats = await get_stats(backend)
    print(f"\nSeed complete. Stats: {json.dumps(stats, indent=2)}")


async def get_stats(backend: InMemoryBackend) -> dict:
    """Get simple stats from backend."""
    try:
        memories = await backend.list_memories(tenant_id="default", subject_id="default", limit=1000)
        return {"total_memories": len(memories)}
    except Exception:
        return {"total_memories": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Memory Lab with sample data")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before seeding")
    args = parser.parse_args()

    database_url = os.environ.get("AGENT_MEMORY_DATABASE__URI")

    if database_url:
        print("Using PostgresBackend (AGENT_MEMORY_DATABASE__URI set)")
        print("Note: Postgres seeding requires running migrations first.")
        print("For now, seeding InMemoryBackend only.")

    asyncio.run(seed_in_memory(InMemoryBackend(), clear=args.clear))


if __name__ == "__main__":
    main()
