# Contributing

## Development Setup

```bash
# Clone and install
git clone https://github.com/agent-memory/agent-memory.git
cd agent-memory
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ tests/contract/ tests/integration/ tests/security/ -q

# Run all tests including property-based
pip install hypothesis
pytest tests/ -q
```

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
pip install ruff
ruff check src/
```

Type hints are required for all public APIs. Run mypy:

```bash
pip install mypy
mypy src/
```

## Testing

- **Unit tests** (`tests/unit/`) — test individual components in isolation
- **Contract tests** (`tests/contract/`) — reusable suites validated against all providers
- **Integration tests** (`tests/integration/`) — test provider integrations
- **Security tests** (`tests/security/`) — test encryption, consent, and audit
- **Property tests** (`tests/property/`) — Hypothesis-based property verification

Write tests for all new code. Follow the existing patterns.

## Pull Request Process

1. Ensure all tests pass
2. Run `python scripts/release_check.py` to verify release gates
3. Update CHANGELOG.md with your changes
4. Open a PR against the `main` branch

## Architecture

See [README.md](README.md) for architecture overview and [docs/adr/](docs/adr/) for architecture decisions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.