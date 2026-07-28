# Threat Model

## Assets

- Tenant-scoped memories.
- Consent records.
- Evidence text and source fragments.
- Encryption keys and encrypted payloads.
- Audit trail integrity.
- System prompts, tools and permissions of host agents.

## Non-negotiable assumptions

- Memory content is untrusted input.
- LLM output is not an authorization source.
- Tenant, subject, actor and purpose come from authenticated application
  context.
- Missing context or consent denies the operation.

## Main threats

| Threat | Control |
|---|---|
| Cross-tenant read/write | Mandatory `tenant_id`, repository filters, PostgreSQL RLS + FORCE RLS |
| Consent bypass | Read/write consent checked before extraction, embedding, search or persistence |
| Assistant hallucination becomes memory | Extract only from `user` and `trusted_tool` roles |
| Evidence fabrication | Literal evidence validation against source message |
| Prompt injection from memory | Render memories as untrusted data; allowlist automatic preferences |
| Revoked memory retrieval | Revocation marks memories revoked and retrieval excludes non-active statuses |
| Secret leakage in audit/telemetry | Audit stores metadata only, not decrypted memory values or evidence |
| Production with unsafe providers | Production config rejects noop encryption and fake/rule extractors |

## Current limitations

- PostgreSQL vector ranking is not yet a full pgvector implementation.
- Testcontainers-backed RLS tests are still required before a production release.
