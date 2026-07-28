"""High-level async MemoryClient facade over backend, extractor, embedder, consent,
encryption, and audit.

The client is the public API boundary — the secure frontier of the system.
All operations go through the full pipeline: consent check → extraction →
encryption → persistence → audit trail.
"""

from __future__ import annotations

import base64
import inspect
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from agent_memory.application.audit import AuditService
from agent_memory.application.remember import extract_memories
from agent_memory.application.retrieve import retrieve
from agent_memory.constants import MemoryStatus, Sensitivity, SourceType
from agent_memory.context import MemoryContext, TenantContext
from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.domain.consent import ConsentRecord, ConsentGrant
from agent_memory.domain.forget import ForgetResult
from agent_memory.domain.memory import MemoryRecord, MemoryVersion
from agent_memory.domain.remember import RememberResult
from agent_memory.domain.retrieval import RetrievalResult
from agent_memory.ports.backend import MemoryBackend
from agent_memory.ports.consent import ConsentProvider
from agent_memory.ports.embedder import EmbeddingProvider
from agent_memory.ports.encryption import EncryptionContext, EncryptionProvider
from agent_memory.ports.extractor import MemoryExtractor

logger = logging.getLogger(__name__)


class MemoryClient:
    """Async high-level facade over the full memory pipeline.

    This is the **public API** and the **security frontier** of the system.
    Every ``remember()`` call:
    1. Checks consent (fail-closed)
    2. Extracts memory candidates via the configured extractor
    3. Encrypts sensitive content if an encryption provider is configured
    4. Persists every candidate as a ``MemoryRecord`` + ``MemoryVersion``
    5. Records an append-only audit event
    6. Returns a ``RememberResult`` with all persisted records

    Use this client in application code that already runs in an async context.
    For synchronous code, use ``SyncMemoryClient`` from ``agent_memory.sync_client``.

    Example::

        async with MemoryClient(backend, extractor, embedder, consent) as client:
            result = await client.remember(context=ctx, messages=[...])
            results = await client.retrieve("coffee", context=ctx)
    """

    def __init__(
        self,
        backend: MemoryBackend,
        extractor: MemoryExtractor | None = None,
        embedder: EmbeddingProvider | None = None,
        consent: ConsentProvider | None = None,
        encryption: EncryptionProvider | None = None,
    ) -> None:
        self._backend = backend
        self._extractor = extractor
        self._embedder = embedder
        self._consent = consent
        self._encryption = encryption
        self._audit = AuditService(backend)

    async def __aenter__(self) -> "MemoryClient":
        if hasattr(self._backend, "initialize"):
            await self._backend.initialize()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if hasattr(self._backend, "close"):
            await self._backend.close()

    # ── remember ───────────────────────────────────────────────────────────────

    async def remember(
        self,
        *,
        context: MemoryContext,
        messages: list[dict[str, Any]],
    ) -> RememberResult:
        """Extract memories from *messages* and persist them.

        Full pipeline: consent check → extraction → optional encryption →
        persistence → audit trail → ``RememberResult``.

        Args:
            context: Memory context with tenant_id, subject_id, actor_id, purpose.
            messages: Conversation messages with id, role, content keys.

        Returns:
            ``RememberResult`` with all created memory records and versions.
        """
        tenant_id = context.tenant_id
        subject_id = context.subject_id
        purpose = context.purpose

        # ── Step 1: consent check (fail-closed) ─────────────────────────────
        consent_record = None
        if self._consent is None:
            logger.info(
                "remember blocked: no consent provider configured for tenant=%s subject=%s purpose=%s",
                tenant_id, subject_id, purpose,
            )
            await self._audit.log_action(
                tenant_id=tenant_id,
                actor_id=context.actor_id,
                action="security.unauthorized_write",
                outcome="denied",
                reason="no consent provider configured for write",
                resource_type="memory",
            )
            return RememberResult(
                candidates=[],
                memories=[],
                versions=[],
                count=0,
                encrypted=bool(self._encryption),
                purpose=purpose,
                tenant_id=tenant_id,
                subject_id=subject_id,
            )

        consent_record = await self._consent.get_active_consent(
            tenant_id=tenant_id,
            subject_id=subject_id,
            purpose=purpose,
        )
        if consent_record is None:
            logger.info(
                "remember blocked: no active consent for tenant=%s subject=%s purpose=%s",
                tenant_id, subject_id, purpose,
            )
            await self._audit.log_action(
                tenant_id=tenant_id,
                actor_id=context.actor_id,
                action="security.unauthorized_write",
                outcome="denied",
                reason="no active consent for write",
                resource_type="memory",
            )
            return RememberResult(
                candidates=[],
                memories=[],
                versions=[],
                count=0,
                encrypted=bool(self._encryption),
                purpose=purpose,
                tenant_id=tenant_id,
                subject_id=subject_id,
            )

        # ── Step 2: extract candidates ──────────────────────────────────────
        if self._extractor is None:
            logger.warning("remember skipped: no extractor configured")
            return RememberResult(
                candidates=[],
                memories=[],
                versions=[],
                count=0,
                encrypted=bool(self._encryption),
                purpose=purpose,
                tenant_id=tenant_id,
                subject_id=subject_id,
            )

        candidates = await extract_memories(
            messages=messages,
            subject_id=subject_id,
            tenant_id=tenant_id,
            extractor=self._extractor,
        )

        allowed_candidates: list[MemoryCandidate] = []
        for candidate in candidates:
            if consent_record.allows_write(candidate.memory_type, candidate.sensitivity):
                allowed_candidates.append(candidate)
            else:
                await self._audit.log_action(
                    tenant_id=tenant_id,
                    actor_id=context.actor_id,
                    action="memory.candidate_rejected",
                    outcome="denied",
                    reason="consent does not allow candidate type/sensitivity",
                    resource_type="candidate",
                    memory_type=candidate.memory_type,
                    details={"predicate": candidate.predicate, "sensitivity": candidate.sensitivity},
                )
        candidates = allowed_candidates

        if not candidates:
            return RememberResult(
                candidates=[],
                memories=[],
                versions=[],
                count=0,
                encrypted=bool(self._encryption),
                purpose=purpose,
                tenant_id=tenant_id,
                subject_id=subject_id,
            )

        # ── Step 3: encrypt sensitive content ───────────────────────────────
        encrypted = self._encryption is not None

        # ── Step 4: persist candidates ──────────────────────────────────────
        memories: list[MemoryRecord] = []
        versions: list[MemoryVersion] = []
        memory_ids: list[UUID] = []
        tenant_ctx = TenantContext(tenant_id=tenant_id, actor_id=context.actor_id)

        for candidate in candidates:
            memory_id = uuid4()
            record = MemoryRecord(
                id=memory_id,
                tenant_id=tenant_id,
                subject_id=subject_id,
                purpose=purpose,
                memory_type=candidate.memory_type,
                subject_key=candidate.subject_key,
                predicate=candidate.predicate,
                status="active",
                current_version=1,
            )

            stored_value: Any = candidate.value
            stored_evidence: str | None = candidate.evidence_text
            if self._encryption is not None:
                encryption_ctx = EncryptionContext(
                    tenant_id=tenant_id,
                    purpose=purpose,
                    key_id="default",
                )
                value_payload = await self._encryption.encrypt(
                    json.dumps(candidate.value, ensure_ascii=False).encode("utf-8"),
                    context=encryption_ctx,
                )
                evidence_payload = await self._encryption.encrypt(
                    candidate.evidence_text.encode("utf-8"),
                    context=encryption_ctx,
                )
                stored_value = {
                    "encrypted": True,
                    "algorithm": value_payload.algorithm,
                    "key_id": value_payload.key_id,
                    "ciphertext": base64.b64encode(value_payload.ciphertext).decode("ascii"),
                    "nonce": base64.b64encode(value_payload.nonce).decode("ascii") if value_payload.nonce else None,
                }
                stored_evidence = json.dumps(
                    {
                        "encrypted": True,
                        "algorithm": evidence_payload.algorithm,
                        "key_id": evidence_payload.key_id,
                        "ciphertext": base64.b64encode(evidence_payload.ciphertext).decode("ascii"),
                        "nonce": base64.b64encode(evidence_payload.nonce).decode("ascii") if evidence_payload.nonce else None,
                    },
                    separators=(",", ":"),
                )

            version = MemoryVersion(
                memory_id=memory_id,
                version=1,
                value=stored_value,
                searchable_summary=f"{candidate.predicate}: {candidate.value}",
                confidence=candidate.confidence,
                sensitivity=candidate.sensitivity or "internal",
                source_type=_infer_source_type(candidate),
                source_message_id=candidate.source_message_id,
                evidence_text=stored_evidence,
                extractor_provider=self._extractor.__class__.__name__ if self._extractor else "unknown",
                extractor_model="",
                extractor_prompt_version="",
                embedding_provider=self._embedder.__class__.__name__ if _can_embed(self._embedder) else "",
                embedding_model="deterministic" if _can_embed(self._embedder) else "",
                embedding=await _embed_text(
                    self._embedder,
                    f"{candidate.predicate} {candidate.value}",
                ),
                consent_id=consent_record.id if self._consent is not None and consent_record else None,
            )

            try:
                saved = await self._backend.save_memory(
                    record, version, context=tenant_ctx,
                )
                memories.append(saved)
                versions.append(version)
                memory_ids.append(memory_id)
            except Exception as exc:
                await self._audit.log_action(
                    tenant_id=tenant_id,
                    actor_id=context.actor_id,
                    action="memory.candidate_rejected",
                    outcome="denied",
                    reason="backend persistence failed",
                    resource_type="candidate",
                    memory_type=candidate.memory_type,
                    details={"predicate": candidate.predicate, "error_type": type(exc).__name__},
                )
                raise

        # ── Step 5: audit ───────────────────────────────────────────────────
        audit_event = await self._audit.log_action(
            tenant_id=tenant_id,
            actor_id=context.actor_id,
            action="memory.activated",
            memory_type=",".join(c.memory_type for c in candidates),
            details={
                "memory_count": len(memories),
                "candidate_count": len(candidates),
                "memory_ids": [str(mid) for mid in memory_ids],
            },
            outcome="allowed",
            resource_type="memory",
            resource_id=str(memory_ids[0]) if memory_ids else None,
        )

        return RememberResult(
            candidates=candidates,
            memories=memories,
            versions=versions,
            count=len(memories),
            audit_id=str(audit_event.id) if hasattr(audit_event, "id") else None,
            encrypted=encrypted,
            purpose=purpose,
            tenant_id=tenant_id,
            subject_id=subject_id,
        )

    # ── retrieve ───────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str | None = None,
        context: MemoryContext | None = None,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        max_tokens: int = 1200,
    ) -> RetrievalResult:
        """Run the full retrieval pipeline.

        Returns a ``RetrievalResult`` with up to *max_tokens* tokens of results.
        """
        if context is None or query is None:
            raise TypeError("retrieve requires query and context")

        filters = dict(filters or {})
        filters.setdefault("purpose", context.purpose)
        if limit is not None:
            filters["limit"] = limit

        result = await retrieve(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            query=query,
            filters=filters,
            backend=self._backend,
            embedder=self._embedder,
            consent=self._consent,
            max_tokens=max_tokens,
        )
        await self._audit.log_action(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            action="memory.retrieved",
            resource_type="memory",
            details={
                "result_count": len(result.results),
                "memory_ids": [str(r.id) for r in result.results],
            },
        )
        return result

    # ── list_memories ──────────────────────────────────────────────────────────

    async def list_memories(
        self,
        context: MemoryContext,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories for a subject, filtered by type and status."""
        return await self._backend.list_memories(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            purpose=context.purpose,
            memory_type=memory_type,
            status=status,
            limit=limit,
            offset=offset,
        )

    # ── forget ─────────────────────────────────────────────────────────────────

    async def forget(
        self,
        memory_id: UUID | None = None,
        context: MemoryContext | None = None,
    ) -> ForgetResult:
        """Soft-delete a memory by ID."""
        if context is None or memory_id is None:
            raise TypeError("forget requires memory_id and context")
        tenant_ctx = TenantContext(tenant_id=context.tenant_id, actor_id=context.actor_id)
        await self._backend.update_memory_status(
            memory_id=memory_id, status="deleted", context=tenant_ctx,
        )
        audit_event = await self._audit.log_action(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            action="memory.deleted",
            resource_type="memory",
            resource_id=str(memory_id),
        )
        return ForgetResult(memory_id=memory_id, forgotten=True, audit_id=str(audit_event.id))

    # ── consent ────────────────────────────────────────────────────────────────

    async def grant_consent(
        self,
        context: MemoryContext,
        *,
        grant: ConsentGrant | None = None,
        memory_types: list[str] | None = None,
        sensitivity: str = "public",
        allow_read: bool = True,
        allow_write: bool = False,
    ) -> ConsentRecord:
        """Grant consent using the context's tenant_id and purpose."""
        if grant is None:
            if memory_types is None:
                raise TypeError("grant_consent requires grant or memory_types")
            grant = ConsentGrant(
                purpose=context.purpose,
                allow_read=allow_read,
                allow_write=allow_write,
                allowed_memory_types=set(memory_types),
                allowed_sensitivity={sensitivity},
            )
        if grant.purpose != context.purpose:
            raise ValueError("Consent grant purpose must match MemoryContext purpose")
        tenant_ctx = TenantContext(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
        )
        record = ConsentRecord(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            actor_id=context.actor_id,
            purpose=grant.purpose,
            allow_write=grant.allow_write,
            allow_read=grant.allow_read,
            allowed_memory_types=grant.allowed_memory_types,
            allowed_sensitivity=grant.allowed_sensitivity,
            retention_days=grant.retention_days,
            expires_at=grant.expires_at,
        )
        if _has_configured_attr(self._backend, "save_consent"):
            saved = await _maybe_await(self._backend.save_consent(record, context=tenant_ctx))
        elif self._consent is not None and _has_configured_attr(self._consent, "grant_consent"):
            saved = await _maybe_await(self._consent.grant_consent(grant, context=tenant_ctx))
        else:
            raise RuntimeError("No consent persistence provider configured")
        await self._audit.log_action(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            action="consent.granted",
            resource_type="consent",
            resource_id=str(saved.id),
        )
        return saved

    async def revoke_consent(
        self,
        subject_id: str | None = None,
        context: MemoryContext | None = None,
        *,
        consent_id: UUID | None = None,
    ) -> ConsentRecord:
        """Revoke consent using the context's tenant_id."""
        if context is None:
            raise TypeError("revoke_consent requires context")
        if consent_id is None:
            if _has_configured_attr(self._backend, "list_consent"):
                records = await _maybe_await(
                    self._backend.list_consent(
                        tenant_id=context.tenant_id,
                        subject_id=subject_id or context.subject_id,
                    )
                )
            elif self._consent is not None and _has_configured_attr(self._consent, "list_consent"):
                records = await _maybe_await(
                    self._consent.list_consent(
                        tenant_id=context.tenant_id,
                        subject_id=subject_id or context.subject_id,
                    )
                )
            else:
                records = []
            active = next((record for record in records if not record.is_revoked()), None)
            if active is None:
                raise ValueError("No active consent found")
            consent_id = active.id
        tenant_ctx = TenantContext(tenant_id=context.tenant_id, actor_id=context.actor_id)
        if _has_configured_attr(self._backend, "revoke_consent"):
            revoked = await _maybe_await(self._backend.revoke_consent(consent_id, context=tenant_ctx))
        elif self._consent is not None and _has_configured_attr(self._consent, "revoke_consent"):
            revoked = await _maybe_await(self._consent.revoke_consent(consent_id, context=tenant_ctx))
        else:
            raise RuntimeError("No consent revocation provider configured")
        memories = await self._backend.list_memories(
            tenant_id=context.tenant_id,
            subject_id=context.subject_id,
            purpose=revoked.purpose,
            limit=10_000,
        )
        for memory in memories:
            await self._backend.update_memory_status(memory.id, "revoked", context=tenant_ctx)
        await self._audit.log_action(
            tenant_id=context.tenant_id,
            actor_id=context.actor_id,
            action="consent.revoked",
            resource_type="consent",
            resource_id=str(consent_id),
            details={"revoked_memories": len(memories)},
        )
        return revoked

    async def check_consent(
        self,
        subject_id: str,
        memory_type: str,
        sensitivity: str,
        context: MemoryContext,
    ) -> bool:
        """Check consent respecting the context's tenant_id and purpose."""
        if self._consent is None:
            return False
        record = await self._consent.get_active_consent(
            tenant_id=context.tenant_id,
            subject_id=subject_id,
            purpose=context.purpose or "general",
        )
        if record is None:
            return False
        return record.allows_read(memory_type, sensitivity)

    # ── stats ──────────────────────────────────────────────────────────────────

    async def get_stats(self, context: MemoryContext) -> dict[str, Any]:
        """Return summary statistics from the backend."""
        try:
            memories = await self._backend.list_memories(
                tenant_id=context.tenant_id,
                subject_id=context.subject_id,
                limit=1000,
            )
            counts: dict[str, int] = {}
            for mem in memories:
                counts[mem.memory_type] = counts.get(mem.memory_type, 0) + 1
            return {"total_memories": len(memories), "by_type": counts}
        except Exception as exc:
            logger.warning("get_stats failed: %s", exc)
            return {"total_memories": 0, "by_type": {}, "error": str(exc)}


# ── helpers ─────────────────────────────────────────────────────────────────────


def _infer_source_type(candidate: MemoryCandidate) -> SourceType:
    """Infer source type from candidate's source_role."""
    role = getattr(candidate, "source_role", "") or ""
    role_lower = role.lower()
    if role_lower == "user":
        return "user_explicit"
    elif role_lower == "trusted_tool":
        return "trusted_tool"
    return "user_explicit"


async def _maybe_await(value: Any) -> Any:
    """Await *value* only when it is awaitable.

    This keeps the public client usable with both real async backends and
    lightweight mocks in tests without changing the production contract.
    """

    if inspect.isawaitable(value):
        return await value
    return value


def _has_configured_attr(obj: Any, name: str) -> bool:
    """Return true for real/configured attributes, false for MagicMock auto attrs."""

    return name in vars(obj) or hasattr(type(obj), name)


def _can_embed(embedder: Any) -> bool:
    """Return whether an embedder has a real/configured embed method."""

    return embedder is not None and _has_configured_attr(embedder, "embed")


async def _embed_text(embedder: Any, text: str) -> list[float] | None:
    """Embed text when a real embedder is configured."""

    if not _can_embed(embedder):
        return None
    return await _maybe_await(embedder.embed(text))
