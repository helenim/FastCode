"""
Evaluation runner: orchestrates golden dataset evaluation against FastCode.

Runs queries, collects retrieved results, computes metrics, and outputs
a summary report. Designed for CI/CD integration.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .golden_dataset import GoldenDataset, GoldenQuery
from .metrics import (
    compute_context_precision,
    compute_mrr,
    compute_ndcg,
    compute_precision_at_k,
    compute_recall_at_k,
)

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of evaluating a single query."""

    query: str
    intent: str
    difficulty: str
    ndcg_at_5: float
    ndcg_at_10: float
    mrr: float
    precision_at_5: float
    recall_at_5: float
    recall_at_10: float
    context_precision: float
    latency_ms: float
    num_retrieved: int
    num_relevant: int


@dataclass
class EvaluationReport:
    """Aggregated evaluation report."""

    dataset_name: str
    num_queries: int
    mean_ndcg_at_5: float
    mean_ndcg_at_10: float
    mean_mrr: float
    mean_precision_at_5: float
    mean_recall_at_5: float
    mean_recall_at_10: float
    mean_context_precision: float
    mean_latency_ms: float
    per_query: list[QueryResult] = field(default_factory=list)
    per_intent: dict[str, dict[str, float]] = field(default_factory=dict)
    per_difficulty: dict[str, dict[str, float]] = field(default_factory=dict)
    timestamp: str = ""


class EvaluationRunner:
    """Run evaluation against a FastCode instance."""

    def __init__(self, retriever_fn: Any = None, k_values: tuple[int, ...] = (5, 10)):
        """Initialize the runner.

        Args:
            retriever_fn: Callable that takes a query string and returns
                a list of element dicts with at least "file_path" and "name" keys.
                If None, the runner operates in offline mode (for testing metrics only).
            k_values: Tuple of K values for @K metrics.
        """
        self._retrieve = retriever_fn
        self._k_values = k_values

    def evaluate_dataset(self, dataset: GoldenDataset) -> EvaluationReport:
        """Evaluate all queries in a golden dataset.

        Args:
            dataset: The golden dataset to evaluate.

        Returns:
            An EvaluationReport with aggregate and per-query metrics.
        """
        results: list[QueryResult] = []

        for i, gq in enumerate(dataset.queries):
            logger.info(
                "Evaluating query %d/%d: %s",
                i + 1, len(dataset.queries), gq.query[:80],
            )
            result = self._evaluate_query(gq)
            results.append(result)

        report = self._aggregate(dataset.name, results)
        return report

    def evaluate_query(
        self,
        query: str,
        relevant_elements: list[dict[str, str]],
        retrieved_elements: list[dict[str, Any]] | None = None,
    ) -> QueryResult:
        """Evaluate a single query (useful for ad-hoc testing).

        If retrieved_elements is provided, uses those directly.
        Otherwise calls the retriever_fn.
        """
        if retrieved_elements is None:
            if self._retrieve is None:
                msg = "No retriever function provided and no retrieved_elements given"
                raise ValueError(msg)
            start = time.monotonic()
            retrieved_elements = self._retrieve(query)
            latency_ms = (time.monotonic() - start) * 1000
        else:
            latency_ms = 0.0

        return QueryResult(
            query=query,
            intent="unknown",
            difficulty="unknown",
            ndcg_at_5=compute_ndcg(retrieved_elements, relevant_elements, k=5),
            ndcg_at_10=compute_ndcg(retrieved_elements, relevant_elements, k=10),
            mrr=compute_mrr(retrieved_elements, relevant_elements),
            precision_at_5=compute_precision_at_k(retrieved_elements, relevant_elements, k=5),
            recall_at_5=compute_recall_at_k(retrieved_elements, relevant_elements, k=5),
            recall_at_10=compute_recall_at_k(retrieved_elements, relevant_elements, k=10),
            context_precision=compute_context_precision(retrieved_elements, relevant_elements),
            latency_ms=latency_ms,
            num_retrieved=len(retrieved_elements),
            num_relevant=len(relevant_elements),
        )

    def _evaluate_query(self, gq: GoldenQuery) -> QueryResult:
        """Evaluate a single golden query."""
        if self._retrieve is not None:
            start = time.monotonic()
            retrieved = self._retrieve(gq.query)
            latency_ms = (time.monotonic() - start) * 1000
        else:
            retrieved = []
            latency_ms = 0.0

        return QueryResult(
            query=gq.query,
            intent=gq.intent,
            difficulty=gq.difficulty,
            ndcg_at_5=compute_ndcg(retrieved, gq.relevant_elements, k=5),
            ndcg_at_10=compute_ndcg(retrieved, gq.relevant_elements, k=10),
            mrr=compute_mrr(retrieved, gq.relevant_elements),
            precision_at_5=compute_precision_at_k(retrieved, gq.relevant_elements, k=5),
            recall_at_5=compute_recall_at_k(retrieved, gq.relevant_elements, k=5),
            recall_at_10=compute_recall_at_k(retrieved, gq.relevant_elements, k=10),
            context_precision=compute_context_precision(retrieved, gq.relevant_elements),
            latency_ms=latency_ms,
            num_retrieved=len(retrieved),
            num_relevant=len(gq.relevant_elements),
        )

    def _aggregate(self, name: str, results: list[QueryResult]) -> EvaluationReport:
        """Aggregate per-query results into a report."""
        n = len(results)
        if n == 0:
            return EvaluationReport(
                dataset_name=name, num_queries=0,
                mean_ndcg_at_5=0, mean_ndcg_at_10=0, mean_mrr=0,
                mean_precision_at_5=0, mean_recall_at_5=0, mean_recall_at_10=0,
                mean_context_precision=0, mean_latency_ms=0,
            )

        def _mean(attr: str) -> float:
            return sum(getattr(r, attr) for r in results) / n

        # Per-intent breakdown
        per_intent: dict[str, dict[str, float]] = {}
        intent_groups: dict[str, list[QueryResult]] = {}
        for r in results:
            intent_groups.setdefault(r.intent, []).append(r)
        for intent, group in intent_groups.items():
            gn = len(group)
            per_intent[intent] = {
                "count": gn,
                "mean_ndcg_at_10": sum(r.ndcg_at_10 for r in group) / gn,
                "mean_mrr": sum(r.mrr for r in group) / gn,
            }

        # Per-difficulty breakdown
        per_difficulty: dict[str, dict[str, float]] = {}
        diff_groups: dict[str, list[QueryResult]] = {}
        for r in results:
            diff_groups.setdefault(r.difficulty, []).append(r)
        for diff, group in diff_groups.items():
            gn = len(group)
            per_difficulty[diff] = {
                "count": gn,
                "mean_ndcg_at_10": sum(r.ndcg_at_10 for r in group) / gn,
                "mean_mrr": sum(r.mrr for r in group) / gn,
            }

        return EvaluationReport(
            dataset_name=name,
            num_queries=n,
            mean_ndcg_at_5=_mean("ndcg_at_5"),
            mean_ndcg_at_10=_mean("ndcg_at_10"),
            mean_mrr=_mean("mrr"),
            mean_precision_at_5=_mean("precision_at_5"),
            mean_recall_at_5=_mean("recall_at_5"),
            mean_recall_at_10=_mean("recall_at_10"),
            mean_context_precision=_mean("context_precision"),
            mean_latency_ms=_mean("latency_ms"),
            per_query=results,
            per_intent=per_intent,
            per_difficulty=per_difficulty,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    @staticmethod
    def save_report(report: EvaluationReport, path: str | Path) -> None:
        """Save evaluation report to JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "dataset_name": report.dataset_name,
            "num_queries": report.num_queries,
            "mean_ndcg_at_5": round(report.mean_ndcg_at_5, 4),
            "mean_ndcg_at_10": round(report.mean_ndcg_at_10, 4),
            "mean_mrr": round(report.mean_mrr, 4),
            "mean_precision_at_5": round(report.mean_precision_at_5, 4),
            "mean_recall_at_5": round(report.mean_recall_at_5, 4),
            "mean_recall_at_10": round(report.mean_recall_at_10, 4),
            "mean_context_precision": round(report.mean_context_precision, 4),
            "mean_latency_ms": round(report.mean_latency_ms, 2),
            "per_intent": report.per_intent,
            "per_difficulty": report.per_difficulty,
            "timestamp": report.timestamp,
            "per_query": [
                {
                    "query": r.query,
                    "intent": r.intent,
                    "difficulty": r.difficulty,
                    "ndcg_at_10": round(r.ndcg_at_10, 4),
                    "mrr": round(r.mrr, 4),
                    "latency_ms": round(r.latency_ms, 2),
                }
                for r in report.per_query
            ],
        }

        with path.open("w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved evaluation report to %s", path)

    @staticmethod
    def print_report(report: EvaluationReport) -> str:
        """Format evaluation report as a human-readable string."""
        lines = [
            f"Evaluation Report: {report.dataset_name}",
            f"{'=' * 50}",
            f"Queries evaluated: {report.num_queries}",
            "",
            "Aggregate Metrics:",
            f"  NDCG@5:              {report.mean_ndcg_at_5:.4f}",
            f"  NDCG@10:             {report.mean_ndcg_at_10:.4f}",
            f"  MRR:                 {report.mean_mrr:.4f}",
            f"  Precision@5:         {report.mean_precision_at_5:.4f}",
            f"  Recall@5:            {report.mean_recall_at_5:.4f}",
            f"  Recall@10:           {report.mean_recall_at_10:.4f}",
            f"  Context Precision:   {report.mean_context_precision:.4f}",
            f"  Mean Latency (ms):   {report.mean_latency_ms:.1f}",
        ]

        if report.per_intent:
            lines.append("")
            lines.append("By Intent:")
            for intent, stats in sorted(report.per_intent.items()):
                lines.append(
                    f"  {intent:12s}  n={stats['count']:<3.0f}  "
                    f"NDCG@10={stats['mean_ndcg_at_10']:.3f}  "
                    f"MRR={stats['mean_mrr']:.3f}"
                )

        if report.per_difficulty:
            lines.append("")
            lines.append("By Difficulty:")
            for diff, stats in sorted(report.per_difficulty.items()):
                lines.append(
                    f"  {diff:12s}  n={stats['count']:<3.0f}  "
                    f"NDCG@10={stats['mean_ndcg_at_10']:.3f}  "
                    f"MRR={stats['mean_mrr']:.3f}"
                )

        return "\n".join(lines)
