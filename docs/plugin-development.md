# Plugin Development

External plugins implement the public ports under `agent_memory.ports`.

Supported plugin categories:

- `MemoryBackend`
- `MemoryExtractor`
- `EmbeddingProvider`
- `EncryptionProvider`
- `ConsentProvider`
- `ConflictResolver`
- `TelemetryProvider`

Entry points are declared in `pyproject.toml`, for example:

```toml
[project.entry-points."agent_memory.extractors"]
rules = "agent_memory.providers:RuleBasedExtractorFactory"
```

Plugins must pass the contract tests before being advertised as compatible.
Security-sensitive plugins must fail closed when required context, consent or
key material is missing.
