#!/usr/bin/env python3
"""Functional example: agent with long-term memory via LangChain integration.

This example demonstrates:
1. Setting up an InMemoryBackend
2. Creating a MemoryMiddleware with LangChain integration
3. Running a simulated conversation
4. Extracting memories from the conversation
5. Retrieving memories for future context

Run with:
    python examples/langchain_agent/agent.py

Requires: langchain (optional extra) or mock objects only.
"""

from __future__ import annotations

import asyncio
import logging

from agent_memory.langchain.middleware import MemoryMiddleware, MemoryMiddlewareConfig
from agent_memory.providers.fake_extractor import FakeExtractor
from agent_memory.providers.in_memory_backend import InMemoryBackend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the agent with memory example."""

    # ── 1. Setup ──────────────────────────────────────────────────────────

    # Create the backend (in production, use PostgreSQLBackend)
    backend = InMemoryBackend()
    await backend.initialize()

    # Create the extraction pipeline (in production, use LangChainExtractor)
    extractor = FakeExtractor()

    # Configure the middleware
    config = MemoryMiddlewareConfig(
        enabled=True,
        auto_extract=True,
        top_k=8,
        max_tokens=1200,
    )

    # Create the middleware
    middleware = MemoryMiddleware(
        backend=backend,
        extractor=extractor,
        config=config,
    )

    # ── 2. Simulated conversation ─────────────────────────────────────────

    # Simulated conversation messages
    messages = [
        {"id": "msg-1", "role": "user", "content": "I love coffee. It's my favorite drink."},
        {"id": "msg-2", "role": "assistant", "content": "Great! I'll remember that."},
        {"id": "msg-3", "role": "user", "content": "I work at Acme Corp as a software engineer."},
        {
            "id": "msg-4",
            "role": "assistant",
            "content": "Nice! I'll note that you work at Acme Corp.",
        },
        {"id": "msg-5", "role": "user", "content": "I prefer Python over Java for development."},
        {"id": "msg-6", "role": "assistant", "content": "Got it. Python it is."},
    ]

    tenant_id = "demo-tenant"
    subject_id = "demo-user"
    actor_id = "demo-agent"
    purpose = "demo"

    # ── 3. Before model hook — retrieve context ───────────────────────────

    logger.info("=== Step 1: Retrieve context before model call ===")

    context_kwargs = await middleware.before_model_hook(
        tenant_id=tenant_id,
        subject_id=subject_id,
        actor_id=actor_id,
        purpose=purpose,
        messages=messages,
    )

    memory_ctx = context_kwargs.get("_memory_context", {})
    retrieved = memory_ctx.get("retrieved_memories", [])
    logger.info("Retrieved %d memories for context", len(retrieved))

    # ── 4. After agent hook — extract memories ────────────────────────────

    logger.info("=== Step 2: Extract memories after agent response ===")

    candidates = await middleware.after_agent_hook(
        response="Response from agent",
        tenant_id=tenant_id,
        subject_id=subject_id,
        actor_id=actor_id,
        purpose=purpose,
        messages=messages,
    )

    logger.info("Extracted %d memory candidates", len(candidates))

    for i, candidate in enumerate(candidates):
        logger.info(
            "  Candidate %d: %s(%s=%s) confidence=%.2f",
            i + 1,
            candidate.memory_type,
            candidate.predicate,
            candidate.value,
            candidate.confidence,
        )

    # ── 5. Retrieve memories for next turn ────────────────────────────────

    logger.info("=== Step 3: Retrieve memories for next conversation turn ===")

    from agent_memory.application.retrieve import retrieve as app_retrieve

    retrieval_result = await app_retrieve(
        tenant_id=tenant_id,
        subject_id=subject_id,
        backend=backend,
        max_tokens=1200,
    )

    logger.info("Total memories stored: %d", retrieval_result.total_count)
    for r in retrieval_result.results:
        logger.info("  - %s: %s = %s", r.memory_type, r.predicate, r.value)

    # ── 6. Cleanup ────────────────────────────────────────────────────────

    await backend.close()

    logger.info("=== Example complete ===")


if __name__ == "__main__":
    asyncio.run(main())
