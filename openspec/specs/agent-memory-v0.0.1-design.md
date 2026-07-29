# Design: agent-memory v0.0.1

## Architecture Decision Records

### ADR-001: Hexagonal Architecture (Ports & Adapters)
**Status**: Accepted  
**Context**: El núcleo debe ser framework-agnostic.  
**Decision**: Domain y Application layers NO dependen de LangChain, PostgreSQL, pgvector, OpenAI, FastAPI, ni OpenTelemetry.  
**Consequence**: Framework migration sin cambiar dominio. Contract tests garantizan compatibilidad de adaptadores.

### ADR-002: PostgreSQL + pgvector como backend único en v0.0.1
**Status**: Accepted  
**Context**: Se necesita un backend que soporte almacenamiento relacional, RLS, vector search, full-text search, transacciones.  
**Decision**: PostgreSQL 16/17 + pgvector + SQLAlchemy 2 + Alembic.  
**Consequence**: Un solo backend productivo en v0.0.1. La interfaz `MemoryBackend` permite otros en futuras versiones.

### ADR-003: Row-Level Security como capa obligatoria de aislamiento
**Status**: Accepted  
**Context**: Multi-tenancy debe tener defensa en profundidad.  
**Decision**: 
- `tenant_id` en cada tabla.
- PostgreSQL RLS con `FORCE ROW LEVEL SECURITY`.
- Rol de ejecución NO propietario, SIN `BYPASSRLS`.
- `SET LOCAL agent_memory.tenant_id = ?` en cada transacción.
- Filtro en repositorios como segunda capa.
**Consequence**: Defense in depth. Tests adversariales verifican cada capa.

### ADR-004: Append-Only Versioning
**Status**: Accepted  
**Context**: Trazabilidad forense requiere que ninguna memoria se sobrescriba.  
**Decision**: `memory_versions` es append-only. `memories` tiene `current_version` y `status`.  
**Consequence**: No se puede editar una versión existente. Las actualizaciones crean nuevas versiones.

### ADR-005: Consentimiento como entidad versionada, no booleano
**Status**: Accepted  
**Context**: El consentimiento debe ser granular y auditable.  
**Decision**: `ConsentGrant` con purpose, write/read flags, memory_types, sensitivity, retention_days, expires_at.  
Cada `memory_version` referencia un `consent_id`.  
**Consequence**: Revocar un consentimiento permite identificar todas las memorias afectadas.

### ADR-006: Extracción estructurada con evidencia literal obligatoria
**Status**: Accepted  
**Context**: Prevenir alucinaciones y fuentes no verificables.  
**Decision**: 
- Solo extraer de `user` y `trusted_tool`.
- `evidence_text` debe ser substring literal de la fuente.
- `source_message_id` debe existir.
- Tres extractores: Fake, RuleBased, LangChainStructured.
**Consequence**: Garantía de que toda memoria tiene origen verificable.

### ADR-007: Retrieval híbrido (vectorial + léxico + filtros)
**Status**: Accepted  
**Context**: La recuperación debe ser precisa tanto semántica como por keyword.  
**Decision**: 
- pgvector para similitud coseno.
- PostgreSQL `tsvector`/`tsquery` para búsqueda léxica.
- Weighted score fusion.
- Filtros obligatorios: tenant_id, status, consent, sensitivity.
**Consequence**: Mejor recall que solo vectorial. Más complejidad en ranking.

### ADR-008: Allowlist de predicados para inyección segura al contexto
**Status**: Accepted  
**Context**: Las memorias son contenido no confiable y no deben modificar el system prompt.  
**Decision**: 
- `AUTOMATIC_PREFERENCE_PREDICATES` allowlist.
- Memorias no reconocidas se renderizan como datos no confiables.
- Formato controlado: `ResolvedPreferences` Pydantic model.
**Consequence**: Prompt injection vía memorias no puede escalar a instrucciones, tools, o permisos.

### ADR-009: Cifrado mediante interfaz configurable
**Status**: Accepted  
**Context**: Diferentes despliegues requieren diferentes niveles de cifrado.  
**Decision**: Interfaz `EncryptionProvider` con `encrypt`/`decrypt`.  
Implementaciones: `NoopEncryptionProvider` (dev/tests), `AESGCMEncryptionProvider` (producción).  
**Consequence**: En producción, noop → error de configuración.

### ADR-010: Datasets versionados como parte del release
**Status**: Accepted  
**Context**: La calidad de extracción y recuperación debe medirse reproduciblemente.  
**Decision**: 
- Datasets en YAML/JSONL bajo `datasets/`.
- Validados mediante Pydantic.
- Runner determinista con seed.
- Gates de release evalúan datasets.
**Consequence**: Cada release tiene evidencia medible de calidad.

### ADR-011: CLI como interfaz única de administración
**Status**: Accepted  
**Context**: Necesitamos init, migrate, doctor, lab, scenario, eval, consent, memory, security.  
**Decision**: Typer/Click CLI con subcomandos. `agent-memory` como entry point.  
**Consequence**: Una sola interfaz para administración y desarrollo.

### ADR-012: Memory Lab con FastAPI + server-side templates
**Status**: Accepted  
**Context**: GUI local para testear sin código. Sin requerir React.  
**Decision**: FastAPI + Jinja2 + HTMX minimal. PostgreSQL real mediante Docker.  
**Consequence**: Sin dependencia de toolchain frontend. Fácil de mantener.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    LangChain / LangGraph                      │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              MemoryMiddleware                         │    │
│  │  ┌─────────────┐    ┌─────────────────────────────┐  │    │
│  │  │ Before Model │    │      After Agent            │  │    │
│  │  │ - Get context│    │ - Filter eligible messages  │  │    │
│  │  │ - Check cons │    │ - Extract candidates        │  │    │
│  │  │ - Retrieve   │    │ - Validate evidence         │  │    │
│  │  │ - Apply alist│    │ - Resolve contradictions   │  │    │
│  │  │ - Render ctx │    │ - Persist versions         │  │    │
│  │  └─────────────┘    │ - Audit                     │  │    │
│  │                     └─────────────────────────────┘  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                     MemoryClient                             │
│  remember() | retrieve() | list_memories() | forget()       │
│  grant_consent() | revoke_consent()                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                Application Services                          │
│  RememberService | RetrieveService | ForgetService          │
│  ConsentService | ContradictionService | RetentionService   │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    Domain Layer                              │
│  MemoryRecord | MemoryVersion | MemoryCandidate             │
│  Evidence | ConsentGrant | ConsentRecord                    │
│  MemoryContext | RetrievalResult | AuditEvent               │
│  Policy | ResolvedPreferences                               │
└──────────────┬──────────────┬──────────────┬────────────────┘
               │              │              │
┌──────────────▼──┐ ┌────────▼──────┐ ┌────▼───────────────┐
│   Ports         │ │  Ports        │ │  Ports              │
│ MemoryBackend   │ │ MemoryExtrac. │ │ EncryptionProvider  │
│ ConsentProvider │ │ EmbeddingProv │ │ TelemetryProvider   │
│ RetrievalPolicy │ │ ConflictRes.  │ │                     │
└──────────┬──────┘ └────────┬──────┘ └────┬───────────────┘
           │                 │              │
┌──────────▼──────────────────▼──────────────▼──────────────┐
│                    Adapters                                │
│  PostgreSQL+pgvector | Deterministic | AES-GCM | NOOP    │
│  LangChainExtractor | RuleBasedExtractor | FakeExtractor  │
│  OpenTelemetry | Memory Lab (FastAPI)                     │
└───────────────────────────────────────────────────────────┘
```

## Data Model

### `memories` table
- `id`: UUID PK
- `tenant_id`: TEXT NOT NULL
- `subject_id`: TEXT NOT NULL
- `purpose`: TEXT NOT NULL
- `memory_type`: TEXT CHECK IN ('semantic', 'preference')
- `subject_key`: TEXT NOT NULL
- `predicate`: TEXT NOT NULL
- `status`: TEXT CHECK IN ('candidate', 'pending_review', 'active', 'superseded', 'revoked', 'expired', 'rejected', 'deleted')
- `current_version`: INT NOT NULL DEFAULT 0
- `valid_from`: TIMESTAMPTZ
- `valid_until`: TIMESTAMPTZ
- `created_at`: TIMESTAMPTZ NOT NULL
- `updated_at`: TIMESTAMPTZ NOT NULL

### `memory_versions` table (append-only)
- `id`: UUID PK
- `memory_id`: UUID FK → memories
- `version`: INT NOT NULL
- `value`: JSONB NOT NULL
- `searchable_summary`: TEXT
- `encrypted_value`: BYTEA
- `encrypted_evidence`: BYTEA
- `confidence`: FLOAT NOT NULL
- `sensitivity`: TEXT CHECK IN ('public', 'internal', 'personal', 'sensitive')
- `source_type`: TEXT CHECK IN ('user_explicit', 'trusted_tool', 'imported')
- `source_message_id`: TEXT
- `evidence_text`: TEXT
- `extractor_provider`: TEXT
- `extractor_model`: TEXT
- `extractor_prompt_version`: TEXT
- `embedding_provider`: TEXT
- `embedding_model`: TEXT
- `policy_version`: TEXT
- `consent_id`: UUID FK → consent
- `supersedes_memory_id`: UUID
- `embedding`: vector(n)
- `created_at`: TIMESTAMPTZ NOT NULL

### `consent` table
- `id`: UUID PK
- `tenant_id`: TEXT NOT NULL
- `subject_id`: TEXT NOT NULL
- `actor_id`: TEXT NOT NULL
- `purpose`: TEXT NOT NULL
- `allow_write`: BOOLEAN NOT NULL
- `allow_read`: BOOLEAN NOT NULL
- `allowed_memory_types`: TEXT[] NOT NULL
- `allowed_sensitivity`: TEXT[] NOT NULL
- `retention_days`: INT
- `expires_at`: TIMESTAMPTZ
- `revoked_at`: TIMESTAMPTZ
- `version`: INT NOT NULL DEFAULT 1
- `created_at`: TIMESTAMPTZ NOT NULL
- `updated_at`: TIMESTAMPTZ NOT NULL

### `audit_log` table (append-only)
- `id`: UUID PK
- `tenant_id`: TEXT NOT NULL
- `actor_id`: TEXT NOT NULL
- `action`: TEXT NOT NULL
- `resource_type`: TEXT
- `resource_id`: TEXT
- `subject_id_hash`: TEXT
- `outcome`: TEXT NOT NULL CHECK IN ('allowed', 'denied')
- `reason`: TEXT
- `metadata`: JSONB
- `created_at`: TIMESTAMPTZ NOT NULL

### Indexes
- `memories`: (tenant_id, subject_id, memory_type, predicate, status)
- `memory_versions`: (memory_id, version DESC), pgvector IVFFlat on embedding
- `memory_versions`: GIN tsvector on searchable_summary
- `consent`: (tenant_id, subject_id, purpose)
- `audit_log`: (tenant_id, created_at DESC)

## RLS Policies

```sql
-- memories
CREATE POLICY tenant_isolation ON memories
  FOR ALL
  USING (tenant_id = current_setting('agent_memory.tenant_id')::TEXT);

-- memory_versions
CREATE POLICY tenant_isolation ON memory_versions
  FOR ALL
  USING (memory_id IN (
    SELECT id FROM memories
    WHERE tenant_id = current_setting('agent_memory.tenant_id')::TEXT
  ));

-- consent
CREATE POLICY tenant_isolation ON consent
  FOR ALL
  USING (tenant_id = current_setting('agent_memory.tenant_id')::TEXT);

-- audit_log
CREATE POLICY tenant_isolation ON audit_log
  FOR ALL
  USING (tenant_id = current_setting('agent_memory.tenant_id')::TEXT);
```

## Security Boundaries

```
┌─────────────────────────────────────────────┐
│           Application / Agent                │
│  ┌───────────────────────────────────────┐   │
│  │  MemoryClient                         │   │
│  │  - Valida MemoryContext               │   │
│  │  - tenant_id del contexto auth        │   │
│  │  - Nunca del modelo/tools             │   │
│  └────────────┬──────────────────────────┘   │
│               │                               │
│  ┌────────────▼──────────────────────────┐   │
│  │  Application Services                 │   │
│  │  - Consent check                      │   │
│  │  - Policy enforcement                 │   │
│  │  - Audit logging                      │   │
│  └────────────┬──────────────────────────┘   │
└───────────────┼──────────────────────────────┘
                │
┌───────────────▼──────────────────────────────┐
│  Ports Layer (interfaces)                    │
│  - Backend, Extractor, Embedder, Encryption  │
│  - Consent, Conflict, Telemetry             │
└───────────────┬──────────────────────────────┘
                │
┌───────────────▼──────────────────────────────┐
│  PostgreSQL Adapter                          │
│  - RLS con FORCE                             │
│  - Non-owner role                            │
│  - SET LOCAL tenant_id                       │
│  - Encrypted columns                         │
│  - Transacciones                             │
└──────────────────────────────────────────────┘
```

## Plugin Discovery

```python
# Entry points en pyproject.toml
[project.entry-points."agent_memory.backends"]
postgres = "agent_memory.postgres:PostgresBackendFactory"

[project.entry-points."agent_memory.extractors"]
fake = "agent_memory.providers:FakeExtractorFactory"
rules = "agent_memory.providers:RuleBasedExtractorFactory"
langchain = "agent_memory.providers:LangChainExtractorFactory"

[project.entry-points."agent_memory.embedders"]
deterministic = "agent_memory.providers:DeterministicEmbeddingFactory"

[project.entry-points."agent_memory.encryption"]
noop = "agent_memory.crypto:NoopEncryptionFactory"
aes-gcm = "agent_memory.crypto:AESGCMEncryptionFactory"
```

## Retrieval Scoring Formula

```
final_score = (vector_score * 0.4) + (lexical_score * 0.3) + (recency_score * 0.15) + (confidence_score * 0.15)
```

Where:
- `vector_score`: cosine similarity (0-1)
- `lexical_score`: ts_rank / normalized (0-1)
- `recency_score`: 1 if within 30 days, decays linearly to 0.1 at 365 days
- `confidence_score`: confidence value (0-1)

## Production Configuration Validation

In `environment=production`:
- [ ] encryption_provider != noop
- [ ] database TLS enabled
- [ ] consent.default == deny
- [ ] postgres_rls == true
- [ ] FORCE RLS enabled
- [ ] DB role is not table owner
- [ ] DB role has no BYPASSRLS
- [ ] No fake/rule-based providers as primary
- [ ] All config validated at startup

## Token Budget

Default: 1200 tokens for retrieved memory context.
- If exceeded: truncate lowest-scored results first.
- Each result's token count estimated as: len(searchable_summary) / 4.
- Budget is per-request, not global.