"""Constants and enums for agent-memory.

These are framework-agnostic values used across domain, application, and adapters.
"""

from __future__ import annotations

from enum import Enum
from typing import Final, Literal

# ── Memory Types ───────────────────────────────────────────────────────────────

MemoryType = Literal["semantic", "preference"]

# ── Memory Status ──────────────────────────────────────────────────────────────

MemoryStatus = Literal[
    "candidate",
    "pending_review",
    "active",
    "superseded",
    "revoked",
    "expired",
    "rejected",
    "deleted",
]

# ── Sensitivity Levels ─────────────────────────────────────────────────────────

Sensitivity = Literal["public", "internal", "personal", "sensitive"]

# ── Source Types ───────────────────────────────────────────────────────────────

SourceType = Literal["user_explicit", "trusted_tool", "imported"]

# ── Message Roles ──────────────────────────────────────────────────────────────

# Roles eligible for extraction
EXTRACTABLE_ROLES: Final[set[str]] = {"user", "trusted_tool"}

# Roles that are NEVER eligible for extraction
NON_EXTRACTABLE_ROLES: Final[set[str]] = {"assistant", "system", "developer", "tool"}

# ── Preference Allowlist ───────────────────────────────────────────────────────

# Only these predicates are automatically injected into the model context.
# All other memories are presented as untrusted data blocks.
AUTOMATIC_PREFERENCE_PREDICATES: Final[set[str]] = {
    "response_language",
    "code_language",
    "response_length",
    "output_format",
}

# ── Contradiction Classification ───────────────────────────────────────────────

ContradictionClass = Literal[
    "duplicate",
    "supports",
    "supersedes",
    "contradicts",
    "unrelated",
]

# ── Audit Actions ──────────────────────────────────────────────────────────────

AuditAction = Literal[
    "consent.granted",
    "consent.revoked",
    "consent.expired",
    "memory.candidate_created",
    "memory.candidate_accepted",
    "memory.candidate_rejected",
    "memory.activated",
    "memory.superseded",
    "memory.retrieved",
    "memory.revoked",
    "memory.expired",
    "memory.deleted",
    "security.access_denied",
    "security.cross_tenant_attempt",
    "security.unauthorized_read",
    "security.unauthorized_write",
]

# ── Default Thresholds ─────────────────────────────────────────────────────────

DEFAULT_MINIMUM_CONFIDENCE: Final[float] = 0.85
DEFAULT_MINIMUM_SCORE: Final[float] = 0.65
DEFAULT_TOP_K: Final[int] = 8
DEFAULT_TOKEN_BUDGET: Final[int] = 1_200
DEFAULT_EMBEDDING_DIMENSIONS: Final[int] = 128

# ── Default Consent ────────────────────────────────────────────────────────────

DEFAULT_RETENTION_DAYS: Final[int | None] = None  # unlimited

# ── Production Safety ──────────────────────────────────────────────────────────

PRODUCTION_FORBIDDEN_PROVIDERS: Final[set[str]] = {
    "noop",  # encryption
    "rules",  # extraction (demo-only)
    "fake",  # extraction (test-only)
}

# ── RLS ────────────────────────────────────────────────────────────────────────

TENANT_CONTEXT_PARAM: Final[str] = "agent_memory.tenant_id"
ACTOR_CONTEXT_PARAM: Final[str] = "agent_memory.actor_id"


class MemoryStatusEnum(str, Enum):
    """String enum for memory status values."""

    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    EXPIRED = "expired"
    REJECTED = "rejected"
    DELETED = "deleted"


class MemoryTypeEnum(str, Enum):
    """String enum for memory types."""

    SEMANTIC = "semantic"
    PREFERENCE = "preference"


class SensitivityEnum(str, Enum):
    """String enum for sensitivity levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


class SourceTypeEnum(str, Enum):
    """String enum for source types."""

    USER_EXPLICIT = "user_explicit"
    TRUSTED_TOOL = "trusted_tool"
    IMPORTED = "imported"


class ContradictionClassEnum(str, Enum):
    """String enum for contradiction classifications."""

    DUPLICATE = "duplicate"
    SUPPORTS = "supports"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    UNRELATED = "unrelated"
