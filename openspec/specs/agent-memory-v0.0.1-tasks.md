# Tasks: agent-memory v0.0.1

Estimated changed lines: ~4500 (exceeds 400 → chained PRs recommended)

## Phase 1: Domain & Contracts (est. 350 lines)

- [ ] **T1.1**: Create directory structure skeleton
  - Files: `src/agent_memory/__init__.py`, `pyproject.toml`
  - Validation: `pip install -e .` succeeds
- [ ] **T1.2**: Define domain models (MemoryRecord, MemoryVersion, MemoryCandidate, Evidence, ConsentGrant, ConsentRecord, RetrievalResult, AuditEvent)
  - Files: `src/agent_memory/domain/*.py`
  - Validation: Pydantic models instantiable, serializable/deserializable
- [ ] **T1.3**: Define exceptions (MemoryError, TenantIsolationError, ConsentDeniedError, EvidenceValidationError, etc.)
  - File: `src/agent_memory/exceptions.py`
- [ ] **T1.4**: Define MemoryContext with validation
  - File: `src/agent_memory/context.py`
  - Validation: missing fields → error, frozen=True
- [ ] **T1.5**: Define constants (MemoryStatus, MemoryType, Sensitivity, SourceType, automatic preference predicates)
  - File: `src/agent_memory/constants.py`
- [ ] **T1.6**: Define all Port interfaces (backend, extractor, embedder, encryption, consent, conflict, telemetry)
  - Files: `src/agent_memory/ports/*.py`
  - Validation: mypy passes, Protocol classes resolve
- [ ] **T1.7**: Define policy module (consent policies, read policies, write policies)
  - File: `src/agent_memory/domain/policies.py`
- [ ] **T1.8**: Unit tests for domain models, context validation, exceptions, constants
  - Files: `tests/unit/test_domain.py`, `tests/unit/test_context.py`, `tests/unit/test_policies.py`
- [ ] **T1.9**: Dataset format schema (Pydantic models for scenario definition)
  - File: `tests/unit/test_dataset_schema.py`

## Phase 2: Deterministic Providers (est. 300 lines)

- [ ] **T2.1**: DeterministicEmbeddingProvider (hash-based, stable per string, configurable dimensions)
  - File: `src/agent_memory/providers/deterministic_embeddings.py`
- [ ] **T2.2**: FakeExtractor (fixture-based responses)
  - File: `src/agent_memory/providers/fake_extractor.py`
- [ ] **T2.3**: RuleBasedExtractor (regex patterns for demos)
  - File: `src/agent_memory/providers/rule_based_extractor.py`
- [ ] **T2.4**: InMemoryBackend (dict-based, for tests only)
  - File: `src/agent_memory/providers/in_memory_backend.py`
- [ ] **T2.5**: Basic scenario runner (load dataset, run scenario, assert expectations)
  - File: `src/agent_memory/evaluation/runner.py`
- [ ] **T2.6**: Contract tests for MemoryBackend (reusable suite)
  - File: `tests/contract/test_backend.py`
- [ ] **T2.7**: Contract tests for MemoryExtractor
  - File: `tests/contract/test_extractor.py`
- [ ] **T2.8**: Contract tests for EmbeddingProvider
  - File: `tests/contract/test_embedder.py`

## Phase 3: PostgreSQL Backend (est. 800 lines)

- [ ] **T3.1**: SQLAlchemy models for memories, memory_versions, consent, audit_log
  - File: `src/agent_memory/postgres/models.py`
- [ ] **T3.2**: Alembic migration setup (alembic.ini, env.py, first migration)
  - Files: `src/agent_memory/postgres/migrations/`, `alembic.ini`
- [ ] **T3.3**: SQLAlchemy session factory + async engine
  - File: `src/agent_memory/postgres/session.py`
- [ ] **T3.4**: RLS implementation (policies, SET LOCAL context, execution role setup)
  - File: `src/agent_memory/postgres/rls.py`
- [ ] **T3.5**: MemoryRepository (CRUD for memories + memory_versions)
  - File: `src/agent_memory/postgres/repositories.py`
- [ ] **T3.6**: ConsentRepository
  - (same file: repositories.py)
- [ ] **T3.7**: AuditRepository
  - (same file: repositories.py)
- [ ] **T3.8**: PostgresBackend (adapter implementing MemoryBackend port)
  - File: `src/agent_memory/postgres/backend.py`
- [ ] **T3.9**: Integration tests with real PostgreSQL (via testcontainers)
  - Files: `tests/integration/test_postgres.py`, `tests/integration/test_rls.py`
- [ ] **T3.10**: Multi-tenant integration tests (cross-tenant adversarial)
  - File: `tests/integration/test_multi_tenant.py`

## Phase 4: Consent & Security (est. 500 lines)

- [ ] **T4.1**: Consent application service
  - File: `src/agent_memory/application/consent.py`
- [ ] **T4.2**: Forget application service
  - File: `src/agent_memory/application/forget.py`
- [ ] **T4.3**: NoopEncryptionProvider
  - File: `src/agent_memory/crypto/noop.py`
- [ ] **T4.4**: AESGCMEncryptionProvider
  - File: `src/agent_memory/crypto/aes_gcm.py`
- [ ] **T4.5**: Audit logging service
  - File: `src/agent_memory/application/audit.py`
- [ ] **T4.6**: Log redaction (filter secrets before writing)
  - File: `src/agent_memory/telemetry/redaction.py`
- [ ] **T4.7**: Security test suite (cross-tenant leakage, unauthorized operations)
  - File: `tests/security/test_isolation.py`
- [ ] **T4.8**: Property-based tests (Hypothesis: monotonic versions, revoked never returns, etc.)
  - File: `tests/property/test_memory_properties.py`
- [ ] **T4.9**: Consent datasets + scenarios
  - Files: `datasets/consent/*.yaml`

## Phase 5: Extraction & Retrieval (est. 700 lines)

- [ ] **T5.1**: Extraction pipeline (filter messages → validate roles → extract → validate evidence → score)
  - File: `src/agent_memory/application/remember.py`
- [ ] **T5.2**: Retrieval pipeline (structured filters → vector search → lexical search → fusion → rerank → consent check)
  - File: `src/agent_memory/application/retrieve.py`
- [ ] **T5.3**: Contradiction resolution service
  - File: `src/agent_memory/application/contradictions.py`
- [ ] **T5.4**: Retention policy service (expired cleanup, scheduled forget)
  - File: `src/agent_memory/application/retention.py`
- [ ] **T5.5**: LangChainStructuredExtractor (LLM-based structured output)
  - File: `src/agent_memory/providers/langchain_extractor.py`
- [ ] **T5.6**: Extraction metrics (precision, recall, F1, evidence match)
  - File: `src/agent_memory/evaluation/extraction_metrics.py`
- [ ] **T5.7**: Retrieval metrics (Precision@K, Recall@K, MRR, nDCG)
  - File: `src/agent_memory/evaluation/retrieval_metrics.py`
- [ ] **T5.8**: Security metrics (counter-based, zero-tolerance)
  - File: `src/agent_memory/evaluation/security_metrics.py`
- [ ] **T5.9**: Extraction datasets
  - Files: `datasets/extraction/*.yaml`
- [ ] **T5.10**: Retrieval datasets
  - Files: `datasets/retrieval/*.yaml`
- [ ] **T5.11**: Contradiction datasets
  - Files: `datasets/contradictions/*.yaml`
- [ ] **T5.12**: Prompt injection datasets
  - Files: `datasets/prompt_injection/*.yaml`

## Phase 6: Memory Lab (est. 800 lines)

- [ ] **T6.1**: FastAPI app setup (routes, lifespan, dependency injection)
  - File: `src/agent_memory/lab/app.py`
- [ ] **T6.2**: Pydantic schemas for API
  - File: `src/agent_memory/lab/schemas.py`
- [ ] **T6.3**: Lab services (context management, conversation simulation, extraction inspection)
  - File: `src/agent_memory/lab/services.py`
- [ ] **T6.4**: Jinja2 templates (main layout, conversation, extraction, retrieval, consent, audit)
  - Directory: `src/agent_memory/lab/templates/`
- [ ] **T6.5**: Static assets (CSS minimal, HTMX)
  - Directory: `src/agent_memory/lab/static/`
- [ ] **T6.6**: Docker Compose setup (PostgreSQL + lab)
  - File: `docker-compose.yml`
- [ ] **T6.7**: Evaluation report generation (JSON, JUnit XML, HTML)
  - File: `src/agent_memory/evaluation/reports.py`
- [ ] **T6.8**: Seed/reset scripts for lab
  - Files: `scripts/seed_lab.py`

## Phase 7: LangChain Integration (est. 400 lines)

- [ ] **T7.1**: MemoryMiddleware class (before model hook, after agent hook)
  - File: `src/agent_memory/langchain/middleware.py`
- [ ] **T7.2**: Context adapter (extract MemoryContext from LangChain runtime)
  - File: `src/agent_memory/langchain/context.py`
- [ ] **T7.3**: BaseStoreAdapter (LangChain BaseStore compatibility)
  - File: `src/agent_memory/langchain/store_adapter.py`
- [ ] **T7.4**: Tools integration (trusted_tool marking)
  - File: `src/agent_memory/langchain/tools.py`
- [ ] **T7.5**: LangChain integration tests with fake providers
  - File: `tests/integration/test_langchain.py`
- [ ] **T7.6**: LangChain example (functional agent with memory)
  - File: `examples/langchain_agent/README.md` + `examples/langchain_agent/agent.py`

## Phase 8: Packaging & Release (est. 500 lines)

- [ ] **T8.1**: CLI implementation (all subcommands)
  - File: `src/agent_memory/cli/main.py` + `pyproject.toml` scripts
- [ ] **T8.2**: Configuration system (Pydantic settings + YAML + env vars)
  - File: `src/agent_memory/config.py`
- [ ] **T8.3**: MemoryClient with sync facade
  - Files: `src/agent_memory/client.py`, `src/agent_memory/sync_client.py`
- [ ] **T8.4**: OpenTelemetry tracing spans + metrics
  - Files: `src/agent_memory/telemetry/tracing.py`, `src/agent_memory/telemetry/metrics.py`
- [ ] **T8.5**: Release gates (release_check command + threshold config)
  - File: `scripts/release_check.py`
- [ ] **T8.6**: CI configuration (GitHub Actions matrix)
  - File: `.github/workflows/ci.yml`
- [ ] **T8.7**: Documentation (README, SECURITY, CONTRIBUTING, threat model, ADRs)
  - Files: `README.md`, `SECURITY.md`, `CONTRIBUTING.md`, `docs/*.md`
- [ ] **T8.8**: Package build + clean install test
  - Validation: `pip install dist/*.whl` in clean venv succeeds
- [ ] **T8.9**: CHANGELOG.md v0.0.1 entry
  - File: `CHANGELOG.md`
- [ ] **T8.10**: Migration tests (fresh install, upgrade, idempotency, compatibility)
  - File: `tests/migrations/`
- [ ] **T8.11**: Dataset evaluations as CI job
  - Validation: `agent-memory eval run --all` passes in CI
- [ ] **T8.12**: All examples verified in CI
  - Validation: all `examples/*/` run without error

Total tasks: ~55 | Estimated lines: ~4500 | Changed files: ~80+