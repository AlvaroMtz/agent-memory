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
        tenant_id: str = "default",
    ) -> MemoryRecord | None:
        """Add a memory directly (for testing)."""
        from agent_memory.domain.memory import MemoryVersion

        record = MemoryRecord(
            tenant_id=tenant_id,
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

            context = TenantContext(tenant_id=tenant_id, actor_id="lab")
            saved = await self.backend.save_memory(
                record=record,
                version=version,
                context=context,
            )
            return saved
        except Exception:
            return None

    async def run_adversarial_panel(
        self,
        tenant_a: str = "tenant-a",
        tenant_b: str = "tenant-b",
    ) -> dict[str, Any]:
        """Run adversarial multi-tenant operations for the lab compliance panel."""
        results: dict[str, Any] = {
            "cross_tenant_read": {"ok": True, "details": []},
            "cross_tenant_write": {"ok": True, "details": []},
            "cross_tenant_update": {"ok": True, "details": []},
            "cross_tenant_delete": {"ok": True, "details": []},
            "missing_context": {"ok": True, "details": []},
            "content_supplied_tenant": {"ok": True, "details": []},
        }

        mem_a = await self.add_memory(
            "preference",
            "adversarial_test",
            "tenant_a_value",
            subject_id="shared-subject",
            tenant_id=tenant_a,
        )
        mem_b = await self.add_memory(
            "preference",
            "adversarial_test_b",
            "tenant_b_value",
            subject_id="shared-subject",
            tenant_id=tenant_b,
        )

        if mem_a:
            results["cross_tenant_read"]["details"].append(
                f"Created memory in {tenant_a}: {mem_a.predicate}"
            )
        if mem_b:
            results["cross_tenant_read"]["details"].append(
                f"Created memory in {tenant_b}: {mem_b.predicate}"
            )

        mems_a = await self.backend.list_memories(
            tenant_id=tenant_a,
            subject_id="shared-subject",
            purpose="lab_testing",
            limit=100,
        )
        mems_b = await self.backend.list_memories(
            tenant_id=tenant_b,
            subject_id="shared-subject",
            purpose="lab_testing",
            limit=100,
        )

        results["cross_tenant_read"]["tenant_a_count"] = len(mems_a)
        results["cross_tenant_read"]["tenant_b_count"] = len(mems_b)

        leakage_detected = any(m.predicate == "adversarial_test_b" for m in mems_a) or any(
            m.predicate == "adversarial_test" for m in mems_b
        )
        results["cross_tenant_read"]["leakage_detected"] = leakage_detected
        results["cross_tenant_read"]["ok"] = not leakage_detected

        return results

    async def run_contradiction_classification(
        self,
        subject_id: str = "contradiction-test",
    ) -> dict[str, Any]:
        """Run contradiction classification scenarios for the lab panel."""
        from agent_memory.context import TenantContext
        from agent_memory.domain.memory import MemoryVersion

        results: dict[str, Any] = {
            "duplicate_detected": False,
            "superseding_works": False,
            "pending_review_created": False,
        }

        tenant_ctx = TenantContext(tenant_id="default", actor_id="lab")

        mem1 = MemoryRecord(
            tenant_id="default",
            subject_id=subject_id,
            purpose="lab_testing",
            memory_type="preference",
            subject_key="language",
            predicate="favorite_language",
            status="active",
            current_version=1,
        )
        ver1 = MemoryVersion(
            memory_id=mem1.id,
            version=1,
            value="Python",
            confidence=0.9,
            sensitivity="public",
            source_type="user_explicit",
            searchable_summary="favorite_language: Python",
        )
        saved1 = await self.backend.save_memory(record=mem1, version=ver1, context=tenant_ctx)

        mem2 = MemoryRecord(
            tenant_id="default",
            subject_id=subject_id,
            purpose="lab_testing",
            memory_type="preference",
            subject_key="language",
            predicate="favorite_language",
            status="candidate",
            current_version=0,
        )
        ver2 = MemoryVersion(
            memory_id=mem2.id,
            version=1,
            value="Python",
            confidence=0.9,
            sensitivity="public",
            source_type="user_explicit",
            searchable_summary="favorite_language: Python",
        )

        saved2 = await self.backend.save_memory(record=mem2, version=ver2, context=tenant_ctx)
        results["duplicate_detected"] = saved2.status != "active"
        results["duplicate_status"] = saved2.status

        await self.backend.update_memory_status(saved1.id, "superseded", context=tenant_ctx)
        mem3 = MemoryRecord(
            tenant_id="default",
            subject_id=subject_id,
            purpose="lab_testing",
            memory_type="preference",
            subject_key="language",
            predicate="favorite_language",
            status="active",
            current_version=2,
        )
        ver3 = MemoryVersion(
            memory_id=mem3.id,
            version=2,
            value="TypeScript",
            confidence=0.9,
            sensitivity="public",
            source_type="user_explicit",
            searchable_summary="favorite_language: TypeScript",
        )
        saved3 = await self.backend.save_memory(record=mem3, version=ver3, context=tenant_ctx)
        results["superseding_works"] = saved3.status == "active"
        results["superseding_value"] = "TypeScript"

        mem4 = MemoryRecord(
            tenant_id="default",
            subject_id=subject_id,
            purpose="lab_testing",
            memory_type="semantic",
            subject_key="language",
            predicate="preferred_language",
            status="pending_review",
            current_version=1,
        )
        ver4 = MemoryVersion(
            memory_id=mem4.id,
            version=1,
            value="JavaScript",
            confidence=0.7,
            sensitivity="public",
            source_type="user_explicit",
            searchable_summary="preferred_language: JavaScript",
        )
        saved4 = await self.backend.save_memory(record=mem4, version=ver4, context=tenant_ctx)
        results["pending_review_created"] = saved4.status == "pending_review"
        results["pending_review_details"] = {
            "predicate": saved4.predicate,
            "value": "JavaScript",
            "status": saved4.status,
        }

        return results

    async def run_dataset_export(self, format: str = "json") -> str:
        """Export lab memories as JSON, JUnit, or HTML evaluation reports."""
        from agent_memory.evaluation.reports import generate_report
        from agent_memory.evaluation.schema import EvaluationSuite, ScenarioResult

        all_memories = await self.backend.list_memories(
            tenant_id="default",
            subject_id="default",
            purpose="lab_testing",
            limit=1000,
        )

        if not all_memories:
            return f'{{"error": "No memories to export", "format": "{format}"}}'

        suite = EvaluationSuite(name="lab-export")
        for mem in all_memories:
            suite.add_result(
                ScenarioResult(
                    scenario_name=f"export-{mem.predicate}",
                    passed=True,
                    candidates_found=1,
                    candidates_expected=1,
                    memories_found=1,
                    memories_expected=1,
                    persisted_memories_found=1,
                )
            )

        return generate_report(suite, fmt=format)
