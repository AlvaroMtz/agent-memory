# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.0.x   | ✅ Active development |

## Reporting a Vulnerability

Report vulnerabilities to **security@agent-memory.dev**. You should receive a response within 48 hours.

**Do not** open public GitHub issues for security vulnerabilities.

## Security Features

### Encryption
- AES-256-GCM at-rest encryption for sensitive memory values and evidence
- Configurable per-memory sensitivity levels: `public`, `internal`, `sensitive`, `critical`
- Encryption provider interface allows custom implementations

### Consent Management
- Per-subject consent records with fine-grained memory type and sensitivity scopes
- Read-access checks enforced at retrieval time
- Audit trail for all consent grant/revoke operations

### GDPR Compliance
- `ForgetService` provides full erasure with audit trail
- Subject-level erasure removes all memories, versions, and consent records
- Audit events persist the erasure action for compliance

### Audit Logging
- All memory writes, consent changes, and erasure operations are logged
- Configurable log redaction for PII and secret patterns
- Tenant-isolated audit trails

### Data Isolation
- Tenant-scoped operations prevent cross-tenant data access
- Row-Level Security (RLS) in PostgreSQL backend
- Tenant ID enforced at the repository layer

## Threat Model

See [docs/threat-model.md](docs/threat-model.md) for the complete threat model and security architecture.