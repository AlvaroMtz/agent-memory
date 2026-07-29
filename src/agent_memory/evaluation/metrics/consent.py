"""Consent and privacy metrics — consent coverage, forget completeness, audit trail.

These metrics evaluate consent compliance: what fraction of subjects have
active consent, how completely forget operations succeed, and audit trail integrity.
"""

from __future__ import annotations


def consent_coverage(
    subjects_with_consent: int,
    total_subjects: int,
) -> float:
    """Fraction of subjects with active consent records."""
    if total_subjects == 0:
        return 1.0
    return subjects_with_consent / total_subjects


def consent_grant_rate(
    grants: int,
    total_requests: int,
) -> float:
    """Fraction of consent requests that were granted."""
    if total_requests == 0:
        return 1.0
    return grants / total_requests


def forget_completeness(
    memories_deleted: int,
    memories_targeted: int,
) -> float:
    """Fraction of targeted memories successfully forgotten."""
    if memories_targeted == 0:
        return 1.0
    return memories_deleted / memories_targeted


def audit_integrity(
    auditable_operations: int,
    total_operations: int,
) -> float:
    """Fraction of operations with a valid audit trail entry."""
    if total_operations == 0:
        return 1.0
    return auditable_operations / total_operations
