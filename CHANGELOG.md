# Changelog

## v0.0.1 (2026-07-28)

Initial release candidate for governed long-term memory with consent,
multi-tenant isolation, evidence validation, encryption, audit, deterministic
evaluation datasets, Memory Lab, and LangChain/LangGraph v1 integration.

### Features

- **Memory Domain Model**: MemoryRecord, MemoryVersion, ConsentRecord, AuditEvent with Pydantic v2 strict validation
- **Port Interfaces**: MemoryBackend, ConsentProvider, EmbeddingProvider, MemoryExtractor, ConflictResolver, EncryptionProvider, TelemetryProvider
- **Deterministic Providers**: InMemoryBackend, DeterministicEmbeddingProvider, FakeExtractor, RuleBasedExtractor, NoopEncryptionProvider
- **PostgreSQL Backend**: SQLAlchemy async models (4 tables), Alembic migrations, RLS policies, async session factory, repository pattern
- **Consent & Security**: ConsentService (grant/revoke/check), ForgetService (GDPR erasure), AES-256-GCM encryption, AuditService, PII/secret redaction
- **Extraction Pipeline**: message filtering, role validation, candidate extraction, evidence validation, scoring with boost/penalty
- **Retrieval Pipeline**: vector search, lexical search, score fusion (4-component weighted), consent filter, token budget
- **Memory Lab**: FastAPI web UI with conversation simulation, extraction inspection, retrieval, consent management, audit log
- **LangChain Integration**: LangChain/LangGraph v1 MemoryMiddleware (before/after model hooks), ContextAdapter, BaseStoreAdapter, tools integration, structured extractor adapter
- **CLI**: agent-memory init, migrate, doctor, lab, scenario, eval, consent, memory, security, and release commands
- **MemoryClient**: High-level async facade with SyncMemoryClient wrapper
- **OpenTelemetry**: Tracing spans and metrics with no-op fallback
- **Evaluation Framework**: Dataset schema (YAML/JSON), scenario runner, reporters (JSON, JUnit XML, HTML)
- **Configuration**: Pydantic-settings based (env vars, YAML, CLI)

### Security and release gates

- Release gates enforce zero security counters for cross-tenant leakage, unauthorized read/write/update/delete, revoked/expired retrieval, instruction/tool/permission escalation, evidence-less activation, and secret logging.
- Deterministic dataset evaluation passes all mandatory suites: extraction, retrieval, consent, multi-tenant, contradictions, and prompt injection.
- PostgreSQL integration uses pgvector, Alembic, Row-Level Security, and FORCE RLS.
- Wheel installation verified in a clean Python 3.12 environment.

### Testing

- 431 unit, contract, integration, security, property, migration, and release-hardening tests across all modules
- Contract test suites for backend, embedder, and extractor ports
- Hypothesis property-based tests for consent and encryption
- Real PostgreSQL + pgvector tests via Testcontainers
- Global coverage release gate: >= 0.85

### Infrastructure

- Docker Compose for PostgreSQL + Memory Lab
- CI matrix (Python 3.11, 3.12, 3.13) with lint, type-check, test, property, contract, migration, security, dataset evaluation, build, dependency scan, and secret scan jobs
- Release gates script: config, required files, dataset inventory, deterministic evaluation, zero security counters, coverage, import, and runtime stub scan
