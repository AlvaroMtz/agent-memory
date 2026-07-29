# Architecture

`agent-memory` follows a ports-and-adapters architecture.

## Layers

- **Domain**: memory records, immutable versions, candidates, evidence,
  consent, retrieval results and audit events. This layer must not depend on
  LangChain, PostgreSQL, OpenTelemetry, FastAPI or external LLM providers.
- **Application services**: remember, retrieve, forget, consent and audit
  orchestration. This is where fail-closed policy is enforced.
- **Ports**: backend, extractor, embedder, encryption, consent, conflict and
  telemetry protocols.
- **Adapters**: in-memory test backend, PostgreSQL backend, deterministic
  providers, crypto providers, CLI, LangChain integration and Memory Lab.

## Security boundaries

The public `MemoryClient` is the main security boundary. It requires a
`MemoryContext` supplied by the host application, never by model output.

The minimum sequence for writes is:

1. Validate context.
2. Verify write consent.
3. Extract only from eligible roles.
4. Validate literal evidence.
5. Filter by consent type and sensitivity.
6. Persist record and immutable version.
7. Audit the operation.

The minimum sequence for reads is:

1. Validate context.
2. Verify read consent before search.
3. Retrieve only active, non-expired, non-revoked memories.
4. Apply consent and sensitivity filters.
5. Return structured data with scoring details.
6. Audit retrieval metadata, not decrypted content.
