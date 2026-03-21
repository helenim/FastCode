"""
Retrieval quality metrics for code search evaluation.

Implements standard IR metrics: NDCG@K, MRR, Precision@K, Recall@K,
and a context precision metric for RAG quality.
"""

from __future__ import annotations

import math
from typing import Any


def compute_ndcg(
    retrieved: list[dict[str, Any]],
    relevant: list[dict[str, str]],
    k: int = 10,
) -> float:
    """Compute Normalized Discounted Cumulative Gain at K.

    Args:
        retrieved: List of retrieved elements (must have "file_path" and "name" keys).
        relevant: List of relevant elements (golden truth).
        k: Cutoff rank.

    Returns:
        NDCG@K score in [0, 1].
    """
    if not relevant:
        return 1.0 if not retrieved else 0.0

    relevant_set = _to_key_set(relevant)
    retrieved_keys = [_element_key(r) for r in retrieved[:k]]

    # DCG: binary relevance (1 if relevant, 0 otherwise)
    dcg = sum(
        1.0 / math.log2(i + 2)  # i+2 because log2(1) = 0
        for i, key in enumerate(retrieved_keys)
        if key in relevant_set
    )

    # Ideal DCG: all relevant items at the top
    ideal_length = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_length))

    if idcg == 0:
        return 0.0

    return dcg / idcg


def compute_mrr(
    retrieved: list[dict[str, Any]],
    relevant: list[dict[str, str]],
) -> float:
    """Compute Mean Reciprocal Rank.

    Returns 1/rank of the first relevant result, or 0 if none found.
    """
    if not relevant:
        return 1.0 if not retrieved else 0.0

    relevant_set = _to_key_set(relevant)

    for i, elem in enumerate(retrieved):
        if _element_key(elem) in relevant_set:
            return 1.0 / (i + 1)

    return 0.0


def compute_precision_at_k(
    retrieved: list[dict[str, Any]],
    relevant: list[dict[str, str]],
    k: int = 10,
) -> float:
    """Compute Precision@K: fraction of top-K results that are relevant."""
    if not retrieved or not relevant:
        return 0.0

    relevant_set = _to_key_set(relevant)
    top_k = retrieved[:k]

    hits = sum(1 for r in top_k if _element_key(r) in relevant_set)
    return hits / len(top_k)


def compute_recall_at_k(
    retrieved: list[dict[str, Any]],
    relevant: list[dict[str, str]],
    k: int = 10,
) -> float:
    """Compute Recall@K: fraction of relevant items found in top-K results."""
    if not relevant:
        return 1.0

    relevant_set = _to_key_set(relevant)
    top_k = retrieved[:k]

    hits = sum(1 for r in top_k if _element_key(r) in relevant_set)
    return hits / len(relevant_set)


def compute_context_precision(
    retrieved: list[dict[str, Any]],
    relevant: list[dict[str, str]],
) -> float:
    """Compute context precision: weighted precision that penalizes irrelevant
    items appearing before relevant ones.

    This approximates RAGAS context precision without requiring an LLM judge.
    Uses the formula: sum(precision@k * rel_k) / total_relevant,
    where rel_k = 1 if item at rank k is relevant.
    """
    if not relevant:
        return 1.0 if not retrieved else 0.0

    relevant_set = _to_key_set(relevant)
    total_relevant = len(relevant_set)

    cumulative_hits = 0
    weighted_sum = 0.0

    for i, elem in enumerate(retrieved):
        if _element_key(elem) in relevant_set:
            cumulative_hits += 1
            # Precision at this rank position
            precision_at_i = cumulative_hits / (i + 1)
            weighted_sum += precision_at_i

    if total_relevant == 0:
        return 0.0

    return weighted_sum / total_relevant


def _element_key(elem: dict[str, Any]) -> tuple[str, str]:
    """Create a hashable key from an element for matching."""
    file_path = elem.get("file_path", "")
    name = elem.get("name", "")
    return (file_path, name)


def _to_key_set(elements: list[dict[str, str]]) -> set[tuple[str, str]]:
    """Convert a list of element dicts to a set of hashable keys."""
    return {_element_key(e) for e in elements}
