"""CLI entry point for agent-memory.

Usage::

    agent-memory init          Initialize the memory backend
    agent-memory remember      Run extraction on a conversation (JSON via stdin or --file)
    agent-memory retrieve      Query memory with filters (JSON via stdin or --file)
    agent-memory serve         Start the FastAPI Lab server
    agent-memory eval run      Run evaluation datasets
    agent-memory eval report   Generate evaluation reports
    agent-memory check         Run release gates
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from agent_memory.config import load_config


# ── helpers ──────────────────────────────────────────────────────────────────


def _read_input(ctx: click.Context, filename: str | None) -> str:
    """Read JSON input from stdin or a file."""
    if filename:
        return Path(filename).read_text(encoding="utf-8")
    return click.get_text_stream("stdin").read()


# ── CLI commands ─────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version="0.0.1")
def app() -> None:
    """agent-memory — Governed Long-Term Memory for AI Agents."""


# ── init ─────────────────────────────────────────────────────────────────────


@app.command()
@click.option("--uri", default=None, help="Database URI")
def init(uri: str | None) -> None:
    """Initialize the memory backend."""
    config = load_config()
    if uri:
        config.database.uri = uri

    click.echo(f"Environment: {config.environment}")
    click.echo(f"Database URI: {config.database.uri}")
    click.echo("Backend ready. Run 'agent-memory serve' to start the Lab.")


# ── remember ─────────────────────────────────────────────────────────────────


@app.command()
@click.option("--file", "filename", default=None, help="JSON file with messages")
def remember(file: str | None) -> None:
    """Run extraction on a conversation (JSON from stdin or file).

    Input format::

        [
          {"id": "m1", "role": "user", "content": "I like coffee."},
          {"id": "m2", "role": "assistant", "content": "Great!"}
        ]
    """
    import json as _json
    from agent_memory.providers.in_memory_backend import InMemoryBackend
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor
    from agent_memory.application.remember import extract_memories

    raw = _read_input(click.get_current_context(), file)
    messages = _json.loads(raw)

    asyncio.run(
        extract_memories(
            messages=messages,
            subject_id="cli-user",
            tenant_id="default",
            extractor=RuleBasedExtractor(),
        )
    )


# ── retrieve ─────────────────────────────────────────────────────────────────


@app.command()
@click.option("--file", "filename", default=None, help="JSON file with query params")
def retrieve(file: str | None) -> None:
    """Query memory with filters (JSON from stdin or file).

    Input format::

        {"query": "coffee", "subject_id": "default", "filters": {}}
    """
    import json as _json
    from agent_memory.providers.in_memory_backend import InMemoryBackend
    from agent_memory.application.retrieve import retrieve as retrieve_fn

    params = _json.loads(_read_input(click.get_current_context(), file))

    backend = InMemoryBackend()
    asyncio.run(backend.initialize())

    result = asyncio.run(
        retrieve_fn(
            tenant_id=params.get("tenant_id", "default"),
            subject_id=params.get("subject_id", "default"),
            query=params.get("query", ""),
            filters=params.get("filters"),
            backend=backend,
        )
    )
    click.echo(
        json.dumps(
            {"results": [r.model_dump() for r in result.results], "total": result.total_count},
            indent=2,
        )
    )


# ── serve ────────────────────────────────────────────────────────────────────


@app.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
def serve(host: str, port: int) -> None:
    """Start the FastAPI Lab server."""
    try:
        import uvicorn
    except ImportError:
        click.echo("Error: uvicorn is required. Install with: pip install 'agent-memory[lab]'", err=True)
        sys.exit(1)

    uvicorn.run(
        "agent_memory.lab.app:app",
        host=host,
        port=port,
        log_level="info",
    )


# ── eval ─────────────────────────────────────────────────────────────────────


@app.group()
def eval_group() -> None:
    """Evaluation commands."""


@eval_group.command()
@click.option(
    "--path",
    "path",
    default="datasets",
    help="Path to dataset directory or file",
)
def run(path: str) -> None:
    """Run evaluation datasets."""
    from agent_memory.evaluation.runner import load_dataset, run_suite
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    dataset_path = Path(path)

    if dataset_path.exists():
        if dataset_path.is_dir():
            scenarios = load_dataset(dataset_path)
        else:
            from agent_memory.evaluation.runner import load_scenario
            scenarios = [load_scenario(dataset_path)]
    else:
        click.echo(f"No datasets found at {path}; nothing to run")
        return

    extractor = RuleBasedExtractor()
    suite = asyncio.run(run_suite(scenarios, extractor, suite_name="cli-eval"))

    for result in suite.results:
        status = "PASS" if result.passed else "FAIL"
        click.echo(f"  [{status}] {result.scenario_name}  ({result.duration_ms:.0f}ms)")

    click.echo(f"\nSuite '{suite.name}': {suite.pass_count}/{suite.total_count} passed")


@eval_group.command()
@click.option(
    "--path",
    "path",
    default="datasets",
    help="Path to dataset directory or file",
)
@click.option("--format", "fmt", default="json", help="Report format: json, junit, html")
def report(path: str, fmt: str) -> None:
    """Generate evaluation reports."""
    from agent_memory.evaluation.reports import generate_report
    from agent_memory.evaluation.runner import load_dataset, run_suite
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    dataset_path = Path(path)

    if dataset_path.exists():
        if dataset_path.is_dir():
            scenarios = load_dataset(dataset_path)
        else:
            from agent_memory.evaluation.runner import load_scenario
            scenarios = [load_scenario(dataset_path)]
    else:
        click.echo(f"No datasets found at {path}; generating empty report")
        from agent_memory.evaluation.schema import EvaluationSuite
        suite = EvaluationSuite(name="empty")
        output = generate_report(suite, fmt=fmt)
        click.echo(output)
        return

    extractor = RuleBasedExtractor()
    suite = asyncio.run(run_suite(scenarios, extractor, suite_name="report-eval"))
    output = generate_report(suite, fmt=fmt)
    click.echo(output)


# ── check ────────────────────────────────────────────────────────────────────


@app.command()
@click.option("--strict", is_flag=True, default=False, help="Fail on any warning")
def check(strict: bool) -> None:
    """Run release gates."""
    from agent_memory.evaluation.reports import _assert_release_gates

    try:
        results = _assert_release_gates(strict=strict)
    except Exception as exc:
        click.echo(f"FAIL: {exc}", err=True)
        sys.exit(1)

    for r in results:
        status = "PASS" if r else "WARN"
        click.echo(f"  [{status}] {r or '(warning)'}")

    if strict and not all(results):
        sys.exit(1)


if __name__ == "__main__":
    app()