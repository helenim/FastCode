"""
FastCode Evaluation Pipeline.

Provides golden dataset management, retrieval quality metrics,
and an evaluation runner for CI/CD quality gates.
"""

from .golden_dataset import GoldenDataset, GoldenQuery
from .metrics import (
    compute_context_precision,
    compute_mrr,
    compute_ndcg,
    compute_precision_at_k,
    compute_recall_at_k,
)
from .runner import EvaluationRunner

__all__ = [
    "EvaluationRunner",
    "GoldenDataset",
    "GoldenQuery",
    "compute_context_precision",
    "compute_mrr",
    "compute_ndcg",
    "compute_precision_at_k",
    "compute_recall_at_k",
]
