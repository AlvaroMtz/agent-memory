"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

from agent_memory.config import DatabaseConfig, load_config


def test_database_schema_alias() -> None:
    """External config keeps using `schema` while Python avoids BaseModel shadowing."""

    config = DatabaseConfig(schema="custom_schema")

    assert config.db_schema == "custom_schema"


def test_load_config_from_yaml_path(tmp_path: Path) -> None:
    """YAML config is a real settings source, not ignored model_config metadata."""

    config_file = tmp_path / "agent-memory.yaml"
    config_file.write_text(
        "database:\n"
        "  schema: yaml_schema\n"
        "  uri: postgresql+psycopg://example/db\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config.database.db_schema == "yaml_schema"
    assert config.database.uri == "postgresql+psycopg://example/db"


def test_environment_overrides_yaml(monkeypatch, tmp_path: Path) -> None:
    """Environment variables have higher precedence than YAML files."""

    config_file = tmp_path / "agent-memory.yaml"
    config_file.write_text("database:\n  schema: yaml_schema\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_MEMORY_DATABASE__SCHEMA", "env_schema")

    config = load_config(config_file)

    assert config.database.db_schema == "env_schema"
