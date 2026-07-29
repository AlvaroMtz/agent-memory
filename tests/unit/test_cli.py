"""Unit tests for the CLI (src/agent_memory/cli/main.py)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch
from uuid import uuid4

from click.testing import CliRunner

from agent_memory.cli.main import app


class TestCLI:
    """Tests for the CLI group and subcommands."""

    def test_version(self):
        """--version flag prints version."""
        result = CliRunner().invoke(app, ["--version"])
        assert "0.0.1" in result.output

    def test_help(self):
        """--help shows all subcommands."""
        result = CliRunner().invoke(app, ["--help"])
        assert "init" in result.output
        assert "remember" in result.output
        assert "retrieve" in result.output
        assert "serve" in result.output
        assert "doctor" in result.output
        assert "migrate" in result.output
        assert "eval" in result.output
        assert "lab" in result.output
        assert "consent" in result.output
        assert "memory" in result.output
        assert "security-check" in result.output
        assert "check" in result.output

    def test_init(self):
        """init command runs without error."""
        result = CliRunner().invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Environment:" in result.output

    def test_doctor(self):
        """doctor command runs without error."""
        result = CliRunner().invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_migrate(self):
        """migrate command runs without error."""
        result = CliRunner().invoke(app, ["migrate"])
        assert result.exit_code == 0
        assert "Alembic" in result.output

    def test_remember(self):
        """remember command runs without error."""
        result = CliRunner().invoke(app, ["remember"], input="[]")
        assert result.exit_code == 0

    def test_retrieve(self):
        """retrieve command runs without error."""
        result = CliRunner().invoke(
            app,
            ["retrieve"],
            input='{"query": "test", "tenant_id": "default", "filters": {}}',
        )
        assert result.exit_code == 0

    def test_check(self):
        """check command runs release gates."""
        result = CliRunner().invoke(app, ["check"])
        assert result.exit_code == 0
        assert "config OK" in result.output

    def test_check_strict(self):
        """check --strict exits 0 when all gates pass."""
        with patch(
            "agent_memory.evaluation.reports._assert_release_gates", return_value=["config OK"]
        ):
            result = CliRunner().invoke(app, ["check", "--strict"])
        assert result.exit_code == 0

    def test_serve(self):
        """serve command starts uvicorn."""
        fake_uvicorn = types.SimpleNamespace(run=MagicMock())
        with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
            result = CliRunner().invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9999"])
            assert result.exit_code == 0
            fake_uvicorn.run.assert_called_once()

    def test_lab_seed(self):
        """lab seed runs without error."""
        result = CliRunner().invoke(app, ["lab", "seed"])
        assert result.exit_code == 0
        assert "Seeding" in result.output

    def test_lab_reset(self):
        """lab reset runs without error."""
        result = CliRunner().invoke(app, ["lab", "reset"])
        assert result.exit_code == 0
        assert "Resetting" in result.output

    def test_eval_run(self):
        """eval run runs without error (datasets dir doesn't exist)."""
        result = CliRunner().invoke(
            app,
            ["eval", "run", "--path", "/tmp/agent-memory-nodatasets-nonexistent"],
        )
        assert result.exit_code == 0

    def test_scenario_run_file(self):
        """scenario run executes a YAML file with scenario wrappers."""
        result = CliRunner().invoke(
            app,
            ["scenario", "run", "datasets/extraction/role-filtering.yaml"],
        )
        assert result.exit_code == 0
        assert "Result: PASS" in result.output

    def test_release_check_command(self):
        """release check reads versioned gate configuration."""
        result = CliRunner().invoke(app, ["release", "check", "--no-strict"])
        assert result.exit_code == 0
        assert "required files OK" in result.output

    def test_eval_report(self):
        """eval report runs without error."""
        result = CliRunner().invoke(
            app,
            [
                "eval",
                "report",
                "--path",
                "/tmp/agent-memory-nodatasets-nonexistent",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0

    def test_consent_grant(self):
        """consent grant runs without error."""
        result = CliRunner().invoke(
            app, ["consent", "grant"], env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"}
        )
        assert result.exit_code == 0
        assert "Consent granted" in result.output

    def test_consent_revoke(self):
        """consent revoke fails closed when no active persisted consent exists."""
        result = CliRunner().invoke(
            app, ["consent", "revoke"], env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"}
        )
        assert result.exit_code != 0

    def test_consent_list(self):
        """consent list runs without error."""
        result = CliRunner().invoke(
            app, ["consent", "list"], env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"}
        )
        assert result.exit_code == 0
        assert "[]" in result.output

    def test_memory_list(self):
        """memory list runs without error."""
        result = CliRunner().invoke(
            app, ["memory", "list"], env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"}
        )
        assert result.exit_code == 0
        assert "[]" in result.output

    def test_memory_inspect(self):
        """memory inspect requires tenant-scoped context and returns JSON/null."""
        result = CliRunner().invoke(
            app,
            ["memory", "inspect", "--id", str(uuid4()), "--tenant-id", "default"],
            env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"},
        )
        assert result.exit_code == 0
        assert "null" in result.output

    def test_memory_forget(self):
        """memory forget fails closed without a matching memory."""
        result = CliRunner().invoke(
            app,
            [
                "memory",
                "forget",
                "--id",
                str(uuid4()),
                "--tenant-id",
                "default",
                "--subject-id",
                "default",
                "--purpose",
                "testing",
            ],
            env={"AGENT_MEMORY_CLI_BACKEND": "in-memory"},
        )
        assert result.exit_code != 0

    def test_security_check(self):
        """security-check runs without error."""
        with patch(
            "agent_memory.evaluation.reports._assert_release_gates", return_value=["config OK"]
        ):
            result = CliRunner().invoke(app, ["security-check"])
        assert result.exit_code == 0
        assert "Security Check" in result.output
