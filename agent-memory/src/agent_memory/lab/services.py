"""Business logic services for the Memory Lab."""

from __future__ import annotations

from typing import Any

from agent_memory.application.remember import extract_memories
from agent_memory.application.retrieve import retrieve
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord
from agent_memory.domain.memory import MemoryRecord
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.extractor import MemoryExtractor


class LabServices:
    """Services for the Memory Lab UI."""

    def __init__(
        self,
        backend: MemoryBackend,
        extractor: MemoryExtractor,
        embedder: EmbeddingProvider | None = None,
    ):
        self.backend = backend
        self.extractor = extractor
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
                subject_id=agent_id,
                tenant_id="default",
                extractor=self.extractor,
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
                filters={
                    "purpose": "lab_testing",
                    **({"memory_types": memory_types} if memory_types else {}),
                },
                backend=self.backend,
                embedder=self.embedder,
                consent=self.backend,
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
            memories = await self.backend.list_memories(
                tenant_id="default", subject_id="default", limit=1000
            )
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
        try:
            from agent_memory.domain.audit import AuditQuery

            audit_events = await self.backend.query_audit(
                AuditQuery(tenant_id="default", limit=limit)
            )
            return [
                {
                    "id": str(event.id) if hasattr(event, "id") else "unknown",
                    "action": event.action,
                    "timestamp": event.created_at.isoformat(),
                    "details": event.metadata,
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
                tenant_id="default",
                subject_id=subject_id,
                actor_id="lab",
                purpose="lab_testing",
                allow_write=True,
                allow_read=True,
                allowed_memory_types=set(memory_types),
                allowed_sensitivity={sensitivity},
            )
            from agent_memory.context import TenantContext

            await self.backend.save_consent(
                consent, context=TenantContext(tenant_id="default", actor_id="lab")
            )
            return True
        except Exception:
            return False

    async def revoke_consent(
        self,
        subject_id: str,
        memory_type: str | None = None,
    ) -> bool:
        """Revoke consent for a subject."""
        from agent_memory.context import TenantContext

        records = await self.backend.list_consent(tenant_id="default", subject_id=subject_id)
        for record in records:
            await self.backend.revoke_consent(
                record.id, context=TenantContext(tenant_id="default", actor_id="lab")
            )
        return bool(records)

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
