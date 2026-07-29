# Design: agent-memory v0.0.1 Compliance Hardening

## Architectural Approach

Keep the existing hexagonal shape. The remediation must strengthen boundaries instead of bypassing them:

```text
LangChain v1 / Memory Lab / CLI / Scenario Runner
        │
        ▼
MemoryClient
        │
        ▼
Application Services
        │
        ▼
Ports
        │
        ▼
Adapters: PostgreSQL, deterministic providers, encryption, telemetry
```

The key design rule: **all product guarantees flow through `MemoryClient` or lower application services**. Tests and scenario runners may inspect internal state, but they must not claim end-to-end compliance by validating a lower-level provider in isolation.

## Decisions

### D1: Release gates validate observed metrics

Release gates will run required suites and compute counters from the resulting execution artifacts. Configured values in `release-gates.yaml` are thresholds only, not evidence.

Tradeoff:
- Pro: prevents false compliance.
- Con: release check becomes slower and requires deterministic fixtures.

### D2: Scenario runner separates raw and accepted candidates

The runner will record:

- raw extractor candidates,
- validated accepted candidates,
- rejected candidates with reasons,
- persisted memory records,
- retrieved memories,
- audit events,
- security counters.

Tradeoff:
- Pro: makes extraction quality and policy enforcement visible.
- Con: requires expanding scenario schema and reports.

### D3: Retrieval owns decryption

Decryption belongs in the retrieval path before returning `RetrievedMemory` to callers. Backend can store encrypted payloads, but application/client layer must return safe plaintext values or exclude the record.

Rules:
- Wrong key/context/tag → exclude memory and audit.
- Never log plaintext/ciphertext/key/nonce.
- Evidence decryption is separate and explicitly authorized.

Tradeoff:
- Pro: callers get consistent API behavior.
- Con: retrieval code must understand encrypted payload envelopes.

### D4: LangChain middleware uses MemoryClient

The middleware should not orchestrate backend/extractor/consent directly. It must depend primarily on `MemoryClient` so it inherits consent, encryption, audit, contradiction, and versioning behavior.

Tradeoff:
- Pro: one security frontier.
- Con: existing constructor usage must be migrated or kept as compatibility wrapper.

### D5: Memory rendering is typed and allowlisted

Introduce a renderer that returns structured output:

```python
ResolvedPreferences(...)
UntrustedMemoryBlock(...)
```

Only predicates in `AUTOMATIC_PREFERENCE_PREDICATES` can become typed preferences. Everything else is rendered as untrusted data.

Tradeoff:
- Pro: prompt-injection guarantees become testable.
- Con: less flexible than raw prompt concatenation, intentionally.

### D6: Memory Lab is a compliance harness, not only a demo UI

Memory Lab must exercise the same service/client paths as production. It may expose manual editing in lab mode, but that path must be visibly marked and excluded from production examples.

Tradeoff:
- Pro: Lab demonstrates guarantees concretely.
- Con: implementation is larger than a simple demo.

### D7: PostgreSQL doctor checks runtime role properties

Doctor must query PostgreSQL metadata to verify:

- extension `vector`,
- migration/schema version,
- RLS enabled,
- FORCE RLS,
- current role ownership,
- `rolbypassrls = false`,
- transaction-local tenant context.

Tradeoff:
- Pro: catches misconfigured deployments.
- Con: requires DB permissions for metadata introspection.

### D8: Versioning model must be made explicit

Preferred implementation: same `MemoryRecord`, append `MemoryVersion` for preference updates, increment `current_version`.

Alternative: create a new `MemoryRecord` with `supersedes_memory_id` and preserve prior record. This is acceptable only if documented as an ADR and all retrieval/history tests prove master-spec-equivalent behavior.

Recommendation: use same-record versioning for direct alignment with the spec.

## Data Model Changes

Potential additions:

- `memory_versions.encrypted_value` or standardized JSON envelope validation.
- `memory_versions.encrypted_evidence` or standardized encrypted evidence envelope.
- `audit_log.outcome`, `audit_log.reason`, `audit_log.resource_type`, `audit_log.resource_id`, `audit_log.request_id` if not already present in model/migration.
- `schema_version` table or Alembic version verification in doctor.

Any migration must include tests for fresh install and compatibility.

## Test Strategy

Tests must be layered:

1. Unit: policies, encryption envelopes, renderers, schema validation.
2. Contract: providers and plugin interfaces.
3. Integration: PostgreSQL/RLS/vector/audit/encryption.
4. Security: cross-tenant, consent, prompt injection, denied operations.
5. Property: monotonic versions, revoked never retrieved, tenant IDs isolated.
6. Scenario datasets: end-to-end deterministic behavior.
7. Release gates: aggregate proof with thresholds.

## Migration Strategy

1. Expand dataset schema while preserving backward compatibility temporarily.
2. Add strict mode to runner and use strict mode in release gates.
3. Implement runtime fixes.
4. Convert all datasets to strict schema.
5. Remove legacy weak scenario compatibility from release path.
