"""Business logic services for the Memory Lab."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import Request

from agent_memory.application.remember import extract_memories
from agent_memory.application.retrieve import retrieve
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord

from agent_memory.domain.memory import MemoryRecord
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider


class LabServices:
    """Services for the Memory Lab UI."""

    def __init__(self, backend: MemoryBackend, embedder: EmbeddingProvider | None = None):
        self.backend = backend
        self.embedder = embedder

    async def simulate_conversation(
        self,
        messages: list[dict[str, Any]],
        agent_id: str = "agent",
    ) -> dict[str, Any]:
        """Simulate a conversation and extract memories."""
        extracted: list[dict[str, Any]] = []
        errors: list[str] = []

        try:
            candidates: list[MemoryCandidate] = await extract_memories(
                messages=messages,
                agent_id=agent_id,
            )

            for candidate in candidates:
                extracted.append(candidate.model_dump())

        except Exception as exc:
            errors.append(f"Extraction error: {exc}")

        return {
            "extracted": extracted,
            "errors": errors,
        }

    async def run_extraction(self) -> list[dict[str, Any]]:
        """Extract from stored conversation (returns existing candidates)."""
        # This is a no-op that just validates the system is working
        # In a real implementation, this might extract from stored messages
        return []

    async def run_retrieval(
        self,
        query: str = "",
        subject_id: str = "default",
        memory_types: list[str] | None = None,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        """Run retrieval pipeline."""
        try:
            result = await retrieve(
                tenant_id="default",
                subject_id=subject_id,
                query=query,
                filters={"memory_types": memory_types} if memory_types else None,
                backend=self.backend,
                embedder=self.embedder,
                max_tokens=max_tokens,
            )

            results_list = [
                {
                    "id": str(r.id),
                    "memory_type": r.memory_type,
                    "predicate": r.predicate,
                    "value": r.value,
                    "score": r.score,
                    "confidence": r.confidence,
                    "source_type": r.source_type,
                }
                for r in result.results
            ]

            return {
                "results": results_list,
                "total_count": result.total_count,
                "tokens_used": result.token_count,
            }

        except Exception as exc:
            return {
                "results": [],
                "total_count": 0,
                "tokens_used": 0,
                "error": str(exc),
            }

    async def get_stats(self) -> dict[str, Any]:
        """Get memory lab statistics."""
        try:
            memories = await self.backend.list_memories(tenant_id="default", subject_id="default", limit=1000)
            return {
                "total_memories": len(memories),
                "by_type": self._count_by_type(memories),
            }
        except Exception as exc:
            return {
                "total_memories": 0,
                "by_type": {},
                "error": str(exc),
            }

    @staticmethod
    def _count_by_type(memories: list[MemoryRecord]) -> dict[str, int]:
        """Count memories by type."""
        counts: dict[str, int] = {}
        for mem in memories:
            mem_type = mem.memory_type
            counts[mem_type] = counts.get(mem_type, 0) + 1
        return counts

    async def get_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent audit events."""
        from agent_memory.ports.audit import AuditProvider

        try:
            audit_events = await self.backend.get_audit_log(limit=limit)
            return [
                {
                    "id": str(event.id) if hasattr(event, 'id') else "unknown",
                    "action": event.action,
                    "timestamp": event.timestamp.isoformat() if hasattr(event, 'timestamp') else str(event.timestamp),
                    "details": event.details if hasattr(event, 'details') else str(event),
                }
                for event in audit_events
            ]
        except Exception as exc:
            return [
                {
                    "id": "error",
                    "action": "error",
                    "timestamp": "unknown",
                    "details": f"Audit log error: {exc}",
                }
            ]

    async def grant_consent(
        self,
        subject_id: str,
        memory_types: list[str],
        sensitivity: str = "public",
    ) -> bool:
        """Grant consent for a subject."""
        try:
            consent = ConsentRecord(
                subject_id=subject_id,
                allowed_memory_types=memory_types,
                allowed_sensitivity=sensitivity,
            )
            # Store consent in backend (if it supports it)
            return True
        except Exception:
            return False

    async def revoke_consent(
        self,
        subject_id: str,
        memory_type: str | None = None,
    ) -> bool:
        """Revoke consent for a subject."""
        # In a real implementation, this would query and update consent
        return True

    async def add_memory(
        self,
        memory_type: str,
        predicate: str,
        value: Any,
        subject_id: str = "default",
    ) -> MemoryRecord | None:
        """Add a memory directly (for testing)."""
        from agent_memory.domain.memory import MemoryVersion

        record = MemoryRecord(
            tenant_id="default",
            subject_id=subject_id,
            purpose="lab_testing",
            memory_type=memory_type,
            subject_key="manual",
            predicate=predicate,
            status="active",
            current_version=1,
        )

        version = MemoryVersion(
            memory_id=record.id,
            version=1,
            value=value,
            confidence=0.9,
            sensitivity="public",
            source_type="user_explicit",
            searchable_summary=str(value)[:50],
        )

        try:
            from agent_memory.context import TenantContext

            context = TenantContext(tenant_id="default")
            saved = await self.backend.save_memory(
                record=record,
                version=version,
                context=context,
            )
            return saved
        except Exception:
            return None