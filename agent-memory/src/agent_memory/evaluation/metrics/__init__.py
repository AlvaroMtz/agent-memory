"""Metric calculators for evaluating memory system quality.

Modules:
    extraction: Precision, recall, F1 for memory extraction.
    retrieval: Hit rate, MRR, NDCG, P@k, R@k for memory retrieval.
    consent: Consent coverage, forget completeness, audit integrity.
"""

from __future__ import annotations

from agent_memory.evaluation.metrics.extraction import (
    extraction_f1,
    extraction_precision,
    extraction_recall,
)
from agent_memory.evaluation.metrics.retrieval import (
    hit_rate,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from agent_memory.evaluation.metrics.consent import (
    consent_coverage,
    consent_grant_rate,
    forget_completeness,
    audit_integrity,
)

__all__ = [
    "extraction_precision",
    "extraction_recall",
    "extraction_f1",
    "hit_rate",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "consent_coverage",
    "consent_grant_rate",
    "forget_completeness",
    "audit_integrity",
]