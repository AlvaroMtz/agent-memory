"""Log redaction — filter secrets and PII from log strings before writing.

Uses regex patterns to identify and replace sensitive data:
- Email addresses
- Phone numbers
- API keys (common formats)
- Bearer tokens
- Passwords and secrets
- Private keys (inline)
"""

from __future__ import annotations

import re
from typing import Final

# ── Redaction patterns ────────────────────────────────────────────────────────

PATTERNS: Final[list[tuple[str, str]]] = [
    # Email addresses
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    # API keys: alphanumeric strings of length 16-64 preceded by common prefixes
    (
        r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?key|secret[_-]?key)"
        r"[=:]\s*['\"]?([a-zA-Z0-9_\-/+=]{16,64})['\"]?",
        r"\1=[REDACTED]",
    ),
    # Phone numbers (international and domestic) — must be word-bounded
    (
        r"\b(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "[PHONE]",
    ),
    # Bearer tokens in Authorization headers
    (
        r"(?i)(Bearer\s+)[a-zA-Z0-9\-._~+/]+=*",
        r"\1[REDACTED]",
    ),
    # Passwords in connection strings / URLs
    (
        r"(?i)(password|passwd|pwd)[=:]\s*['\"]?([^\s'\"&]+)['\"]?",
        r"\1=[REDACTED]",
    ),
    # Tokens (generic long alphanumeric strings commonly used as tokens)
    (
        r"(?i)(token|auth[_-]?token|refresh[_-]?token|session[_-]?id)"
        r"[=:]\s*['\"]?([a-zA-Z0-9_\-]{16,128})['\"]?",
        r"\1=[REDACTED]",
    ),
    # JWT tokens (base64url-encoded with dots)
    (
        r"eyJ[a-zA-Z0-9\-_]+\.([a-zA-Z0-9\-_]+\.)[a-zA-Z0-9\-_]+",
        "[JWT_REDACTED]",
    ),
    # SSH private keys (inline)
    (
        r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----.*?"
        r"-----END\s+(?:RSA|DSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----",
        "[PRIVATE_KEY_REDACTED]",
    ),
    # GitHub tokens (ghp_, gho_, ghu_, ghs_, ghf_, etc.)
    (
        r"(?i)(gh[pousrf]_)[a-zA-Z0-9_]{36,}",
        r"\1[REDACTED]",
    ),
    # Slack tokens (xoxb-, xoxp-, xoxa-, xoxr-)
    (
        r"(?i)(xox[baprs]-)[a-zA-Z0-9-]+",
        r"\1[REDACTED]",
    ),
    # Generic base64 secrets (32+ characters ending in = or ==)
    (
        r"[A-Za-z0-9+/]{40,}={1,2}",
        "[BASE64_REDACTED]",
    ),
]


def redact(text: str) -> str:
    """Redact PII, secrets, and tokens from a string.

    Applies all redaction patterns sequentially and returns the
    sanitized text. Use before logging any data that may contain
    sensitive information.

    Args:
        text: The input string to sanitize.

    Returns:
        Sanitized string with sensitive data replaced by placeholders.
    """
    result = text
    for pattern, replacement in PATTERNS:
        try:
            result = re.sub(pattern, replacement, result, flags=re.DOTALL)
        except re.error:
            # If a pattern fails, skip it rather than crashing
            continue
    return result
