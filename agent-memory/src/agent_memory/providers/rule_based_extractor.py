"""Rule-based extractor for deterministic demos without external APIs.

Uses simple regex patterns to extract preferences and semantic facts.
Not suitable for production — for demos and local development only.
"""

from __future__ import annotations

import re
from typing import Any

from agent_memory.domain.candidate import MemoryCandidate
from agent_memory.ports.extractor import MemoryExtractor


# Extraction patterns: (pattern, memory_type, predicate, value_fn)
PATTERNS: list[tuple[re.Pattern, str, str, Any]] = [
    # Preference: "Prefiero X" → preference
    (re.compile(r"prefiero\s+(que\s+)?(los\s+)?(ejemplos\s+(sean\s+)?(en\s+)?)?(\w+)", re.IGNORECASE),
     "preference", "response_language", lambda m: m.group(6)),
    # Preference: "Mi lenguaje es X" → preference
    (re.compile(r"(mi\s+)?lenguaje\s+(favorito\s+)?es\s+(\w+)", re.IGNORECASE),
     "preference", "code_language", lambda m: m.group(3)),
    # Preference: "Prefiero respuestas cortas/largas" → preference
    (re.compile(r"prefiero\s+respuestas\s+(cortas|largas|medias)", re.IGNORECASE),
     "preference", "response_length", lambda m: m.group(1)),
    # Semantic: "Trabajo en X" → semantic
    (re.compile(r"trabajo\s+(en|como)\s+(\w[\w\s]*)", re.IGNORECASE),
     "semantic", "occupation", lambda m: m.group(2).strip()),
    # Semantic: "Soy X" → semantic (role)
    (re.compile(r"soy\s+(un|una|el|la)?\s*(\w[\w\s]*)", re.IGNORECASE),
     "semantic", "role", lambda m: m.group(2).strip()),
    # Contradiction: "Ya no prefiero X" → explicit change
    (re.compile(r"ya\s+no\s+(quiero|prefiero|uso)\s+(\w[\w\s]*)", re.IGNORECASE),
     "preference", "negated", lambda m: m.group(2).strip()),
]

# Subject key inference from predicate
SUBJECT_KEY_MAP: dict[str, str] = {
    "response_language": "communication",
    "code_language": "code",
    "response_length": "communication",
    "output_format": "communication",
    "occupation": "work",
    "role": "work",
}


class RuleBasedExtractor:
    """Deterministic, rule-based memory extractor.

    Uses simple regex patterns to extract memories from messages.
    Only extracts from user messages.
    """

    async def extract(
        self,
        *,
        messages: list[dict],
        subject_id: str,
    ) -> list[MemoryCandidate]:
        """Extract memory candidates using regex patterns."""
        candidates: list[MemoryCandidate] = []

        for msg in messages:
            role = msg.get("role", "")
            if role not in ("user", "trusted_tool"):
                continue

            content = msg.get("content", "")
            msg_id = msg.get("id", "")

            for pattern, memory_type, predicate, value_fn in PATTERNS:
                match = pattern.search(content)
                if match:
                    value = value_fn(match)
                    subject_key = SUBJECT_KEY_MAP.get(predicate, predicate)
                    candidates.append(
                        MemoryCandidate(
                            memory_type=memory_type,
                            subject_key=subject_key,
                            predicate=predicate,
                            value=value,
                            source_message_id=msg_id,
                            evidence_text=match.group(0),
                            source_role=role,
                            explicitly_stated=True,
                            confidence=1.0,
                        )
                    )

        return candidates


class RuleBasedExtractorFactory:
    """Factory for RuleBasedExtractor."""

    def create(self) -> RuleBasedExtractor:
        return RuleBasedExtractor()