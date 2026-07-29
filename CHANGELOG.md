# Changelog

## v0.0.1 (2026-07-28)

### Features

- **Memory Domain Model**: MemoryRecord, MemoryVersion, ConsentRecord, AuditEvent with Pydantic v2 strict validation
- **Port Interfaces**: MemoryBackend, ConsentProvider, EmbeddingProvider, MemoryExtractor, ConflictResolver, EncryptionProvider, TelemetryProvider
- **Deterministic Providers**: InMemoryBackend, DeterministicEmbeddingProvider, FakeExtractor, RuleBasedExtractor, NoopEncryptionProvider
- **PostgreSQL Backend**: SQLAlchemy async models (4 tables), Alembic migrations, RLS policies, async session factory, repository pattern
- **Consent & Security**: ConsentService (grant/revoke/check), ForgetService (GDPR erasure), AES-256-GCM encryption, AuditService, PII/secret redaction
- **Extraction Pipeline**: message filtering, role validation, candidate extraction, evidence validation, scoring with boost/penalty
- **Retrieval Pipeline**: vector search, lexical search, score fusion (4-component weighted), consent filter, token budget
- **Memory Lab**: FastAPI web UI with conversation simulation, extraction inspection, retrieval, consent management, audit log
- **LangChain Integration**: MemoryMiddleware (before/after model hooks), ContextAdapter, BaseStoreAdapter, tools integration
- **CLI**: agent-memory init, remember, retrieve, serve, eval commands
- **MemoryClient**: High-level async facade with SyncMemoryClient wrapper
- **OpenTelemetry**: Tracing spans and metrics with no-op fallback
- **Evaluation Framework**: Dataset schema (YAML/JSON), scenario runner, reporters (JSON, JUnit XML, HTML)
- **Configuration**: Pydantic-settings based (env vars, YAML, CLI)

### Testing

- 257 unit, contract, integration, security, and property tests across all modules
- Contract test suites for backend, embedder, and extractor ports
- Hypothesis property-based tests for consent and encryption

### Infrastructure

- Docker Compose for PostgreSQL + Memory Lab
- CI matrix (Python 3.11, 3.12, 3.13) with lint, test, migration, build, example, and dataset evaluation jobs
- Release gates script: import check, test pass, CLI works, migration runs, build succeeds