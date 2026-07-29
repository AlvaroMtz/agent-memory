"""Unit tests for MemoryContext validation."""

import pytest

from agent_memory.context import MemoryContext
from agent_memory.exceptions import (
    MissingActorError,
    MissingPurposeError,
    MissingSubjectError,
    MissingTenantError,
)


class TestMemoryContext:
    """Test MemoryContext creation and validation."""

    def test_valid_context(self):
        ctx = MemoryContext(
            tenant_id="tenant-a",
            subject_id="user-1",
            actor_id="user-1",
            purpose="assistant-personalization",
        )
        assert ctx.tenant_id == "tenant-a"
        assert ctx.subject_id == "user-1"
        assert ctx.actor_id == "user-1"
        assert ctx.purpose == "assistant-personalization"
        assert ctx.request_id is not None

    def test_frozen(self):
        ctx = MemoryContext(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
        )
        with pytest.raises(AttributeError):
            ctx.tenant_id = "other"  # type: ignore

    def test_missing_tenant(self):
        with pytest.raises(MissingTenantError):
            MemoryContext(
                tenant_id="",
                subject_id="s",
                actor_id="a",
                purpose="p",
            )

    def test_blank_tenant(self):
        with pytest.raises(MissingTenantError):
            MemoryContext(
                tenant_id="   ",
                subject_id="s",
                actor_id="a",
                purpose="p",
            )

    def test_missing_subject(self):
        with pytest.raises(MissingSubjectError):
            MemoryContext(
                tenant_id="t",
                subject_id="",
                actor_id="a",
                purpose="p",
            )

    def test_missing_actor(self):
        with pytest.raises(MissingActorError):
            MemoryContext(
                tenant_id="t",
                subject_id="s",
                actor_id="",
                purpose="p",
            )

    def test_missing_purpose(self):
        with pytest.raises(MissingPurposeError):
            MemoryContext(
                tenant_id="t",
                subject_id="s",
                actor_id="a",
                purpose="",
            )

    def test_unique_request_ids(self):
        ctx1 = MemoryContext(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
        )
        ctx2 = MemoryContext(
            tenant_id="t",
            subject_id="s",
            actor_id="a",
            purpose="p",
        )
        assert ctx1.request_id != ctx2.request_id
