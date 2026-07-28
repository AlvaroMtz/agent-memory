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
from agent_memory import create_client
from agent_memory.context import MemoryContext

# Create a client with in-memory backend
client = create_client()

# Remember something from a conversation
context = MemoryContext(
    agent_id="assistant-1",
    user_id="user-1",
    conversation_id="conv-1",
    tenant_id="t1",
)
result = await client.remember("The user prefers dark mode", context)

# Retrieve relevant memories
results = await client.retrieve(
    query="dark mode preferences",
    context=context,
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
agent-memory/
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
- [Memory Lab UI](docs/lab.md) — FastAPI-based development tool
- [Threat Model](docs/threat-model.md)
- [Architecture Decision Records](docs/adr/)

## License

MIT