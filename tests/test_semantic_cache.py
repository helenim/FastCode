"""Tests for the SemanticCache (vector-similarity query caching)."""

import numpy as np
import pytest

from fastcode.cache import SemanticCache


def _random_vec(dim=384, seed=None):
    """Create a random L2-normalized vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _similar_vec(base, noise_scale=0.05, seed=42):
    """Create a vector similar to base (high cosine similarity)."""
    rng = np.random.RandomState(seed)
    noise = rng.randn(*base.shape).astype(np.float32) * noise_scale
    v = base + noise
    v /= np.linalg.norm(v)
    return v


def _make_config(enabled=True, threshold=0.90):
    return {
        "cache": {
            "semantic_cache": {
                "enabled": enabled,
                "similarity_threshold": threshold,
                "max_entries": 100,
                "ttl": 3600,
            }
        }
    }


class TestSemanticCache:
    def test_disabled_returns_none(self):
        cache = SemanticCache(_make_config(enabled=False))
        vec = _random_vec(seed=1)
        cache.store(vec, ["repo"], "result")
        assert cache.lookup(vec, ["repo"]) is None

    def test_store_and_exact_lookup(self):
        cache = SemanticCache(_make_config(threshold=0.95))
        vec = _random_vec(seed=1)
        cache.store(vec, ["repo"], {"answer": "hello"})
        result = cache.lookup(vec, ["repo"])
        assert result == {"answer": "hello"}

    def test_similar_vector_hits(self):
        cache = SemanticCache(_make_config(threshold=0.90))
        vec = _random_vec(seed=1)
        cache.store(vec, ["repo"], "cached_result")

        similar = _similar_vec(vec, noise_scale=0.02)
        sim = float(np.dot(vec, similar))
        assert sim > 0.90  # Sanity: vectors are indeed similar

        result = cache.lookup(similar, ["repo"])
        assert result == "cached_result"

    def test_dissimilar_vector_misses(self):
        cache = SemanticCache(_make_config(threshold=0.90))
        vec1 = _random_vec(seed=1)
        vec2 = _random_vec(seed=99)  # Very different

        cache.store(vec1, ["repo"], "result1")
        result = cache.lookup(vec2, ["repo"])
        assert result is None

    def test_scope_isolation(self):
        """Results in one repo scope should not leak to another."""
        cache = SemanticCache(_make_config(threshold=0.95))
        vec = _random_vec(seed=1)

        cache.store(vec, ["repo_a"], "result_a")
        assert cache.lookup(vec, ["repo_a"]) == "result_a"
        assert cache.lookup(vec, ["repo_b"]) is None

    def test_scope_key_is_sorted(self):
        """["b", "a"] and ["a", "b"] should be the same scope."""
        cache = SemanticCache(_make_config(threshold=0.95))
        vec = _random_vec(seed=1)

        cache.store(vec, ["b", "a"], "result")
        assert cache.lookup(vec, ["a", "b"]) == "result"

    def test_invalidate_specific_scope(self):
        cache = SemanticCache(_make_config(threshold=0.95))
        vec = _random_vec(seed=1)

        cache.store(vec, ["repo_a"], "a")
        cache.store(vec, ["repo_b"], "b")

        cache.invalidate(["repo_a"])
        assert cache.lookup(vec, ["repo_a"]) is None
        assert cache.lookup(vec, ["repo_b"]) == "b"

    def test_invalidate_all(self):
        cache = SemanticCache(_make_config(threshold=0.95))
        vec = _random_vec(seed=1)

        cache.store(vec, ["repo_a"], "a")
        cache.store(vec, ["repo_b"], "b")

        cache.invalidate()
        assert cache.lookup(vec, ["repo_a"]) is None
        assert cache.lookup(vec, ["repo_b"]) is None

    def test_stats(self):
        cache = SemanticCache(_make_config())
        assert cache.stats()["total_entries"] == 0

        vec = _random_vec(seed=1)
        cache.store(vec, ["repo"], "x")

        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["scopes"] == 1

    def test_eviction_on_max_entries(self):
        config = _make_config()
        config["cache"]["semantic_cache"]["max_entries"] = 5
        cache = SemanticCache(config)

        vecs = [_random_vec(seed=i) for i in range(10)]
        for i, v in enumerate(vecs):
            cache.store(v, ["repo"], f"result_{i}")

        # After eviction, most recent entries should still be available
        result = cache.lookup(vecs[-1], ["repo"])
        assert result is not None

    def test_expired_entry_misses(self):
        config = _make_config()
        config["cache"]["semantic_cache"]["ttl"] = 0  # Expire immediately
        cache = SemanticCache(config)

        vec = _random_vec(seed=1)
        cache.store(vec, ["repo"], "expired")

        import time
        time.sleep(0.01)
        result = cache.lookup(vec, ["repo"])
        assert result is None
