"""Evidence model — verifiable proof that a memory originates from a source."""

from __future__ import annotations

from pydantic import BaseModel


class Evidence(BaseModel):
    """Verifiable evidence that a memory was extracted from a specific source.

    All fields must be exact and verifiable.
    evidence_text must appear literally in the referenced message.
    """

    source_message_id: str
    evidence_text: str
    source_role: str
    message_content: str  # full content for verification

    def evidence_is_literal_substring(self) -> bool:
        """Check that evidence_text appears literally in the message content."""
        return self.evidence_text in self.message_content


class EvidenceValidationResult(BaseModel):
    """Result of validating evidence for a candidate."""

    is_valid: bool
    reason: str | None = None
