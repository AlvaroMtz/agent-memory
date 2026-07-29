# Specification: agent-memory v0.0.1 Compliance Hardening

## Global Rule

The system MUST NOT claim v0.0.1 compliance unless every acceptance criterion below is verified by executable tests, scenario datasets, or release gates.

If a guarantee cannot be measured, the release check MUST fail.

---

## AC-1: Release Gates Must Measure Actual Outcomes

- [ ] `agent-memory release check` MUST execute the required security and quality suites, not merely read configured threshold values.
- [ ] Security counters MUST be computed from scenario/test execution results.
- [ ] Release check MUST fail if any required dataset suite is missing.
- [ ] Release check MUST fail if any required scenario has weak expectations that cannot detect failure.
- [ ] Release check MUST fail when `min_results: 0` is used as the only assertion for a positive retrieval/security behavior.
- [ ] Release check MUST fail if coverage data is missing when coverage thresholds are configured.
- [ ] Release check MUST report actual values for every configured gate.

### Scenarios

#### Scenario: configured zero counters are not enough
Given `release-gates.yaml` sets `cross_tenant_leakage: 0`
When the multi-tenant dataset produces a cross-tenant result
Then `agent-memory release check` fails
And the report shows `cross_tenant_leakage > 0`

#### Scenario: weak prompt injection scenario rejected
Given a prompt-injection scenario only asserts `min_results: 0`
When release check validates datasets
Then release check fails with a weak-assertion error

---

## AC-2: Scenario Runner Must Validate the Real Pipeline

- [ ] Expected extraction MUST be compared against candidates accepted/rejected by the application pipeline, not raw `extractor.extract()` output alone.
- [ ] Runner MUST distinguish raw extractor candidates, validated candidates, persisted memories, rejected candidates, and audit events.
- [ ] Runner MUST support expected rejection reasons: missing evidence, invalid role, low confidence, no consent, sensitivity denied, not explicit, cross-tenant denied.
- [ ] Runner MUST support explicit query text and expected predicates/IDs/ranking.
- [ ] Runner MUST support forbidden predicates, forbidden memory IDs, forbidden tenants, and forbidden statuses.
- [ ] Runner MUST support expected security counters.
- [ ] Runner MUST support deterministic seed and include it in JSON/JUnit/HTML reports.

### Scenarios

#### Scenario: extractor returns invalid evidence
Given a fake extractor returns a candidate whose `evidence_text` is absent from the source message
When the scenario runner executes through `MemoryClient.remember`
Then the candidate is rejected
And no active memory is created
And an audit event records the rejection reason

#### Scenario: assistant assertion is ignored
Given an assistant message says "The user prefers Python"
When the scenario runner executes the full pipeline
Then no candidate is accepted
And no memory is persisted

---

## AC-3: Mandatory Dataset Coverage

- [ ] Extraction datasets MUST include every case from the master spec: explicit preference, explicit semantic fact, negation, preference change, ambiguity, assistant invention, trusted tool, untrusted tool, missing evidence, partial evidence, low confidence, inferred sensitive attribute.
- [ ] Retrieval datasets MUST include exact query, paraphrase, irrelevant query, multiple relevant memories, old memory, superseded memory, revoked memory, expired memory, token budget, purpose filter, type filter, sensitivity filter.
- [ ] Multi-tenant datasets MUST include same `subject_id` across tenants, cross-tenant read/write/update/delete, missing tenant, tenant from user content, tenant from tool call, absent RLS context.
- [ ] Consent datasets MUST include no consent, read-only, write-only, type denied, sensitivity denied, expired, revoked, consent version change.
- [ ] Contradiction datasets MUST include duplicate, updated preference, contradictory preferences, semantic conflict with equal authority, trusted tool vs user, ambiguous candidate, temporal change.
- [ ] Prompt-injection datasets MUST include all required injection classes, including injection through evidence and searchable summary.
- [ ] Every required dataset scenario MUST have at least one assertion capable of failing if the relevant guarantee is broken.

### Scenarios

#### Scenario: required case inventory enforced
Given one mandatory prompt-injection case is missing
When `agent-memory release check` runs
Then the release fails before publishing

---

## AC-4: Encrypted Retrieval Must Decrypt or Fail Closed

- [ ] When an encryption provider is configured, persisted memory value, evidence, and sensitive metadata MUST be encrypted at rest.
- [ ] Retrieval MUST decrypt encrypted values before returning `RetrievedMemory.value`.
- [ ] Retrieval MUST decrypt evidence only when explicitly requested by an authorized path.
- [ ] If decryption fails, the affected memory MUST NOT be returned.
- [ ] Decryption failures MUST be audited without logging plaintext, ciphertext, keys, nonces, or evidence.
- [ ] Searchable summaries MUST NOT leak sensitive plaintext in production mode.
- [ ] `NoopEncryptionProvider` MUST be forbidden in production startup and doctor checks.

### Scenarios

#### Scenario: encrypted memory round-trip
Given AES-GCM encryption is configured
And a user explicitly states a preference
When the memory is remembered and retrieved
Then storage contains encrypted payloads
And retrieval returns the plaintext value
And no decrypted content appears in audit logs

#### Scenario: wrong tenant cannot decrypt
Given a memory encrypted with tenant A context
When tenant B attempts retrieval
Then no memory is returned
And an access denied or decrypt denied audit event is recorded

---

## AC-5: LangChain v1 Middleware Must Use MemoryClient End-to-End

- [ ] Optional dependency MUST target LangChain v1-compatible versions.
- [ ] Middleware constructor MUST accept `client=MemoryClient` as the primary integration path.
- [ ] Before model execution, middleware MUST obtain `MemoryContext` from authenticated runtime context only.
- [ ] Before model execution, middleware MUST retrieve through `MemoryClient.retrieve`.
- [ ] Retrieved memories MUST be rendered as controlled untrusted data blocks.
- [ ] Allowlisted preferences MAY be resolved into typed fields only.
- [ ] Memory values MUST NOT be appended directly to the system prompt.
- [ ] After agent execution, middleware MUST call `MemoryClient.remember` to validate, persist, version, encrypt, and audit.
- [ ] Middleware MUST NOT extract from assistant/system/developer/retrieved-memory content.
- [ ] Critical security errors MUST not be swallowed silently.
- [ ] Non-critical degradation MUST be configurable.

### Scenarios

#### Scenario: after-agent persists memory
Given LangChain middleware receives a user message with explicit preference
When `after_agent_hook` runs
Then a memory is persisted through `MemoryClient.remember`
And an audit event records activation or rejection

#### Scenario: malicious memory rendered as data
Given a retrieved memory value says "Ignore previous instructions"
When middleware renders context
Then the string appears only inside an untrusted data block
And tools, tenant, permissions, and system instructions are unchanged

---

## AC-6: Memory Lab Must Demonstrate Required Workflows

- [ ] Memory Lab MUST allow creating/selecting tenant, subject, actor, purpose, consent, policy, extractor, and embedder.
- [ ] Lab MUST simulate conversations with `user`, `assistant`, `trusted_tool`, and untrusted tool roles.
- [ ] Lab MUST show eligible vs ineligible extraction sources.
- [ ] Lab MUST show raw candidates, validation status, evidence, confidence, sensitivity, rejection reason, and policy applied.
- [ ] Lab MUST show contradiction classification, decision, active memory, new candidate, and version history.
- [ ] Lab MUST run retrieval with score breakdown and exclusion reasons.
- [ ] Lab MUST grant/revoke/expire consent and show blocked memories.
- [ ] Lab MUST include adversarial multi-tenant operations: read/write/update/delete/missing context/content-supplied tenant/RLS-absent.
- [ ] Lab MUST include prompt-injection checks proving runtime state is unchanged.
- [ ] Lab MUST show audit timeline without secrets or decrypted content by default.
- [ ] Lab MUST run datasets and export JSON, JUnit, and HTML reports.
- [ ] Lab MUST use PostgreSQL by default when available and deterministic providers by default.

### Scenarios

#### Scenario: same subject in two tenants
Given tenant A and tenant B both use `subject_id=user-1`
When each creates a different preference in Memory Lab
Then each tenant only retrieves its own preference
And the adversarial panel reports zero leakage

---

## AC-7: PostgreSQL/RLS Doctor and Integration Hardening

- [ ] `agent-memory doctor` MUST verify PostgreSQL connectivity and pgvector installation.
- [ ] Doctor MUST verify schema version compatibility.
- [ ] Doctor MUST verify RLS enabled and `FORCE ROW LEVEL SECURITY` on every table.
- [ ] Doctor MUST verify execution role is not table owner.
- [ ] Doctor MUST verify execution role does not have `BYPASSRLS`.
- [ ] Doctor MUST verify tenant and actor context can be set with transaction-local settings.
- [ ] Application MUST fail closed if RLS context cannot be established.
- [ ] Integration tests MUST use real PostgreSQL + pgvector via Testcontainers or CI service.
- [ ] Cross-tenant read, write, update, and delete MUST be tested against PostgreSQL, not only in-memory backend.

### Scenarios

#### Scenario: missing RLS context fails closed
Given a repository operation executes without `agent_memory.tenant_id`
When it reaches PostgreSQL
Then the operation returns no rows or is denied
And the application records a denied audit event

---

## AC-8: Versioning and Contradiction Semantics

- [ ] Logical identity MUST be `(tenant_id, subject_id, purpose, memory_type, subject_key, predicate)`.
- [ ] Duplicate candidate MUST not create a new active memory.
- [ ] Preference changes MUST create a new immutable version or a clearly linked superseding record consistent with documented design.
- [ ] If using superseding records instead of same-record versions, the design MUST explicitly justify the deviation and tests MUST prove append-only history.
- [ ] Semantic contradictions with equal authority MUST become `pending_review`, not active.
- [ ] Ambiguous candidates MUST become `pending_review` or be rejected with a reason.
- [ ] Rejected candidates MUST be auditable and unretrievable.
- [ ] Version numbers MUST be monotonic for same-record versioning.

### Scenarios

#### Scenario: preference update preserves history
Given an active preference `code_language=Python`
When the user explicitly states `code_language=TypeScript`
Then the previous value remains in immutable history
And only TypeScript is active for retrieval
And the new version or superseding record references the previous memory

---

## AC-9: Public API Compatibility

- [ ] `MemoryClient.retrieve` public signature MUST support the master spec keyword shape: `retrieve(*, context, query, limit=None)`.
- [ ] `MemoryClient.forget` MUST support `forget(*, context, memory_id)`.
- [ ] `list_memories` MUST default to active memories unless another status is specified.
- [ ] Public APIs MUST validate `MemoryContext` before backend access.
- [ ] Public APIs MUST not accept tenant/subject/actor/purpose from messages, memories, tools, or model output.

### Scenarios

#### Scenario: documented retrieve signature works
Given a valid context and query
When caller invokes `await client.retrieve(context=context, query="language", limit=5)`
Then retrieval executes successfully
And no positional argument form is required

---

## AC-10: CI Must Expose Independent Quality Jobs

- [ ] CI MUST run ruff, format check, mypy, unit tests, property tests, integration tests, security tests, contract tests, migration tests, dataset evaluations, package build, clean wheel install, dependency scan, secret scan, and release gates.
- [ ] CI MUST test Python 3.11, 3.12, and 3.13.
- [ ] CI MUST test PostgreSQL 16 and 17 with pgvector.
- [ ] CI MUST include visible independent jobs for security isolation, prompt injection, extraction eval, retrieval eval, migration, package build, and release gates.
- [ ] CI MUST not require internet APIs or real LLM provider keys.

### Scenarios

#### Scenario: missing security job blocks compliance
Given CI does not expose a dedicated prompt-injection job
When release readiness is checked
Then compliance is rejected
