# agent-memory

**Governed Long-Term Memory for AI Agents.**

`agent-memory` is a Python library that gives AI agents persistent, governed long-term memory with extraction pipelines, hybrid retrieval, consent management, and configurable backends.

## Features

- **Extraction pipeline** — filter messages → validate roles → extract candidates → score → persist
- **Hybrid retrieval** — vector search + lexical search + score fusion + reranking + consent filter
- **Consent management** — grant/revoke per subject, memory type, sensitivity level
- **Multiple backends** — InMemoryBackend (dev/test), PostgreSQL + SQLAlchemy (production)
- **GDPR compliance** — forget service with full erasure audit trails
- **Encryption** — AES-256-GCM at-rest encryption for sensitive memories
- **LangChain integration** — MemoryMiddleware, ContextAdapter, BaseStoreAdapter, tools
- **Memory Lab** — FastAPI web UI for development and debugging
- **CLI** — `agent-memory` command for init, remember, retrieve, serve, eval

## Quick Start

```bash
pip install agent-memory
```

```python
from agent_memory.client import MemoryClient
from agent_memory.context import MemoryContext
from agent_memory.domain.consent import ConsentGrant
from agent_memory.providers.in_memory_backend import InMemoryBackend
from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

backend = InMemoryBackend()
client = MemoryClient(
    backend=backend,
    extractor=RuleBasedExtractor(),
    consent=backend,
)

context = MemoryContext(
    tenant_id="t1",
    subject_id="user-1",
    actor_id="assistant-1",
    purpose="assistant-personalization",
)

await backend.initialize()
await client.grant_consent(
    context=context,
    grant=ConsentGrant(
        purpose="assistant-personalization",
        allow_write=True,
        allow_read=True,
        allowed_memory_types={"preference", "semantic"},
        allowed_sensitivity={"public", "internal", "personal"},
    ),
)

result = await client.remember(
    context=context,
    messages=[
        {"id": "msg-1", "role": "user", "content": "I prefer Python."},
    ],
)

results = await client.retrieve(
    context=context,
    query="Which code language does the user prefer?",
)
for memory in results.results:
    print(f"  {memory.predicate}: {memory.value} (score: {memory.score:.2f})")
```

## Installation

```bash
# Core
pip install agent-memory

# With LangChain integration
pip install "agent-memory[langchain]"

# With Memory Lab web UI
pip install "agent-memory[lab]"

# With encryption support
pip install "agent-memory[crypto]"

# With OpenTelemetry
pip install "agent-memory[otel]"

# Everything
pip install "agent-memory[all]"
```

## Architecture

```
src/agent_memory/
├── domain/          # MemoryRecord, MemoryVersion, ConsentRecord, AuditEvent
├── ports/           # MemoryBackend, ConsentProvider, EmbeddingProvider, etc.
├── providers/       # InMemoryBackend, DeterministicEmbedding, FakeExtractor
├── postgres/        # SQLAlchemy async models, Alembic migrations, RLS
├── crypto/          # AES-256-GCM, Noop encryption providers
├── application/     # Extraction pipeline (remember), Retrieval pipeline (retrieve)
├── langchain/       # MemoryMiddleware, ContextAdapter, BaseStoreAdapter
├── lab/             # FastAPI web UI for development (Memory Lab)
├── eval/            # Evaluation runner, dataset schema, report generators
├── client.py        # High-level async client facade
├── sync_client.py   # Synchronous wrapper
└── cli/             # CLI entry point
```

## Documentation

- [API Reference](https://agent-memory.dev)
- [Memory Lab UI](docs/memory-lab.md) — FastAPI-based development tool
- [Threat Model](docs/threat-model.md)
- [Architecture Decision Records](docs/adr/)

## License

MIT
