"""Context adapter — extracts MemoryContext from LangChain runtime.

Provides utilities to convert LangChain's RunnableConfig, BaseMessage, and
other framework types into agent-memory's domain types.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_memory.constants import NON_EXTRACTABLE_ROLES
from agent_memory.context import MemoryContext

logger = logging.getLogger(__name__)


class ContextAdapter:
    """Adapter between LangChain runtime types and agent-memory context.

    Extracts tenant_id, subject_id, and other required context from
    LangChain's ``RunnableConfig`` and message metadata.
    """

    def extract_from_runtime(
        self,
        runnable_config: dict[str, Any],
        **kwargs: Any,
    ) -> MemoryContext:
        """Extract MemoryContext from a LangChain RunnableConfig.

        Looks for tenant_id, subject_id, actor_id, and purpose in the config
        metadata, fallback_tags, and config dict.

        Args:
            runnable_config: LangChain's RunnableConfig dict.
            **kwargs: Additional context sources (e.g. user-provided defaults).

        Returns:
            A validated ``MemoryContext`` instance.

        Raises:
            ValueError: If required context fields are missing.
        """
        metadata = runnable_config.get("metadata", {})
        tags = runnable_config.get("tags", [])

        # Extract tenant_id from various sources
        tenant_id = (
            kwargs.get("tenant_id")
            or metadata.get("tenant_id")
            or self._first_match(tags, "tenant:")
        )

        # Extract subject_id from various sources
        subject_id = (
            kwargs.get("subject_id")
            or metadata.get("subject_id")
            or metadata.get("user_id")
            or self._first_match(tags, "subject:")
        )

        # Extract actor_id from various sources
        actor_id = (
            kwargs.get("actor_id")
            or metadata.get("actor_id")
            or metadata.get("agent_id")
            or self._first_match(tags, "agent:")
        )

        # Extract purpose from various sources
        purpose = (
            kwargs.get("purpose")
            or metadata.get("purpose")
            or self._first_match(tags, "purpose:")
        )

        if not tenant_id:
            raise ValueError("tenant_id is required in LangChain RunnableConfig")
        if not subject_id:
            raise ValueError("subject_id is required in LangChain RunnableConfig")
        if not actor_id:
            raise ValueError("actor_id is required in LangChain RunnableConfig")
        if not purpose:
            raise ValueError("purpose is required in LangChain RunnableConfig")

        return MemoryContext(
            tenant_id=tenant_id,
            subject_id=subject_id,
            actor_id=actor_id,
            purpose=purpose,
        )

    def extract_from_message(
        self,
        msg: Any,
    ) -> dict[str, Any]:
        """Extract metadata from a LangChain BaseMessage.

        Extracts user_id, conversation_id, and agent_id from message metadata,
        content, and other attributes.

        Args:
            msg: A LangChain BaseMessage instance (or mock with similar attributes).

        Returns:
            Dict with extracted keys: user_id, conversation_id, agent_id, role, content.
        """
        result: dict[str, Any] = {}

        # Extract from metadata
        metadata = getattr(msg, "metadata", {}) or {}
        if isinstance(metadata, dict):
            result.update(metadata)

        # Extract user_id / agent_id
        if hasattr(msg, "type"):
            result["type"] = msg.type
        if hasattr(msg, "role"):
            result["role"] = msg.role
        if hasattr(msg, "content"):
            content = msg.content
            if isinstance(content, str):
                result["content"] = content
            elif isinstance(content, list):
                # Handle multimodal content
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        parts.append(item["text"])
                    elif isinstance(item, str):
                        parts.append(item)
                result["content"] = " ".join(parts) if parts else ""

        return result

    def should_process(self, msg: Any) -> bool:
        """Check if a message should trigger memory operations.

        Returns True for user, assistant, human, ai, and tool messages;
        False for system and developer messages.

        Args:
            msg: A LangChain BaseMessage instance.

        Returns:
            True if the message should be processed by the middleware.
        """
        role = getattr(msg, "role", None) or getattr(msg, "type", "")

        # Never process system and developer messages
        if role in ("system", "developer"):
            return False

        # Accept known message types
        if role in ("user", "human", "ai", "assistant", "tool"):
            return True

        # Unknown roles: do not process
        return False

    # ── Internal helpers ──────────────────────────────────────────────────

    def _first_match(self, tags: list[str], prefix: str) -> str | None:
        """Find the first tag matching a prefix, return its value.

        Example: tags=["tenant:acme", "purpose:analysis"] -> "acme" with prefix "tenant:"
        """
        for tag in tags:
            if tag.startswith(prefix):
                return tag[len(prefix):]
        return None