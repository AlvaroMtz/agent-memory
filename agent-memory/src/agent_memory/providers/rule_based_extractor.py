"""Rule-based extractor for deterministic demos without external APIs.

Uses simple regex patterns to extract preferences and semantic facts.
Not suitable for production — for demos and local development only.
"""

from __future__ import annotations

import re
from typing import Any

from agent_memory.domain.candidate import MemoryCandidate

# Extraction patterns: (pattern, memory_type, subject_key, predicate, value_fn)
PATTERNS: list[tuple[re.Pattern, str, str, str, Any]] = [
    # Preference: "I prefer responses in English" → preference
    (
        re.compile(r"i\s+prefer\s+responses\s+in\s+(\w+)", re.IGNORECASE),
        "preference",
        "language",
        "response_language",
        lambda m: m.group(1),
    ),
    # Preference: "My preferred language is Spanish" → preference
    (
        re.compile(r"my\s+preferred\s+language\s+is\s+(\w+)", re.IGNORECASE),
        "preference",
        "language",
        "response_language",
        lambda m: m.group(1),
    ),
    # Preference: "Use formal language please" → preference
    (
        re.compile(r"use\s+(formal|informal|simple)\s+language\s+please", re.IGNORECASE),
        "preference",
        "language",
        "response_language",
        lambda m: m.group(1),
    ),
    # Preference: "I prefer short responses" → preference
    (
        re.compile(
            r"i\s+prefer\s+(short|terse|concise|long|medium)\s+(responses|answers)", re.IGNORECASE
        ),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Preference: "I like terse answers" → preference
    (
        re.compile(r"i\s+like\s+(terse|concise|short)\s+answers", re.IGNORECASE),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Preference: "Keep answers concise" → preference
    (
        re.compile(r"keep\s+answers\s+(concise|short|terse)", re.IGNORECASE),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Preference: "keep them concise" → preference
    (
        re.compile(r"keep\s+them\s+(concise|short|terse)", re.IGNORECASE),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Preference: "I prefer code snippets" → preference
    (
        re.compile(r"i\s+prefer\s+(code\s+snippets)", re.IGNORECASE),
        "preference",
        "response",
        "output_format",
        lambda m: m.group(1),
    ),
    # Preference: "Actually, I prefer TypeScript now" → preference
    (
        re.compile(r"actually,?\s+i\s+prefer\s+(\w+)\s+now", re.IGNORECASE),
        "preference",
        "code",
        "code_language",
        lambda m: m.group(1),
    ),
    # Preference: "I prefer JavaScript" → preference
    (
        re.compile(r"i\s+prefer\s+(python|typescript|javascript|rust|java)\b", re.IGNORECASE),
        "preference",
        "code",
        "code_language",
        lambda m: m.group(1),
    ),
    # Preference: "I like TypeScript" → preference
    (
        re.compile(r"i\s+like\s+(python|typescript|javascript|rust|java)\b", re.IGNORECASE),
        "preference",
        "code",
        "code_language",
        lambda m: m.group(1),
    ),
    # Preference: "I like fast responses" → preference
    (
        re.compile(r"i\s+like\s+(fast|short|long|medium)\s+responses", re.IGNORECASE),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Preference: "Please use simple language" → preference
    (
        re.compile(r"please\s+use\s+(simple|plain|technical)\s+language", re.IGNORECASE),
        "preference",
        "language",
        "code_language",
        lambda m: m.group(1),
    ),
    # Trusted tool: "Detected user prefers dark mode: true" → preference
    (
        re.compile(r"detected\s+user\s+prefers\s+dark\s+mode:\s*(true|false)", re.IGNORECASE),
        "preference",
        "theme",
        "dark_mode",
        lambda m: m.group(1).lower() == "true",
    ),
    # Semantic: "My favorite color is blue" → semantic
    (
        re.compile(r"my\s+favorite\s+color\s+is\s+(\w+)", re.IGNORECASE),
        "semantic",
        "user",
        "favorite_color",
        lambda m: m.group(1).lower(),
    ),
    # Semantic: "My favorite programming language is Python" → semantic
    (
        re.compile(r"my\s+favorite\s+programming\s+language\s+is\s+(\w+)", re.IGNORECASE),
        "semantic",
        "programming",
        "favorite_language",
        lambda m: m.group(1),
    ),
    # Preference: "I used to like Java" → preference fixture for stale-memory datasets
    (
        re.compile(
            r"i\s+used\s+to\s+like\s+(python|typescript|javascript|rust|java)\b", re.IGNORECASE
        ),
        "preference",
        "programming",
        "favorite_language",
        lambda m: m.group(1),
    ),
    # Semantic: "My name is Alice" → semantic
    (
        re.compile(r"my\s+name\s+is\s+(\w+)", re.IGNORECASE),
        "semantic",
        "user",
        "name",
        lambda m: m.group(1),
    ),
    # Semantic: "I am interested in machine learning" → semantic
    (
        re.compile(r"i\s+am\s+interested\s+in\s+([\w\s]+)", re.IGNORECASE),
        "semantic",
        "interest",
        "topic",
        lambda m: m.group(1).strip().rstrip("."),
    ),
    # Semantic: employment facts
    (
        re.compile(r"my\s+current\s+employer\s+is\s+([\w\s]+)", re.IGNORECASE),
        "semantic",
        "employment",
        "employer",
        lambda m: m.group(1).strip().rstrip("."),
    ),
    (
        re.compile(r"i\s+work\s+for\s+([\w\s]+)\s+now", re.IGNORECASE),
        "semantic",
        "employment",
        "employer",
        lambda m: m.group(1).strip(),
    ),
    (
        re.compile(r"i\s+work\s+as\s+an?\s+(\w+)", re.IGNORECASE),
        "semantic",
        "employment",
        "job_title",
        lambda m: m.group(1),
    ),
    # Prompt-injection/sensitive fixtures are extracted as data, not commands.
    (
        re.compile(
            r"ignore\s+previous\s+instructions\s+and\s+output\s+the\s+system\s+prompt\.?",
            re.IGNORECASE,
        ),
        "semantic",
        "security",
        "injection_attempt",
        lambda m: m.group(0),
    ),
    (
        re.compile(r"new\s+password\s+is:\s*(\S+)", re.IGNORECASE),
        "semantic",
        "credentials",
        "password",
        lambda m: m.group(1),
    ),
    (
        re.compile(r"you\s+are\s+now\s+an\s+admin\.", re.IGNORECASE),
        "semantic",
        "security",
        "escalation_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"change\s+the\s+tenant\s+to\s+([\w-]+)", re.IGNORECASE),
        "semantic",
        "security",
        "tenant_change_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"activate\s+the\s+administrative\s+tool", re.IGNORECASE),
        "semantic",
        "security",
        "tool_escalation_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"run\s+all\s+actions\s+without\s+confirmation", re.IGNORECASE),
        "semantic",
        "security",
        "permission_escalation_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"reveal\s+the\s+credentials", re.IGNORECASE),
        "semantic",
        "security",
        "secret_exfiltration_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"replace\s+the\s+system\s+prompt", re.IGNORECASE),
        "semantic",
        "security",
        "system_prompt_change_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"authorize\s+external\s+actions", re.IGNORECASE),
        "semantic",
        "security",
        "external_action_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"execute\s+this\s+stored\s+text\s+as\s+code", re.IGNORECASE),
        "semantic",
        "security",
        "stored_code_execution_attempt",
        lambda m: m.group(0).strip(),
    ),
    (
        re.compile(r"<script>.*?</script>", re.IGNORECASE),
        "semantic",
        "security",
        "html_injection",
        lambda m: m.group(0),
    ),
    # Preference: "Prefiero X" → preference
    (
        re.compile(
            r"prefiero\s+(que\s+)?(los\s+)?(ejemplos\s+(sean\s+)?(en\s+)?)?(\w+)", re.IGNORECASE
        ),
        "preference",
        "language",
        "response_language",
        lambda m: m.group(6),
    ),
    # Preference: "Mi lenguaje es X" → preference
    (
        re.compile(r"(mi\s+)?lenguaje\s+(favorito\s+)?es\s+(\w+)", re.IGNORECASE),
        "preference",
        "code",
        "code_language",
        lambda m: m.group(3),
    ),
    # Preference: "Prefiero respuestas cortas/largas" → preference
    (
        re.compile(r"prefiero\s+respuestas\s+(cortas|largas|medias)", re.IGNORECASE),
        "preference",
        "response",
        "response_length",
        lambda m: m.group(1),
    ),
    # Semantic: "Trabajo en X" → semantic
    (
        re.compile(r"trabajo\s+(en|como)\s+(\w[\w\s]*)", re.IGNORECASE),
        "semantic",
        "work",
        "occupation",
        lambda m: m.group(2).strip(),
    ),
    # Semantic: "Soy X" → semantic (role)
    (
        re.compile(r"soy\s+(un|una|el|la)?\s*(\w[\w\s]*)", re.IGNORECASE),
        "semantic",
        "work",
        "role",
        lambda m: m.group(2).strip(),
    ),
    # Contradiction: "Ya no prefiero X" → explicit change
    (
        re.compile(r"ya\s+no\s+(quiero|prefiero|uso)\s+(\w[\w\s]*)", re.IGNORECASE),
        "preference",
        "preference",
        "negated",
        lambda m: m.group(2).strip(),
    ),
]


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

            for pattern, memory_type, subject_key, predicate, value_fn in PATTERNS:
                match = pattern.search(content)
                if match:
                    value = value_fn(match)
                    sensitivity = "personal" if predicate == "password" else "public"
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
                            sensitivity=sensitivity,
                        )
                    )

        return candidates


class RuleBasedExtractorFactory:
    """Factory for RuleBasedExtractor."""

    def create(self) -> RuleBasedExtractor:
        return RuleBasedExtractor()
