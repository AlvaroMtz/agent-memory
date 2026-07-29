# Memory Lab

Memory Lab is the local web UI for exercising the memory system without external
APIs.

Start it with:

```bash
agent-memory serve --host 127.0.0.1 --port 8080
```

The current local lab uses deterministic providers by default:

- `InMemoryBackend`
- `RuleBasedExtractor`

The production target is a PostgreSQL-backed lab that can demonstrate consent,
revocation, RLS behavior, retrieval scoring, prompt-injection handling and audit
events end to end.
