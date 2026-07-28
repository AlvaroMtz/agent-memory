"""Extraction quality metrics — precision, recall, and F1 for memory extraction.

These metrics evaluate how well an extractor identifies valid memory candidates
while avoiding false positives.
"""

from __future__ import annotations


def extraction_precision(
    true_positive: int,
    false_positive: int,
) -> float:
    """Precision = TP / (TP + FP).

    Measures what fraction of extracted candidates are correct.
    """
    denominator = true_positive + false_positive
    if denominator == 0:
        return 1.0
    return true_positive / denominator


def extraction_recall(
    true_positive: int,
    false_negative: int,
) -> float:
    """Recall = TP / (TP + FN).

    Measures what fraction of actual memory candidates were found.
    """
    denominator = true_positive + false_negative
    if denominator == 0:
        return 1.0
    return true_positive / denominator


def extraction_f1(
    precision: float,
    recall: float,
) -> float:
    """F1 = 2 * P * R / (P + R).

    Harmonic mean of precision and recall.
    Returns 0.0 when both precision and recall are zero.
    """
    denominator = precision + recall
    if denominator == 0:
        return 0.0
    return 2.0 * precision * recall / denominator