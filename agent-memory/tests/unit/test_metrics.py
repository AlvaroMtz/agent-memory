"""Unit tests for evaluation metric calculators."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from agent_memory.evaluation.metrics import (
    consent_coverage,
    consent_grant_rate,
    forget_completeness,
    audit_integrity,
    extraction_f1,
    extraction_precision,
    extraction_recall,
    hit_rate,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestExtractionMetrics:
    def test_precision_perfect(self):
        assert extraction_precision(10, 0) == 1.0

    def test_precision_no_predictions(self):
        assert extraction_precision(0, 0) == 1.0

    def test_precision_half(self):
        assert extraction_precision(5, 5) == 0.5

    def test_precision_zero(self):
        assert extraction_precision(0, 10) == 0.0

    def test_recall_perfect(self):
        assert extraction_recall(10, 0) == 1.0

    def test_recall_no_ground_truth(self):
        assert extraction_recall(0, 0) == 1.0

    def test_recall_half(self):
        assert extraction_recall(5, 5) == 0.5

    def test_recall_zero(self):
        assert extraction_recall(0, 10) == 0.0

    def test_f1_perfect(self):
        assert extraction_f1(1.0, 1.0) == 1.0

    def test_f1_balanced(self):
        assert extraction_f1(0.5, 0.5) == 0.5

    def test_f1_zero(self):
        assert extraction_f1(0.0, 0.0) == 0.0

    def test_f1_harmonic_mean(self):
        result = extraction_f1(0.8, 0.6)
        expected = 2.0 * 0.8 * 0.6 / (0.8 + 0.6)
        assert abs(result - expected) < 1e-10


class TestRetrievalMetrics:
    def test_hit_rate_perfect(self):
        assert hit_rate(10, 10) == 1.0

    def test_hit_rate_none_relevant(self):
        assert hit_rate(3, 0) == 1.0

    def test_hit_rate_half(self):
        assert hit_rate(5, 10) == 0.5

    def test_hit_rate_zero(self):
        assert hit_rate(0, 10) == 0.0

    def test_mrr_all_rank_one(self):
        assert mean_reciprocal_rank([1, 1, 1]) == 1.0

    def test_mrr_mixed(self):
        result = mean_reciprocal_rank([1, 2, 5])
        expected = (1.0 / 1 + 1.0 / 2 + 1.0 / 5) / 3
        assert abs(result - expected) < 1e-10

    def test_mrr_empty(self):
        assert mean_reciprocal_rank([]) == 0.0

    def test_mrr_some_missing(self):
        result = mean_reciprocal_rank([0, 2, 0])
        expected = (1.0 / 2) / 3
        assert abs(result - expected) < 1e-10

    def test_ndcg_at_k_perfect(self):
        assert ndcg_at_k([3, 2, 1], 3) == 1.0

    def test_ndcg_at_k_empty(self):
        assert ndcg_at_k([], 5) == 0.0

    def test_ndcg_at_k_zero_k(self):
        assert ndcg_at_k([3, 2, 1], 0) == 0.0

    def test_ndcg_at_k_partial(self):
        result = ndcg_at_k([3, 0, 0], 3)
        # Only one non-zero relevance, so DCG == IDCG → NDCG = 1.0
        assert result == 1.0

    def test_ndcg_at_k_non_perfect(self):
        result = ndcg_at_k([0, 3, 1], 3)
        # DCG(0,3,1) = 0 + 7/log2(3) + 1/log2(4) ≈ 4.9165
        # IDCG(3,1,0) = 7/log2(2) + 1/log2(3) + 0 ≈ 7.6309
        # NDCG ≈ 0.644
        assert abs(result - 0.6442) < 0.01

    def test_precision_at_k(self):
        assert precision_at_k(3, 10) == 0.3

    def test_precision_at_k_zero_k(self):
        assert precision_at_k(5, 0) == 0.0

    def test_recall_at_k_perfect(self):
        assert recall_at_k(5, 5) == 1.0

    def test_recall_at_k_no_relevant(self):
        assert recall_at_k(0, 0) == 1.0

    def test_recall_at_k_partial(self):
        assert recall_at_k(3, 10) == 0.3


class TestConsentMetrics:
    def test_coverage_perfect(self):
        assert consent_coverage(100, 100) == 1.0

    def test_coverage_no_subjects(self):
        assert consent_coverage(0, 0) == 1.0

    def test_coverage_half(self):
        assert consent_coverage(5, 10) == 0.5

    def test_grant_rate_perfect(self):
        assert consent_grant_rate(10, 10) == 1.0

    def test_grant_rate_no_requests(self):
        assert consent_grant_rate(0, 0) == 1.0

    def test_grant_rate_zero(self):
        assert consent_grant_rate(0, 10) == 0.0

    def test_forget_completeness_perfect(self):
        assert forget_completeness(5, 5) == 1.0

    def test_forget_completeness_none_targeted(self):
        assert forget_completeness(0, 0) == 1.0

    def test_forget_completeness_half(self):
        assert forget_completeness(3, 6) == 0.5

    def test_audit_integrity_perfect(self):
        assert audit_integrity(100, 100) == 1.0

    def test_audit_integrity_no_ops(self):
        assert audit_integrity(0, 0) == 1.0

    def test_audit_integrity_zero(self):
        assert audit_integrity(0, 50) == 0.0