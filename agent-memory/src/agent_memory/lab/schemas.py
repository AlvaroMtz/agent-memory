"""Pydantic schemas for the Memory Lab API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConversationSimulationRequest(BaseModel):
    """Request to simulate a conversation and extract memories."""

    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of conversation messages with 'role' and 'content' keys",
    )
    agent_id: str = Field(default="agent", description="Agent identifier")
    context_id: str = Field(default="default", description="Context/session identifier")


class ConversationSimulationResponse(BaseModel):
    """Response from conversation simulation."""

    extracted: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted memory candidates",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Any errors during extraction",
    )


class RetrieveRequest(BaseModel):
    """Request for memory retrieval."""

    query: str = Field(
        default="",
        description="Search query",
    )
    subject_id: str = Field(
        default="default",
        description="Subject identifier",
    )
    memory_types: list[str] | None = Field(
        default=None,
        description="Optional memory type filter",
    )
    max_tokens: int = Field(
        default=1200,
        description="Token budget for results",
        ge=100,
        le=10000,
    )


class RetrieveResponse(BaseModel):
    """Response from memory retrieval."""

    results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Retrieved memories",
    )
    total_count: int = Field(
        default=0,
        description="Total number of results",
    )
    tokens_used: int = Field(
        default=0,
        description="Token count used",
    )


class ConsentGrantRequest(BaseModel):
    """Request to grant consent."""

    subject_id: str = Field(
        description="Subject identifier",
    )
    memory_types: list[str] = Field(
        default_factory=list,
        description="List of allowed memory types",
    )
    sensitivity: str = Field(
        default="public",
        description="Allowed sensitivity level",
    )


class ConsentRevokeRequest(BaseModel):
    """Request to revoke consent."""

    subject_id: str = Field(
        description="Subject identifier",
    )
    memory_type: str | None = Field(
        default=None,
        description="Memory type to revoke (None for all types)",
    )


class ErrorResponse(BaseModel):
    """Error response structure."""

    error: str = Field(
        default="error",
        description="Error type",
    )
    detail: str | None = Field(
        default=None,
        description="Detailed error message",
    )
