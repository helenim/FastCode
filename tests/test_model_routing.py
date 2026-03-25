"""Tests for Phase 6: Tiered model routing — complexity scoring and model selection."""

from unittest.mock import patch

from fastcode.llm_utils import select_model_for_complexity
from fastcode.query_processor import QueryProcessor


class TestComplexityScoring:
    """Test the _compute_complexity method in QueryProcessor."""

    def _make_processor(self):
        config = {
            "query": {
                "expand_query": False,
                "decompose_complex": False,
                "extract_keywords": True,
                "detect_intent": True,
                "use_llm_enhancement": False,
            }
        }
        return QueryProcessor(config)

    def test_simple_find_query_is_low_complexity(self):
        proc = self._make_processor()
        score = proc._compute_complexity("find foo", "find", [], ["foo"])
        assert score < 40

    def test_implementation_query_is_high_complexity(self):
        proc = self._make_processor()
        score = proc._compute_complexity(
            "implement a caching layer with LRU eviction and TTL support",
            "implement", ["cache design", "eviction policy"], ["caching", "LRU", "TTL"],
        )
        assert score > 50

    def test_debug_query_is_medium_high(self):
        proc = self._make_processor()
        score = proc._compute_complexity(
            "debug why the search returns empty results",
            "debug", [], ["search", "empty", "results"],
        )
        assert score > 40

    def test_where_query_is_low(self):
        proc = self._make_processor()
        score = proc._compute_complexity("where is auth", "where", [], ["auth"])
        assert score < 30

    def test_subqueries_increase_complexity(self):
        proc = self._make_processor()
        score_no_sub = proc._compute_complexity("how does X work", "how", [], ["X"])
        score_with_sub = proc._compute_complexity(
            "how does X work", "how", ["what is X", "where is X used"], ["X"],
        )
        assert score_with_sub > score_no_sub

    def test_score_clamped_to_0_100(self):
        proc = self._make_processor()
        # Very simple
        score = proc._compute_complexity("x", "find", [], [])
        assert 0 <= score <= 100
        # Very complex
        score = proc._compute_complexity(
            " ".join(["word"] * 30), "implement",
            ["a", "b", "c", "d"], ["k1", "k2", "k3", "k4", "k5", "k6"],
        )
        assert 0 <= score <= 100


class TestSelectModelForComplexity:
    def _make_config(self, enabled=True, threshold=40):
        return {
            "generation": {
                "routing": {
                    "enabled": enabled,
                    "complexity_threshold": threshold,
                    "fast_model_env": "FAST_MODEL",
                    "strong_model_env": "MODEL",
                }
            }
        }

    def test_disabled_returns_none(self):
        config = self._make_config(enabled=False)
        assert select_model_for_complexity(config, 10) is None

    def test_low_complexity_routes_to_fast(self):
        config = self._make_config(threshold=40)
        with patch.dict("os.environ", {"FAST_MODEL": "haiku", "MODEL": "sonnet"}):
            model = select_model_for_complexity(config, 20)
        assert model == "haiku"

    def test_high_complexity_routes_to_strong(self):
        config = self._make_config(threshold=40)
        with patch.dict("os.environ", {"FAST_MODEL": "haiku", "MODEL": "sonnet"}):
            model = select_model_for_complexity(config, 60)
        assert model == "sonnet"

    def test_missing_fast_model_falls_through(self):
        config = self._make_config(threshold=40)
        with patch.dict("os.environ", {"MODEL": "sonnet"}, clear=False):
            # Remove FAST_MODEL if present
            import os
            os.environ.pop("FAST_MODEL", None)
            model = select_model_for_complexity(config, 20)
        assert model == "sonnet"

    def test_at_threshold_uses_strong(self):
        config = self._make_config(threshold=40)
        with patch.dict("os.environ", {"FAST_MODEL": "haiku", "MODEL": "sonnet"}):
            model = select_model_for_complexity(config, 40)
        assert model == "sonnet"

    def test_just_below_threshold_uses_fast(self):
        config = self._make_config(threshold=40)
        with patch.dict("os.environ", {"FAST_MODEL": "haiku", "MODEL": "sonnet"}):
            model = select_model_for_complexity(config, 39)
        assert model == "haiku"
