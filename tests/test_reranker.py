"""Tests for retrieval fusion (RRF) and reranker strategies."""

import pytest

from fastcode.reranker import (
    CrossEncoderReranker,
    TypeWeightReranker,
    create_reranker,
    _element_to_text,
)


def _make_result(elem_id: str, name: str, elem_type: str, score: float) -> dict:
    return {
        "element": {"id": elem_id, "name": name, "type": elem_type, "file_path": f"{name}.py"},
        "total_score": score,
        "semantic_score": score * 0.6,
        "keyword_score": score * 0.4,
        "pseudocode_score": 0.0,
        "graph_score": 0.0,
    }


class TestTypeWeightReranker:
    def test_functions_boosted(self):
        reranker = TypeWeightReranker()
        results = [
            _make_result("1", "my_file", "file", 1.0),
            _make_result("2", "my_func", "function", 0.9),
        ]
        reranked = reranker.rerank("query", results)
        # Function (0.9 * 1.2 = 1.08) should outrank file (1.0 * 0.9 = 0.9)
        assert reranked[0]["element"]["name"] == "my_func"

    def test_no_op_with_empty_weights(self):
        reranker = TypeWeightReranker(type_weights={})
        results = [_make_result("1", "a", "function", 0.5)]
        reranked = reranker.rerank("q", results)
        assert reranked[0]["total_score"] == pytest.approx(0.5)


class TestCreateReranker:
    def test_default_is_type_weight(self):
        reranker = create_reranker({})
        assert isinstance(reranker, TypeWeightReranker)

    def test_none_reranker(self):
        reranker = create_reranker({"retrieval": {"reranker": "none"}})
        # none => TypeWeightReranker with empty weights (no-op)
        assert isinstance(reranker, TypeWeightReranker)

    def test_cross_encoder_reranker_created(self):
        reranker = create_reranker({"retrieval": {"reranker": "cross_encoder"}})
        assert isinstance(reranker, CrossEncoderReranker)

    def test_unknown_falls_back(self):
        reranker = create_reranker({"retrieval": {"reranker": "unknown"}})
        assert isinstance(reranker, TypeWeightReranker)


class TestRRFCombine:
    """Test the RRF fusion logic in the retriever."""

    def _make_retriever_config(self, fusion_method="rrf"):
        return {
            "retrieval": {
                "fusion_method": fusion_method,
                "rrf_k": 60,
                "semantic_weight": 0.5,
                "keyword_weight": 0.5,
            }
        }

    def test_rrf_combines_from_multiple_lists(self):
        """Items appearing in both lists get higher RRF scores."""
        from fastcode.retriever import HybridRetriever

        config = self._make_retriever_config("rrf")
        # We can't easily instantiate HybridRetriever without all deps,
        # so test the _rrf_combine method directly via a minimal instance
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.retrieval_config = config["retrieval"]

        semantic = [
            ({"id": "a", "name": "foo"}, 0.9),
            ({"id": "b", "name": "bar"}, 0.7),
        ]
        keyword = [
            ({"id": "b", "name": "bar"}, 15.0),
            ({"id": "c", "name": "baz"}, 10.0),
        ]

        results = retriever._rrf_combine(semantic, keyword)

        # "b" appears in both lists, should have highest score
        scores = {r["element"]["id"]: r["total_score"] for r in results}
        assert scores["b"] > scores["a"]
        assert scores["b"] > scores["c"]

    def test_rrf_is_rank_based_not_score_based(self):
        """RRF should produce the same output regardless of raw score magnitudes."""
        from fastcode.retriever import HybridRetriever

        config = self._make_retriever_config("rrf")
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.retrieval_config = config["retrieval"]

        # Same ranking, different score magnitudes
        semantic1 = [({"id": "a", "name": "a"}, 0.99), ({"id": "b", "name": "b"}, 0.01)]
        semantic2 = [({"id": "a", "name": "a"}, 100.0), ({"id": "b", "name": "b"}, 99.0)]

        results1 = retriever._rrf_combine(semantic1, [])
        results2 = retriever._rrf_combine(semantic2, [])

        # Scores should be identical (rank-based)
        for r1, r2 in zip(results1, results2):
            assert r1["total_score"] == pytest.approx(r2["total_score"])

    def test_weighted_linear_fallback(self):
        """Verify weighted_linear still works when configured."""
        from fastcode.retriever import HybridRetriever

        config = self._make_retriever_config("weighted_linear")
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.retrieval_config = config["retrieval"]
        retriever.semantic_weight = 0.5
        retriever.keyword_weight = 0.5

        semantic = [({"id": "a", "name": "a"}, 0.8)]
        keyword = [({"id": "a", "name": "a"}, 10.0)]

        results = retriever._weighted_linear_combine(semantic, keyword)
        assert len(results) == 1
        assert results[0]["total_score"] > 0

    def test_rrf_handles_empty_lists(self):
        from fastcode.retriever import HybridRetriever

        config = self._make_retriever_config("rrf")
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.retrieval_config = config["retrieval"]

        results = retriever._rrf_combine([], [])
        assert results == []

    def test_rrf_with_pseudocode(self):
        from fastcode.retriever import HybridRetriever

        config = self._make_retriever_config("rrf")
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.retrieval_config = config["retrieval"]

        semantic = [({"id": "a", "name": "a"}, 0.9)]
        keyword = [({"id": "b", "name": "b"}, 5.0)]
        pseudo = [({"id": "a", "name": "a"}, 0.8)]

        results = retriever._rrf_combine(semantic, keyword, pseudo)
        scores = {r["element"]["id"]: r["total_score"] for r in results}
        # "a" in both semantic and pseudocode, "b" only in keyword
        assert scores["a"] > scores["b"]


class TestElementToText:
    def test_basic_conversion(self):
        elem = {"type": "function", "name": "foo", "signature": "def foo(x)"}
        text = _element_to_text(elem)
        assert "function" in text
        assert "foo" in text
        assert "def foo(x)" in text

    def test_truncates_long_content(self):
        elem = {"code": "x" * 5000}
        text = _element_to_text(elem)
        assert len(text) <= 1100  # 1000 code + some overhead
