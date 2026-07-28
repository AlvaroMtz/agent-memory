"""Memory context — mandatory authentication/authorization context for every operation.

The context is frozen and validated before any backend access.
tenant_id, subject_id, and actor_id must come from the authenticated application
context, NEVER from model output or tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from agent_memory.exceptions import (
    MissingActorError,
    MissingPurposeError,
    MissingSubjectError,
    MissingTenantError,
)


@dataclass(frozen=True)
class MemoryContext:
    """Mandatory context for every memory operation.

    All fields must be provided by the application runtime.
    The model/agent must never be allowed to select these values.
    """

    tenant_id: str
    subject_id: str
    actor_id: str
    purpose: str
    request_id: str = field(default_factory=lambda: uuid4().hex[:16])

    def __post_init__(self) -> None:
        """Validate context fields on creation."""
        if not self.tenant_id or not self.tenant_id.strip():
            raise MissingTenantError("tenant_id is required and must be non-empty")
        if not self.subject_id or not self.subject_id.strip():
            raise MissingSubjectError("subject_id is required and must be non-empty")
        if not self.actor_id or not self.actor_id.strip():
            raise MissingActorError("actor_id is required and must be non-empty")
        if not self.purpose or not self.purpose.strip():
            raise MissingPurposeError("purpose is required and must be non-empty")


@dataclass(frozen=True)
class TenantContext:
    """Minimal tenant-scoped context for backend operations.

    Used to establish RLS context and filter queries.
    """

    tenant_id: str
    actor_id: str | None = None