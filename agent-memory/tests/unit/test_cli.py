"""Unit tests for the CLI (src/agent_memory/cli/main.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        assert "eval" in result.output
        assert "check" in result.output

    def test_init(self):
        """init command runs without error."""
        result = CliRunner().invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Environment:" in result.output

    def test_check(self):
        """check command runs release gates."""
        result = CliRunner().invoke(app, ["check"])
        assert result.exit_code == 0
        assert "config OK" in result.output

    def test_check_strict(self):
        """check --strict exits 0 when all gates pass."""
        result = CliRunner().invoke(app, ["check", "--strict"])
        assert result.exit_code == 0

    def test_serve(self):
        """serve command starts uvicorn."""
        with patch("uvicorn.run") as mock_run:
            result = CliRunner().invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9999"])
            assert result.exit_code == 0
            mock_run.assert_called_once()

    def test_eval_run(self):
        """eval run runs without error (datasets dir doesn't exist)."""
        result = CliRunner().invoke(
            app,
            ["eval", "run", "--path", "/tmp/agent-memory-nodatasets-nonexistent"],
        )
        assert result.exit_code == 0

    def test_eval_report(self):
        """eval report runs without error."""
        result = CliRunner().invoke(
            app,
            ["eval", "report", "--path", "/tmp/agent-memory-nodatasets-nonexistent", "--format", "json"],
        )
        assert result.exit_code == 0