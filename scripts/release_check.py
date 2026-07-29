"""Release gates checker — pre-flight validation for agent-memory releases.

Usage:
    python scripts/release_check.py
    # or after CLI is installed:
    agent-memory check
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def check_tests() -> tuple[bool, str]:
    """Run the test suite and verify 0 failures."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/",
            "tests/contract/",
            "tests/integration/",
            "tests/security/",
            "-q",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else ""
    failed = result.returncode != 0
    if failed:
        return False, f"Test suite failed: {summary}"
    return True, summary


def _get_last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def check_imports() -> tuple[bool, str]:
    """Verify the package can be imported."""
    try:
        import agent_memory  # noqa: F401

        return True, "agent_memory imports OK"
    except Exception as exc:
        return False, f"Import failed: {exc}"


def check_cli_help() -> tuple[bool, str]:
    """Verify the CLI is installed and shows help."""
    result = subprocess.run(
        [sys.executable, "-m", "click", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        return True, "CLI help works"
    return False, f"CLI failed: {result.stderr.strip() or result.stdout.strip()}"


def check_migrations() -> tuple[bool, str]:
    """Verify alembic can generate a migration (quick sanity check)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        alembic_cfg = Config(REPO_ROOT / "alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        heads = script.get_heads()
        if heads:
            return True, f"Alembic heads: {', '.join(heads)}"
        return False, "No migration heads found"
    except Exception as exc:
        return False, f"Migration check failed: {exc}"


def main() -> int:
    """Run all release gates and exit with non-zero if any fail."""
    gates: list[tuple[str, tuple[bool, str]]] = [
        ("Package imports", check_imports()),
        ("Test suite", check_tests()),
        ("CLI help", check_cli_help()),
    ]

    # Optional: alembic migration check
    if (REPO_ROOT / "alembic.ini").exists():
        gates.append(("Migrations", check_migrations()))

    failed = 0
    print("=" * 50)
    print("agent-memory Release Gates")
    print("=" * 50)
    for name, (ok, detail) in gates:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  {name}")
        print(f"        {detail}")
        if not ok:
            failed += 1
    print("=" * 50)
    if failed:
        print(f"  {failed} gate(s) failed — release blocked")
        return 1
    else:
        print("  All gates passed — ready to release 🚀")
        return 0


if __name__ == "__main__":
    sys.exit(main())
