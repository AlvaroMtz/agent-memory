"""LangChain structured extractor adapter.

The domain only depends on the MemoryExtractor protocol. This adapter is kept
optional and accepts any LangChain-compatible runnable that returns either a
list of dictionaries or an object with ``candidates``.
"""

from __future__ import annotations

import inspect
from typing import Any

from agent_memory.domain.candidate import MemoryCandidate


class LangChainStructuredExtractor:
    """Extract memory candidates through a LangChain-compatible runnable."""

    def __init__(self, runnable: Any, *, provider: str = "langchain") -> None:
        self.runnable = runnable
        self.provider = provider

    async def extract(
        self,
        *,
        messages: list[dict],
        subject_id: str,
    ) -> list[MemoryCandidate]:
        payload = {"messages": messages, "subject_id": subject_id}
        if hasattr(self.runnable, "ainvoke"):
            raw = await self.runnable.ainvoke(payload)
        elif hasattr(self.runnable, "invoke"):
            raw = self.runnable.invoke(payload)
            if inspect.isawaitable(raw):
                raw = await raw
        else:
            raise TypeError("LangChain extractor runnable must expose invoke() or ainvoke()")

        candidates_raw = getattr(raw, "candidates", raw)
        if isinstance(candidates_raw, dict):
            candidates_raw = candidates_raw.get("candidates", [])
        if not isinstance(candidates_raw, list):
            raise TypeError(
                "LangChain extractor output must be a list or {candidates: [...]} object"
            )
        return [
            item if isinstance(item, MemoryCandidate) else MemoryCandidate(**item)
            for item in candidates_raw
        ]
