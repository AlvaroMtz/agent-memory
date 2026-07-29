"""Retrieval quality metrics — hit rate, MRR, NDCG, reciprocal rank.

These metrics evaluate retrieval quality: how well the system returns relevant
memories from a query, with position-sensitive scoring.
"""

from __future__ import annotations

import math


def hit_rate(
    relevant_in_results: int,
    total_relevant: int,
) -> float:
    """Hit rate = relevant_in_results / total_relevant.

    The fraction of relevant items that appear in the result set.
    """
    if total_relevant == 0:
        return 1.0
    return relevant_in_results / total_relevant


def mean_reciprocal_rank(
    ranks: list[int],
) -> float:
    """MRR = mean(1 / rank_i).

    Args:
        ranks: List of ranks (1-based) of the first relevant result per query.
               Returns 0.0 for queries with no relevant result (rank=0).

    Returns:
        Mean reciprocal rank across all queries.
    """
    if not ranks:
        return 0.0
    reciprocal_sums = sum(1.0 / r for r in ranks if r > 0)
    return reciprocal_sums / len(ranks)


def ndcg_at_k(
    relevance_scores: list[float],
    k: int,
) -> float:
    """Normalized Discounted Cumulative Gain @ k.

    Args:
        relevance_scores: Relevance scores for the top-k results (ordered).
        k: Cutoff rank.

    Returns:
        NDCG@k in [0.0, 1.0].
    """
    if not relevance_scores or k <= 0:
        return 0.0

    effective_scores = relevance_scores[:k]
    dcg = sum((2**s - 1) / math.log2(i + 2) for i, s in enumerate(effective_scores))

    ideal = sorted(relevance_scores, reverse=True)[:k]
    idcg = sum((2**s - 1) / math.log2(i + 2) for i, s in enumerate(ideal))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def precision_at_k(
    relevant_count: int,
    k: int,
) -> float:
    """Precision@k = relevant_in_top_k / k."""
    if k <= 0:
        return 0.0
    return relevant_count / k


def recall_at_k(
    relevant_in_top_k: int,
    total_relevant: int,
) -> float:
    """Recall@k = relevant_in_top_k / total_relevant."""
    if total_relevant == 0:
        return 1.0
    return relevant_in_top_k / total_relevant
