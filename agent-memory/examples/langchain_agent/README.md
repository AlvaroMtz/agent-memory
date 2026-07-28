# LangChain Agent with Memory

This example demonstrates how to integrate `agent-memory` with LangChain to give an agent long-term memory capabilities.

## What it does

- Sets up an in-memory backend for the memory store
- Uses `MemoryMiddleware` to automatically inject memory context before model calls
- Extracts memories from conversation messages after the agent responds
- Retrieves stored memories for future context

## Setup

```bash
cd agent-memory
pip install -e ".[dev]"  # or pip install -e ".[langchain]"
```

## Run the example

```bash
python examples/langchain_agent/agent.py
```

The example simulates a conversation and demonstrates:
1. Retrieving memories before a model call (context injection)
2. Extracting memories after the agent responds (memory creation)
3. Listing all stored memories

## Key components

### MemoryMiddleware

```python
from agent_memory.langchain.middleware import MemoryMiddleware, MemoryMiddlewareConfig

middleware = MemoryMiddleware(
    backend=backend,
    extractor=extractor,
    config=MemoryMiddlewareConfig(
        enabled=True,
        auto_extract=True,
        top_k=8,
        max_tokens=1200,
    ),
)
```

### Context extraction from LangChain

```python
from agent_memory.langchain.context import ContextAdapter

adapter = ContextAdapter()
memory_ctx = adapter.extract_from_runtime(runnable_config)
```

### Store adapter (LangChain BaseStore)

```python
from agent_memory.langchain.store_adapter import AgentMemoryStoreAdapter

store = AgentMemoryStoreAdapter(
    backend=backend,
    namespace="my-agent",
    tenant_id="acme",
    subject_id="user-1",
)

await store.mset([("preference", "language"), ("en")])
await store.mget(["preference", "language"])
```

### Trusted tool decorator

```python
from agent_memory.langchain.tools import trust_tool_output

@trust_tool_output("weather_lookup")
async def weather_lookup(location: str) -> str:
    return "Sunny in London"
```

## Production deployment

For production, replace the `InMemoryBackend` with `PostgresBackend`:

```python
from agent_memory.postgres.backend import PostgresBackendFactory

factory = PostgresBackendFactory(database_url="postgresql+asyncpg://...")
backend = await factory.create()
await backend.initialize()
```

## License

MIT