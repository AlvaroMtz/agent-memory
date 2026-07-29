"""Forget result — outcome of a memory revocation/deletion operation."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ForgetResult(BaseModel):
    """Result returned by ``MemoryClient.forget``.

    ``forgotten`` is true only when the memory status update succeeded. The
    memory is soft-deleted/revoked at the storage layer; previous immutable
    versions remain available for audit but must not be returned by retrieval.
    """

    memory_id: UUID
    forgotten: bool
    status: str = "deleted"
    audit_id: str | None = None
