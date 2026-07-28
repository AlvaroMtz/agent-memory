"""agent-memory configuration.

Configuration via Pydantic settings with YAML file and environment variable support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_memory.constants import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_MINIMUM_CONFIDENCE,
    DEFAULT_MINIMUM_SCORE,
    DEFAULT_TOKEN_BUDGET,
    DEFAULT_TOP_K,
    PRODUCTION_FORBIDDEN_PROVIDERS,
)
from agent_memory.exceptions import ConfigurationError


class DatabaseConfig(BaseModel):
    uri: str = "postgresql+asyncpg://localhost:5432/agent_memory"
    schema: str = "agent_memory"
    pool_size: int = 5
    max_overflow: int = 10


class TenantConfig(BaseModel):
    isolation: Literal["strict", "none"] = "strict"
    postgres_rls: bool = True


class ConsentConfig(BaseModel):
    default: Literal["deny", "allow"] = "deny"


class ExtractionConfig(BaseModel):
    provider: str = "rules"
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE
    require_evidence: bool = True
    allow_inference: bool = False


class EmbeddingsConfig(BaseModel):
    provider: str = "deterministic"
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS


class RetrievalConfig(BaseModel):
    strategy: Literal["hybrid", "vector", "lexical"] = "hybrid"
    top_k: int = DEFAULT_TOP_K
    minimum_score: float = DEFAULT_MINIMUM_SCORE
    token_budget: int = DEFAULT_TOKEN_BUDGET


class EncryptionConfig(BaseModel):
    provider: str = "noop"
    key: str | None = None


class MemoryConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_MEMORY_",
        env_nested_delimiter="__",
        yaml_file="agent-memory.yaml",
        extra="ignore",
    )

    environment: Literal["development", "production", "testing"] = "development"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    tenant: TenantConfig = Field(default_factory=TenantConfig)
    consent: ConsentConfig = Field(default_factory=ConsentConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)

    evaluation: dict = Field(default_factory=lambda: {
        "datasets_path": "./datasets",
        "seed": 42,
        "fail_on_gate_violation": True,
    })

    def validate_production(self) -> None:
        """Validate configuration for production environment.

        Raises ConfigurationError if any requirement is not met.
        """
        if self.environment != "production":
            return

        errors: list[str] = []

        if self.encryption.provider in PRODUCTION_FORBIDDEN_PROVIDERS:
            errors.append(
                f"Encryption provider '{self.encryption.provider}' is forbidden in production. "
                f"Use 'aes-gcm' or another production-grade provider."
            )

        if not self.tenant.postgres_rls:
            errors.append("PostgreSQL RLS is required in production")

        if self.consent.default != "deny":
            errors.append("Consent default must be 'deny' in production")

        if errors:
            raise ConfigurationError(
                f"Production configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            )


def load_config(path: str | Path | None = None) -> MemoryConfig:
    """Load memory configuration from a YAML file or environment variables."""
    config = MemoryConfig()
    if path:
        config = MemoryConfig(_yaml_file=str(path))
    config.validate_production()
    return config