"""Agent-memory domain exceptions.

All custom exceptions follow a strict hierarchy rooted in MemoryError.
Fail-closed principle: when security/authorization info is missing, raise an error.
"""


class MemoryError(Exception):
    """Base exception for all agent-memory errors."""


# ── Configuration ──────────────────────────────────────────────────────────────


class ConfigurationError(MemoryError):
    """Invalid or missing configuration."""


class EncryptionConfigurationError(ConfigurationError):
    """Encryption provider is not suitable for the current environment."""


# ── Context / Authorization ────────────────────────────────────────────────────


class ContextError(MemoryError):
    """Invalid or missing memory context."""


class MissingTenantError(ContextError):
    """No tenant_id provided."""


class MissingSubjectError(ContextError):
    """No subject_id provided."""


class MissingActorError(ContextError):
    """No actor_id provided."""


class MissingPurposeError(ContextError):
    """No purpose provided."""


class UnauthorizedTenantError(ContextError):
    """tenant_id was provided by an untrusted source (model/tool)."""


# ── Consent ────────────────────────────────────────────────────────────────────


class ConsentError(MemoryError):
    """Consent-related error."""


class ConsentDeniedError(ConsentError):
    """Consent was not granted for this operation."""


class ConsentExpiredError(ConsentError):
    """Consent has expired."""


class ConsentRevokedError(ConsentError):
    """Consent has been revoked."""


class ConsentNotFoundError(ConsentError):
    """No consent record found for the given context and purpose."""


# ── Multi-tenancy ──────────────────────────────────────────────────────────────


class TenantIsolationError(MemoryError):
    """Cross-tenant operation detected or tenant context cannot be established."""


class RLSError(TenantIsolationError):
    """PostgreSQL Row-Level Security context could not be set or verified."""


# ── Extraction / Candidates ────────────────────────────────────────────────────


class ExtractionError(MemoryError):
    """Memory extraction error."""


class EvidenceValidationError(ExtractionError):
    """Candidate evidence is invalid or missing."""


class EvidenceNotFoundError(EvidenceValidationError):
    """evidence_text not found in the source message."""


class SourceMessageNotFoundError(EvidenceValidationError):
    """source_message_id does not reference an existing message."""


class InvalidSourceRoleError(ExtractionError):
    """Message role is not eligible for extraction."""


class LowConfidenceError(ExtractionError):
    """Candidate confidence is below the configured threshold."""


class NotExplicitlyStatedError(ExtractionError):
    """Candidate is not explicitly stated."""


class SensitiveInferenceError(ExtractionError):
    """Candidate appears to infer sensitive attributes."""


# ── Memory ─────────────────────────────────────────────────────────────────────


class MemoryNotFoundError(MemoryError):
    """Memory record not found."""


class VersionNotFoundError(MemoryError):
    """Memory version not found."""


class InvalidMemoryStatusError(MemoryError):
    """Operation not allowed on memory in current status."""


class MemoryExpiredError(MemoryError):
    """Memory has expired and cannot be retrieved."""


class MemoryRevokedError(MemoryError):
    """Memory has been revoked and cannot be retrieved."""


# ── Contradictions ─────────────────────────────────────────────────────────────


class ContradictionError(MemoryError):
    """Contradiction resolution error."""


class AmbiguousCandidateError(ContradictionError):
    """Candidate is ambiguous and requires manual review."""


# ── Encryption ─────────────────────────────────────────────────────────────────


class EncryptionError(MemoryError):
    """Encryption or decryption error."""


class DecryptionError(EncryptionError):
    """Failed to decrypt a payload."""


# ── Retrieval ──────────────────────────────────────────────────────────────────


class RetrievalError(MemoryError):
    """Retrieval error."""


class TokenBudgetExceededError(RetrievalError):
    """Token budget for retrieved context was exceeded."""


# ── Storage / Backend ──────────────────────────────────────────────────────────


class BackendError(MemoryError):
    """Backend storage error."""


class MigrationError(BackendError):
    """Database migration error."""


class SchemaVersionMismatchError(BackendError):
    """Application schema version does not match database schema version."""


# ── Audit ──────────────────────────────────────────────────────────────────────


class AuditError(MemoryError):
    """Audit logging error."""


# ── Plugin ─────────────────────────────────────────────────────────────────────


class PluginError(MemoryError):
    """Plugin discovery or loading error."""


class PluginNotFoundError(PluginError):
    """Requested plugin is not registered."""