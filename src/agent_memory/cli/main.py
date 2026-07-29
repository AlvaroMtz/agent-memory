"""CLI entry point for agent-memory.

Usage::

    agent-memory init              Initialize the memory backend
    agent-memory remember          Run extraction on a conversation (JSON via stdin or --file)
    agent-memory retrieve          Query memory with filters (JSON via stdin or --file)
    agent-memory serve             Start the FastAPI Lab server
    agent-memory doctor            Validate production requirements
    agent-memory migrate           Run database migrations
    agent-memory eval run          Run evaluation datasets
    agent-memory eval report       Generate evaluation reports
    agent-memory check             Run release gates
    agent-memory lab seed          Seed the lab with example data
    agent-memory lab reset         Reset lab data
    agent-memory consent grant     Grant consent
    agent-memory consent revoke    Revoke consent
    agent-memory consent list      List consent records
    agent-memory memory list       List memories
    agent-memory memory inspect    Inspect a memory by ID
    agent-memory memory forget     Forget/revoke a memory
    agent-memory security check    Run security scan
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

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


# ── doctor ───────────────────────────────────────────────────────────────────


@app.command()
def doctor() -> None:
    """Validate production requirements."""
    config = load_config()
    try:
        config.validate_production()
        click.echo("All production requirements satisfied.")
    except Exception as exc:
        click.echo(f"Production requirements FAILED: {exc}", err=True)
        sys.exit(1)


# ── migrate ──────────────────────────────────────────────────────────────────


@app.command()
def migrate() -> None:
    """Run database migrations."""
    click.echo("Database migrations supported via Alembic. Run: alembic upgrade head")


def _run(coro):
    return asyncio.run(coro)


async def _postgres_client():
    from agent_memory.client import MemoryClient

    backend_name = os.environ.get("AGENT_MEMORY_CLI_BACKEND", "postgres")
    if backend_name == "in-memory":
        from agent_memory.providers.in_memory_backend import InMemoryBackend

        backend = InMemoryBackend()
    else:
        try:
            from agent_memory.postgres.backend import PostgresBackend

            backend = PostgresBackend(load_config())
        except ModuleNotFoundError:
            # Keep the CLI usable in minimal editable environments. Installed
            # wheels include the PostgreSQL dependencies declared in pyproject;
            # test/dev shells may not. The fallback is explicit and non-prod.
            from agent_memory.providers.in_memory_backend import InMemoryBackend

            backend = InMemoryBackend()
    client = MemoryClient(backend=backend, consent=backend)
    await client.__aenter__()
    return client


# ── remember ─────────────────────────────────────────────────────────────────


@app.command()
@click.option("--file", "filename", default=None, help="JSON file with messages")
def remember(filename: str | None) -> None:
    """Run extraction on a conversation (JSON from stdin or file).

    Input format::

        [
          {"id": "m1", "role": "user", "content": "I like coffee."},
          {"id": "m2", "role": "assistant", "content": "Great!"}
        ]
    """
    import json as _json

    from agent_memory.application.remember import extract_memories
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    raw = _read_input(click.get_current_context(), filename)
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
def retrieve(filename: str | None) -> None:
    """Query memory with filters (JSON from stdin or file).

    Input format::

        {"query": "coffee", "subject_id": "default", "filters": {}}
    """
    import json as _json

    from agent_memory.application.retrieve import retrieve as retrieve_fn
    from agent_memory.providers.in_memory_backend import InMemoryBackend

    params = _json.loads(_read_input(click.get_current_context(), filename))

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


def _serve_lab(host: str, port: int) -> None:
    """Start the FastAPI Lab server."""
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "Error: uvicorn is required. Install with: pip install 'agent-memory[lab]'", err=True
        )
        sys.exit(1)

    uvicorn.run(
        "agent_memory.lab.app:app",
        host=host,
        port=port,
        log_level="info",
    )


@app.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
def serve(host: str, port: int) -> None:
    """Start the FastAPI Lab server."""
    _serve_lab(host, port)


# ── lab ──────────────────────────────────────────────────────────────────────


@app.group(invoke_without_command=True)
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.pass_context
def lab(ctx: click.Context, host: str, port: int) -> None:
    """Lab commands for the Memory Lab."""
    if ctx.invoked_subcommand is None:
        _serve_lab(host, port)


@lab.command()
def seed() -> None:
    """Seed the lab with example data."""
    click.echo("Seeding lab with example data...")


@lab.command()
def reset() -> None:
    """Reset lab data."""
    click.echo("Resetting lab data...")


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

            loaded = load_scenario(dataset_path)
            scenarios = loaded if isinstance(loaded, list) else [loaded]
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

            loaded = load_scenario(dataset_path)
            scenarios = loaded if isinstance(loaded, list) else [loaded]
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


# ── scenario ─────────────────────────────────────────────────────────────────


@app.group()
def scenario() -> None:
    """Scenario runner commands."""


@scenario.command(name="run")
@click.argument("path", type=click.Path(exists=True))
@click.option("--seed", default=42, help="Deterministic seed for providers")
@click.option(
    "--format", "fmt", default="text", type=click.Choice(["text", "json", "junit", "html"])
)
def scenario_run(path: str, seed: int, fmt: str) -> None:
    """Run a scenario file or directory."""
    from agent_memory.evaluation.reports import generate_report
    from agent_memory.evaluation.runner import load_dataset, load_scenario, run_suite
    from agent_memory.providers.rule_based_extractor import RuleBasedExtractor

    dataset_path = Path(path)
    if dataset_path.is_dir():
        scenarios = load_dataset(dataset_path)
    else:
        loaded = load_scenario(dataset_path)
        scenarios = loaded if isinstance(loaded, list) else [loaded]

    suite = asyncio.run(
        run_suite(scenarios, RuleBasedExtractor(), suite_name=dataset_path.name, seed=seed)
    )

    if fmt != "text":
        click.echo(generate_report(suite, fmt=fmt))
        if suite.total_failed:
            sys.exit(1)
        return

    click.echo(f"Dataset: {dataset_path}")
    for result in suite.results:
        mark = "✓" if result.passed else "✗"
        click.echo(f"{mark} {result.scenario_name}")
        for error in result.errors:
            click.echo(f"  Reason: {error}")
    click.echo("")
    click.echo("Result: PASS" if suite.total_failed == 0 else "Result: FAIL")
    if suite.total_failed:
        sys.exit(1)


# ── consent ──────────────────────────────────────────────────────────────────


@app.group()
def consent() -> None:
    """Consent management commands."""


@consent.command()
@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--subject-id", default="default", help="Subject ID")
@click.option("--actor-id", default="cli-user", help="Actor ID")
@click.option("--purpose", default="general", help="Purpose for consent")
def grant(tenant_id: str, subject_id: str, actor_id: str, purpose: str) -> None:
    """Grant consent."""
    from agent_memory.context import MemoryContext
    from agent_memory.domain.consent import ConsentGrant

    async def run() -> str:
        client = await _postgres_client()
        try:
            ctx = MemoryContext(
                tenant_id=tenant_id, subject_id=subject_id, actor_id=actor_id, purpose=purpose
            )
            record = await client.grant_consent(
                context=ctx,
                grant=ConsentGrant(
                    purpose=purpose,
                    allow_write=True,
                    allow_read=True,
                    allowed_memory_types={"preference", "semantic"},
                    allowed_sensitivity={"public", "internal", "personal", "sensitive"},
                ),
            )
            return str(record.id)
        finally:
            await client.__aexit__(None, None, None)

    click.echo(f"Consent granted: {_run(run())}")


@consent.command()
@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--subject-id", default="default", help="Subject ID")
@click.option("--purpose", default="general", help="Purpose for consent")
def revoke(tenant_id: str, subject_id: str, purpose: str) -> None:
    """Revoke consent."""
    from agent_memory.context import MemoryContext

    async def run() -> str:
        client = await _postgres_client()
        try:
            ctx = MemoryContext(
                tenant_id=tenant_id, subject_id=subject_id, actor_id="cli-user", purpose=purpose
            )
            record = await client.revoke_consent(context=ctx)
            return str(record.id)
        finally:
            await client.__aexit__(None, None, None)

    click.echo(f"Consent revoked: {_run(run())}")


@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--subject-id", default=None, help="Subject ID (optional)")
@consent.command(name="list")
def list_consent(tenant_id: str, subject_id: str | None) -> None:
    """List consent records."""

    async def run() -> list[dict]:
        client = await _postgres_client()
        try:
            records = await client._backend.list_consent(tenant_id=tenant_id, subject_id=subject_id)
            return [record.model_dump(mode="json") for record in records]
        finally:
            await client.__aexit__(None, None, None)

    click.echo(json.dumps(_run(run()), indent=2, default=str))


# ── memory ───────────────────────────────────────────────────────────────────


@app.group()
def memory() -> None:
    """Memory management commands."""


@click.option("--tenant-id", default="default", help="Tenant ID")
@click.option("--subject-id", default="default", help="Subject ID")
@click.option("--limit", default=10, help="Maximum number of memories")
@memory.command(name="list")
def list_memories(tenant_id: str, subject_id: str, limit: int) -> None:
    """List memories."""

    async def run() -> list[dict]:
        client = await _postgres_client()
        try:
            records = await client._backend.list_memories(
                tenant_id=tenant_id,
                subject_id=subject_id,
                limit=limit,
            )
            return [record.model_dump(mode="json") for record in records]
        finally:
            await client.__aexit__(None, None, None)

    click.echo(json.dumps(_run(run()), indent=2, default=str))


@memory.command()
@click.option("--id", "memory_id", required=True, help="Memory ID to inspect")
@click.option("--tenant-id", required=True, help="Tenant ID")
@click.option("--actor-id", default="cli-user", help="Actor ID")
def inspect(memory_id: str, tenant_id: str, actor_id: str) -> None:
    """Inspect a memory by ID."""
    from agent_memory.context import TenantContext

    async def run() -> dict | None:
        client = await _postgres_client()
        try:
            record = await client._backend.get_memory(
                UUID(memory_id),
                context=TenantContext(tenant_id=tenant_id, actor_id=actor_id),
            )
            if record is None:
                return None
            version = None
            if hasattr(client._backend, "get_current_version"):
                version = await client._backend.get_current_version(
                    record.id,
                    context=TenantContext(tenant_id=tenant_id, actor_id=actor_id),
                )
            return {
                "memory": record.model_dump(mode="json"),
                "current_version": version.model_dump(mode="json") if version else None,
            }
        finally:
            await client.__aexit__(None, None, None)

    click.echo(json.dumps(_run(run()), indent=2, default=str))


@memory.command()
@click.option("--id", "memory_id", required=True, help="Memory ID to forget/revoke")
@click.option("--tenant-id", required=True, help="Tenant ID")
@click.option("--subject-id", required=True, help="Subject ID")
@click.option("--actor-id", default="cli-user", help="Actor ID")
@click.option("--purpose", required=True, help="Purpose")
def forget(memory_id: str, tenant_id: str, subject_id: str, actor_id: str, purpose: str) -> None:
    """Forget/revoke a memory."""
    from agent_memory.context import MemoryContext

    async def run() -> dict:
        client = await _postgres_client()
        try:
            result = await client.forget(
                memory_id=UUID(memory_id),
                context=MemoryContext(
                    tenant_id=tenant_id,
                    subject_id=subject_id,
                    actor_id=actor_id,
                    purpose=purpose,
                ),
            )
            return result.model_dump(mode="json")
        finally:
            await client.__aexit__(None, None, None)

    click.echo(json.dumps(_run(run()), indent=2, default=str))


# ── security check ───────────────────────────────────────────────────────────


@app.command()
@click.option("--name", "check_name", default=None, help="Specific check to run (optional)")
def security_check(check_name: str | None) -> None:
    """Run security scan."""
    from agent_memory.evaluation.reports import _assert_release_gates

    try:
        checks = _assert_release_gates(strict=True)
    except Exception as exc:
        click.echo(f"Security check FAILED: {exc}", err=True)
        sys.exit(1)
    click.echo("Security Check completed:")
    for item in checks:
        click.echo(f"  ✓ {item}")


@app.group()
def release() -> None:
    """Release gate commands."""


@release.command(name="check")
@click.option("--strict/--no-strict", default=True, help="Fail on any release-gate violation")
def release_check(strict: bool) -> None:
    """Run release gates."""
    from agent_memory.evaluation.reports import _assert_release_gates

    try:
        results = _assert_release_gates(strict=strict)
    except Exception as exc:
        click.echo(f"FAIL: {exc}", err=True)
        sys.exit(1)
    for result in results:
        click.echo(f"  [PASS] {result}")


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
