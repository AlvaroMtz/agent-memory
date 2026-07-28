"""Tools integration — helpers for marking tool outputs as trusted_tool source.

Provides decorators and utilities for integrating agent-memory's extraction
pipeline with LangChain's tool calling system.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable

from agent_memory.constants import SourceTypeEnum

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

MEMORY_TOOL_KEY: str = "_agent_memory_source"
"""Metadata key used to mark tool outputs as coming from agent-memory."""

TRUSTED_TOOL_SOURCE: str = SourceTypeEnum.TRUSTED_TOOL.value


# ── Decorators ────────────────────────────────────────────────────────────


def trust_tool_output(
    tool_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a tool's output as a trusted_tool source type.

    When applied to a tool function, the decorator ensures that any memory
    candidates extracted from the tool's output are tagged with
    ``source_type="trusted_tool"`` instead of the default ``"user_explicit"``.

    Example::

        from agent_memory.langchain.tools import trust_tool_output

        @trust_tool_output("weather_lookup")
        async def weather_lookup(location: str) -> str:
            return f"Weather in {location}: sunny"

    Args:
        tool_name: Name of the tool (used for metadata tagging).

    Returns:
        A decorator that wraps the tool function with trusted_tool metadata.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                result = await func(*args, **kwargs)
                if isinstance(result, dict):
                    result.setdefault(MEMORY_TOOL_KEY, {})
                    result[MEMORY_TOOL_KEY]["source"] = TRUSTED_TOOL_SOURCE
                    result[MEMORY_TOOL_KEY]["tool_name"] = tool_name
                return result

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                result = func(*args, **kwargs)
                if isinstance(result, dict):
                    result.setdefault(MEMORY_TOOL_KEY, {})
                    result[MEMORY_TOOL_KEY]["source"] = TRUSTED_TOOL_SOURCE
                    result[MEMORY_TOOL_KEY]["tool_name"] = tool_name
                return result

            return sync_wrapper

    return decorator


def is_trusted_tool(tool_call: Any) -> bool:
    """Check if a tool call is marked as a trusted_tool source.

    Args:
        tool_call: A tool call object (dict or object with metadata attribute).

    Returns:
        True if the tool call has MEMORY_TOOL_KEY metadata with
        source set to TRUSTED_TOOL_SOURCE.
    """
    if isinstance(tool_call, dict):
        metadata = tool_call.get("metadata", {})
        if isinstance(metadata, dict):
            source_info = metadata.get(MEMORY_TOOL_KEY, {})
            if isinstance(source_info, dict):
                return source_info.get("source") == TRUSTED_TOOL_SOURCE
        return False

    # Handle object-style tool calls
    metadata = getattr(tool_call, "metadata", None)
    if isinstance(metadata, dict):
        source_info = metadata.get(MEMORY_TOOL_KEY, {})
        if isinstance(source_info, dict):
            return source_info.get("source") == TRUSTED_TOOL_SOURCE

    return False


def mark_tool_as_trusted(
    tool_call: dict[str, Any],
    tool_name: str,
) -> dict[str, Any]:
    """Mark a tool call dict as trusted_tool source.

    Convenience function for marking tool calls that have already been
    created (e.g. from LangChain's tool calling output).

    Args:
        tool_call: The tool call dict to mark.
        tool_name: Name of the tool.

    Returns:
        The modified tool_call dict with trusted_tool metadata.
    """
    tool_call.setdefault("metadata", {})
    tool_call["metadata"][MEMORY_TOOL_KEY] = {
        "source": TRUSTED_TOOL_SOURCE,
        "tool_name": tool_name,
    }
    return tool_call