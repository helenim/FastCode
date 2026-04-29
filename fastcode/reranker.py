"""
Reranking strategies for retrieved code elements.

Supports:
- type_weight: Simple element-type preference weighting (original behavior)
- cross_encoder: Cross-encoder model rescoring for top-N candidates
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Protocol

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """Protocol for reranking strategies."""

    def rerank(
        self, query: str, results: list[dict[str, Any]], top_n: int = 20
    ) -> list[dict[str, Any]]:
        """Rerank results for the given query.

        Args:
            query: The user query.
            results: List of result dicts with "element" and "total_score" keys.
            top_n: Max number of results to rerank (others kept in original order).

        Returns:
            Reranked list of results.
        """
        ...


class TypeWeightReranker:
    """Rerank by element type preference weights.

    This is the original FastCode reranking logic, extracted into its own class.
    """

    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        "function": 1.2,
        "class": 1.1,
        "file": 0.9,
        "documentation": 0.8,
    }

    def __init__(self, type_weights: dict[str, float] | None = None) -> None:
        self._weights = self.DEFAULT_WEIGHTS if type_weights is None else type_weights

    def rerank(
        self, query: str, results: list[dict[str, Any]], top_n: int = 20
    ) -> list[dict[str, Any]]:
        for result in results:
            elem_type = result["element"].get("type", "")
            weight = self._weights.get(elem_type, 1.0)
            result["total_score"] *= weight
            for key in (
                "semantic_score",
                "keyword_score",
                "pseudocode_score",
                "graph_score",
            ):
                if key in result:
                    result[key] *= weight

        results.sort(key=lambda x: x["total_score"], reverse=True)
        return results


class CrossEncoderReranker:
    """Rerank top-N candidates using a cross-encoder model.

    Loads the model lazily on first use to avoid startup cost.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return

        import torch
        from sentence_transformers import CrossEncoder

        if self._device == "auto":
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if torch.backends.mps.is_available()
                else "cpu"
            )
        else:
            device = self._device

        logger.info(
            "Loading cross-encoder model: %s (device=%s)", self._model_name, device
        )
        self._model = CrossEncoder(self._model_name, device=device)

    def rerank(
        self, query: str, results: list[dict[str, Any]], top_n: int = 20
    ) -> list[dict[str, Any]]:
        if not results:
            return results

        self._load_model()

        # Only rerank the top-N candidates
        to_rerank = results[:top_n]
        rest = results[top_n:]

        # Build (query, document) pairs for cross-encoder scoring
        pairs = []
        for result in to_rerank:
            elem = result["element"]
            doc_text = _element_to_text(elem)
            pairs.append((query, doc_text))

        # Score with cross-encoder
        scores = self._model.predict(pairs)

        # Update total_score with cross-encoder score
        for result, ce_score in zip(to_rerank, scores, strict=True):
            result["cross_encoder_score"] = float(ce_score)
            # Blend: keep 30% of original score, 70% cross-encoder
            result["total_score"] = 0.3 * result["total_score"] + 0.7 * float(ce_score)

        to_rerank.sort(key=lambda x: x["total_score"], reverse=True)
        return to_rerank + rest


def create_reranker(config: dict[str, Any]) -> Reranker:
    """Factory: create a reranker from configuration."""
    retrieval_cfg = config.get("retrieval", {})
    reranker_type = retrieval_cfg.get("reranker", "type_weight")

    if reranker_type == "none":
        return TypeWeightReranker(type_weights={})  # No-op (all weights = 1.0)
    elif reranker_type == "type_weight":
        return TypeWeightReranker()
    elif reranker_type == "cross_encoder":
        model = retrieval_cfg.get(
            "cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
        return CrossEncoderReranker(model_name=model)
    else:
        logger.warning(
            "Unknown reranker type: %s, falling back to type_weight", reranker_type
        )
        return TypeWeightReranker()


def _element_to_text(elem: dict[str, Any]) -> str:
    """Convert an element dict to a text string for cross-encoder input."""
    parts = []
    if elem.get("type"):
        parts.append(f"[{elem['type']}]")
    if elem.get("name"):
        parts.append(elem["name"])
    if elem.get("signature"):
        parts.append(elem["signature"])
    if elem.get("docstring"):
        parts.append(elem["docstring"][:500])
    if elem.get("code"):
        parts.append(elem["code"][:1000])
    return " ".join(parts)
