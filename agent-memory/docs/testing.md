# Testing

## Local commands

```bash
make unit
make test
make scenario-check
make release-check
```

`make release-check` first generates a coverage data file and then validates
`release-gates.yaml`. Running `agent-memory release check` directly in strict
mode requires an existing coverage data file; set `AGENT_MEMORY_COVERAGE_FILE`
when the data file is not `.coverage`.

The core suite avoids external APIs. Deterministic providers are used for
extractors and embeddings.

## Required categories

- Unit tests for context, consent, policies, extraction, retrieval, encryption
  and dataset schema.
- Security tests for tenant isolation, consent bypass, revoked memories and
  prompt injection.
- Contract tests for backend, extractor and embedder ports.
- Migration tests for schema compatibility.
- Property tests using Hypothesis.
- Release coverage gate using `coverage.py` data generated before the gate runs.

## Important note

Do not replace PostgreSQL integration tests with mocks for release validation.
Mocked tests are useful for fast feedback, but release gates must include real
PostgreSQL + pgvector checks.
