"""Regression tests for VectorStore.delete_by_filter.

Covers FINDING-EXT-C-003 (data loss + cross-tenant leakage): before the
fix, delete_by_filter pruned self.metadata but left self.index untouched,
so search() could return row-ids that referenced deleted — or worse,
wrong-tenant — records.
"""

from __future__ import annotations

import numpy as np

from fastcode.vector_stores.factory import create_vector_store


def _make_store(dim: int = 16, index_type: str = "Flat"):
    store = create_vector_store(
        {
            "vector_store": {
                "type": "faiss",
                "distance_metric": "cosine",
                "index_type": index_type,
                "persist_directory": "/tmp/test_delete_by_filter",
            },
            "evaluation": {"in_memory_index": True},
        }
    )
    store.initialize(dim)
    return store


def _normalized(n: int, dim: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vecs = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


def test_delete_preserves_search_correctness_tenant_isolation():
    """After deleting tenant B, search must never return any tenant B row.

    This is the canonical regression for the cross-tenant leakage bug.
    """
    store = _make_store()
    vecs = _normalized(3, 16, seed=1)
    store.add_vectors(
        vecs,
        [
            {"id": "a", "tenant_id": "A", "repo_name": "repo-a"},
            {"id": "b", "tenant_id": "B", "repo_name": "repo-b"},
            {"id": "c", "tenant_id": "C", "repo_name": "repo-c"},
        ],
    )

    deleted = store.delete_by_filter(lambda m: m.get("tenant_id") == "B")
    assert deleted == 1
    assert len(store.metadata) == 2
    assert store.index.ntotal == 2, (
        "FAISS index must be rebuilt after delete — "
        "pre-fix behaviour left index.ntotal == 3"
    )

    # Query with vecs[1] (the tenant-B vector). If the old bug were
    # present, the search would return B with similarity ~1.0 or would
    # return the wrong-tenant slot at index 1 of the pruned list.
    results = store.search(vecs[1], k=3)
    tenants = {r[0]["tenant_id"] for r in results}
    assert "B" not in tenants, f"Tenant B leaked after deletion: {tenants}"
    assert tenants.issubset({"A", "C"})


def test_delete_multiple_and_empty_survivors():
    store = _make_store()
    vecs = _normalized(4, 16, seed=2)
    store.add_vectors(
        vecs,
        [
            {"id": "1", "tenant_id": "A"},
            {"id": "2", "tenant_id": "A"},
            {"id": "3", "tenant_id": "A"},
            {"id": "4", "tenant_id": "A"},
        ],
    )
    deleted = store.delete_by_filter(lambda m: m.get("tenant_id") == "A")
    assert deleted == 4
    assert store.metadata == []
    assert store.index.ntotal == 0
    assert store.search(vecs[0], k=3) == []


def test_delete_no_match_is_noop():
    store = _make_store()
    vecs = _normalized(2, 16, seed=3)
    store.add_vectors(
        vecs, [{"id": "1", "tenant_id": "A"}, {"id": "2", "tenant_id": "B"}]
    )
    deleted = store.delete_by_filter(lambda m: m.get("tenant_id") == "Z")
    assert deleted == 0
    assert len(store.metadata) == 2
    assert store.index.ntotal == 2


def test_delete_partial_preserves_order_of_survivors():
    store = _make_store()
    vecs = _normalized(5, 16, seed=4)
    store.add_vectors(
        vecs,
        [
            {"id": "keep-1", "tenant_id": "A"},
            {"id": "drop-1", "tenant_id": "B"},
            {"id": "keep-2", "tenant_id": "A"},
            {"id": "drop-2", "tenant_id": "B"},
            {"id": "keep-3", "tenant_id": "A"},
        ],
    )
    store.delete_by_filter(lambda m: m.get("tenant_id") == "B")
    ids = [m["id"] for m in store.metadata]
    assert ids == ["keep-1", "keep-2", "keep-3"]
    assert store.index.ntotal == 3

    # search for the exact survivor vectors and ensure each maps back to
    # the correct metadata row (proves index↔metadata alignment).
    for original_idx in (0, 2, 4):
        results = store.search(vecs[original_idx], k=1)
        assert results, "search should return the self-hit"
        assert results[0][0]["tenant_id"] == "A"


def test_delete_works_for_hnsw_index():
    """HNSW index type exercises the same reconstruct() rebuild path."""
    store = _make_store(index_type="HNSW")
    vecs = _normalized(4, 16, seed=5)
    store.add_vectors(
        vecs,
        [
            {"id": "1", "tenant_id": "A"},
            {"id": "2", "tenant_id": "B"},
            {"id": "3", "tenant_id": "A"},
            {"id": "4", "tenant_id": "B"},
        ],
    )
    store.delete_by_filter(lambda m: m.get("tenant_id") == "B")
    assert store.index.ntotal == 2
    for _meta, _score in store.search(vecs[1], k=5):
        assert _meta["tenant_id"] != "B"


def test_delete_empty_store_is_safe():
    store = _make_store()
    assert store.delete_by_filter(lambda m: True) == 0
