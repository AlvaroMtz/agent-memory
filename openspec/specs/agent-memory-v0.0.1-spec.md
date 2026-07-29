# Specification: agent-memory v0.0.1

## Acceptance Criteria

### AC-1: Multi-tenant Isolation
- [ ] Two tenants with the same `subject_id` produce independent memory stores.
- [ ] Cross-tenant read returns zero results.
- [ ] Cross-tenant write is blocked by RLS and application layer.
- [ ] Cross-tenant update is blocked.
- [ ] Cross-tenant delete is blocked.
- [ ] Operations without `tenant_id` are denied.
- [ ] `tenant_id` provided by model/tool content is rejected.
- [ ] PostgreSQL RLS is `FORCE`d.
- [ ] Execution role is not table owner and has no `BYPASSRLS`.
- [ ] Tenant context is set via `SET LOCAL` per transaction.

### AC-2: Consent
- [ ] No consent → no write, no retrieve.
- [ ] Write-only consent → no retrieve.
- [ ] Read-only consent → no write.
- [ ] Expired consent → operations denied.
- [ ] Revoked consent blocks reads immediately.
- [ ] Every memory stores the consent ID under which it was created.
- [ ] Consent is versioned (not a boolean).
- [ ] Consent grants specify: purpose, allow_write, allow_read, allowed_memory_types, allowed_sensitivity, retention_days, expires_at.

### AC-3: Hallucination Control / Extraction
- [ ] Only `user` and explicit `trusted_tool` messages are extracted.
- [ ] `assistant`, `system`, `developer` messages are never extracted.
- [ ] Retrieved memories are never re-extracted.
- [ ] `evidence_text` must appear literally in the source message.
- [ ] `source_message_id` must reference an existing message.
- [ ] `confidence` below threshold → candidate rejected.
- [ ] `explicitly_stated` must be `true`.
- [ ] Candidates without evidence are rejected.
- [ ] The extractor does not determine `tenant_id`.

### AC-4: Evidence & Versioning
- [ ] Every active memory has verifiable evidence.
- [ ] Evidence text is a literal substring of the source.
- [ ] Updates create new versions (append-only).
- [ ] Previous versions are never overwritten.
- [ ] Superseded memories have `supersedes_memory_id`.
- [ ] Version numbers are monotonic per memory.
- [ ] Memory record stores: memory_type, subject_key, predicate, status, current_version.

### AC-5: Contradiction Resolution
- [ ] Duplicate candidates are detected and skipped.
- [ ] Explicit preference change supersedes previous preference.
- [ ] Contradictory semantic facts with equal authority go to `pending_review`.
- [ ] Ambiguous candidates go to `pending_review`.
- [ ] Candidates without valid evidence are `rejected`.
- [ ] Each version stores `supersedes_memory_id`.

### AC-6: Hybrid Retrieval
- [ ] Structured filter by memory_type, predicate, status.
- [ ] Vector similarity search.
- [ ] Lexical (full-text) search.
- [ ] Score fusion from vector + lexical matches.
- [ ] Revoked, expired, superseded memories excluded.
- [ ] Consent applied before returning results.
- [ ] Sensitivity filter applied.
- [ ] Token budget enforced.
- [ ] Each result includes score breakdown.

### AC-7: Security / Protection
- [ ] No memory value is ever concatenated to system prompt directly.
- [ ] Allowlist-based preference predicates only.
- [ ] Prompt injection via memory content does not modify: tools, permissions, tenant, system instructions, credentials, guardrails.
- [ ] Malicious memory content stored safely.
- [ ] Rendered as untrusted data, not as instructions.

### AC-8: Encryption
- [ ] Encrypted: full memory value, evidence text, searchable summaries.
- [ ] Noop provider → error in production mode.
- [ ] Encryption keys external to the package.
- [ ] Decrypted content never logged.
- [ ] Encryption provider interface: encrypt(plaintext, context) → EncryptedPayload, decrypt(payload, context) → bytes.

### AC-9: Audit
- [ ] Every write and retrieval is logged.
- [ ] Audit events include: action, tenant_id, actor_id, subject_id (hashed), timestamp, outcome.
- [ ] Secrets and decrypted content never logged.
- [ ] Denied operations are audited.
- [ ] Audit log is append-only.

### AC-10: Evaluation & Gates
- [ ] Extraction precision >= 0.95.
- [ ] Evidence exact-match = 1.00.
- [ ] Retrieval Precision@5 >= 0.80.
- [ ] Retrieval Recall@5 >= 0.80.
- [ ] Core policy test coverage >= 0.95.
- [ ] Global coverage >= 0.85.
- [ ] cross_tenant_leakage = 0.
- [ ] unauthorized_read/write/update/delete = 0.
- [ ] revoked_memory_retrieval = 0.
- [ ] instruction/tool/permission_escalation = 0.
- [ ] secretos detectados en logs = 0.

### AC-11: Memory Lab
- [ ] Runs via `agent-memory lab` or `docker compose up`.
- [ ] Simulates conversations with user/assistant/trusted_tool messages.
- [ ] Shows extraction candidates with evidence.
- [ ] Shows contradiction detection.
- [ ] Shows retrieval results with score breakdown.
- [ ] Consent grant/revoke UI.
- [ ] Adversarial multi-tenant testing panel.
- [ ] Prompt injection testing panel.
- [ ] Audit timeline viewer.
- [ ] Dataset evaluation runner with reports (JSON, JUnit, HTML).

### AC-12: CLI Complete
- [ ] `agent-memory init`, `migrate`, `doctor`.
- [ ] `agent-memory lab`, `lab seed`, `lab reset`.
- [ ] `agent-memory scenario run`.
- [ ] `agent-memory eval run`, `eval report`.
- [ ] `agent-memory consent grant/revoke/list`.
- [ ] `agent-memory memory list/inspect/forget`.
- [ ] `agent-memory security check`.
- [ ] `agent-memory release check`.

### AC-13: Plugin Architecture
- [ ] MemoryBackend, MemoryExtractor, EmbeddingProvider, EncryptionProvider interfaces defined.
- [ ] Entry point discovery via Python `entry_points`.
- [ ] Contract tests for each plugin interface.
- [ ] Deterministic/fake providers bundled.
- [ ] AES-GCM encryption + NOOP for dev.

### AC-14: Datasets
- [ ] At minimum: extraction, retrieval, multi-tenant, consent, contradictions, prompt injection suites.
- [ ] YAML/JSONL format validated via Pydantic.
- [ ] Each scenario defines: context, consent, messages, expected extraction, expected persistence, queries, audit events.
- [ ] Versioned in-repo under `datasets/`.
- [ ] Runnable via `agent-memory scenario run`.

### AC-15: Production Hardening
- [ ] Production mode forbids: noop encryption, fake providers, RLS disabled.
- [ ] Production mode requires: TLS, consent deny default, non-owner DB role, FORCE RLS.
- [ ] `agent-memory doctor` validates all production requirements.
- [ ] Configuration validation at startup.