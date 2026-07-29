# ADR-001: Memory Model

**Status:** Accepted  
**Date:** 2026-07-28  
**Deciders:** agent-memory contributors

## Context

The system needs a memory model that supports:
- Governed long-term storage of agent-learned information
- Versioned updates (memories can be corrected)
- Consent-based access control
- Multi-tenant isolation
- GDPR compliance (right to erasure)

## Decision

### MemoryRecord as Aggregate Root

Each memory is represented by a `MemoryRecord` (the aggregate root) with one or more `MemoryVersion` snapshots:

- **MemoryRecord**: mutable metadata (status, current version pointer)
- **MemoryVersion**: immutable snapshot (value, confidence, source, evidence)

### Memory Schema

Every memory has:
- `tenant_id` / `subject_id` / `purpose` — ownership and scope
- `memory_type` — preference, semantic, episodic, procedural, relationship
- `subject_key` / `predicate` — structured key-value semantics
- `status` — candidate → pending_review → active → superseded/revoked
- `confidence` — 0.0 to 1.0 float
- `sensitivity` — public, internal, sensitive, critical
- `source_type` — user_explicit, agent_inference, conversation, trusted_tool, system

### Consent Model

Consent is per-subject with scoped `memory_types` and `sensitivity` levels. Consent records are stored separately from memories and checked at retrieval time.

### Audit Trail

All write operations produce an `AuditEvent` with:
- Action type (create, update, grant, revoke, erase)
- Actor identity
- Target identifiers
- Timestamp (UTC)

## Consequences

- **Positive**: Clear separation of concerns between memory storage, consent, and audit
- **Positive**: Version history enables rollback and diff analysis
- **Positive**: Tenant isolation at the data model level enables multi-tenant deployment
- **Negative**: Retrieval requires joining memory records with their current version
- **Negative**: Consent checks add latency to retrieval (mitigated by in-memory caching layer planned for v0.2.0)