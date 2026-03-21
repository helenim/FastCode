"""Tests for vector store abstraction and factory."""

import numpy as np
import pytest

from fastcode.vector_stores.factory import create_vector_store
from fastcode.vector_stores.faiss_store import FaissVectorStore


class TestVectorStoreFactory:
    def test_default_creates_faiss(self):
        store = create_vector_store({"vector_store": {}})
        assert isinstance(store, FaissVectorStore)

    def test_explicit_faiss(self):
        store = create_vector_store({"vector_store": {"type": "faiss"}})
        assert isinstance(store, FaissVectorStore)

    def test_unknown_falls_back_to_faiss(self):
        store = create_vector_store({"vector_store": {"type": "unknown"}})
        assert isinstance(store, FaissVectorStore)

    def test_qdrant_type_imports(self):
        """Verify Qdrant backend can be created (without connecting)."""
        from fastcode.vector_stores.qdrant_store import QdrantVectorStore
        store = QdrantVectorStore({"vector_store": {"qdrant": {"url": "http://fake:6333"}}})
        assert store.dimension is None
        assert store._collection_name == "fastcode"


class TestFaissVectorStore:
    """Test FAISS backend via the factory + new interface methods."""

    def _make_store(self, dim=128):
        store = create_vector_store({
            "vector_store": {
                "type": "faiss",
                "distance_metric": "cosine",
                "index_type": "Flat",
                "persist_directory": "/tmp/test_vs",
            },
            "evaluation": {"in_memory_index": True},
        })
        store.initialize(dim)
        return store

    def _random_vectors(self, n, dim=128):
        vecs = np.random.randn(n, dim).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    def test_add_and_search(self):
        store = self._make_store()
        vecs = self._random_vectors(5)
        meta = [
            {"id": f"e{i}", "name": f"elem{i}", "repo_name": "repo1", "type": "function"}
            for i in range(5)
        ]
        store.add_vectors(vecs, meta)

        results = store.search(vecs[0], k=3)
        assert len(results) > 0
        assert results[0][0]["id"] == "e0"  # Most similar to itself
        assert results[0][1] > 0.9  # High similarity

    def test_repo_filter(self):
        store = self._make_store()
        vecs = self._random_vectors(4)
        meta = [
            {"id": "a1", "name": "a", "repo_name": "repo_a", "type": "function"},
            {"id": "a2", "name": "b", "repo_name": "repo_a", "type": "function"},
            {"id": "b1", "name": "c", "repo_name": "repo_b", "type": "function"},
            {"id": "b2", "name": "d", "repo_name": "repo_b", "type": "function"},
        ]
        store.add_vectors(vecs, meta)

        results = store.search(vecs[0], k=10, repo_filter=["repo_b"])
        repo_names = {r[0]["repo_name"] for r in results}
        assert repo_names == {"repo_b"}

    def test_get_count(self):
        store = self._make_store()
        assert store.get_count() == 0
        store.add_vectors(self._random_vectors(3), [
            {"id": f"e{i}", "repo_name": "r"} for i in range(3)
        ])
        assert store.get_count() == 3

    def test_get_repository_names(self):
        store = self._make_store()
        store.add_vectors(self._random_vectors(3), [
            {"id": "1", "repo_name": "alpha"},
            {"id": "2", "repo_name": "beta"},
            {"id": "3", "repo_name": "alpha"},
        ])
        assert store.get_repository_names() == ["alpha", "beta"]

    def test_get_count_by_repository(self):
        store = self._make_store()
        store.add_vectors(self._random_vectors(3), [
            {"id": "1", "repo_name": "alpha"},
            {"id": "2", "repo_name": "beta"},
            {"id": "3", "repo_name": "alpha"},
        ])
        counts = store.get_count_by_repository()
        assert counts["alpha"] == 2
        assert counts["beta"] == 1

    def test_delete_by_repo(self):
        store = self._make_store()
        store.add_vectors(self._random_vectors(3), [
            {"id": "1", "repo_name": "keep"},
            {"id": "2", "repo_name": "delete_me"},
            {"id": "3", "repo_name": "keep"},
        ])
        deleted = store.delete_by_repo("delete_me")
        assert deleted == 1
        assert len(store.metadata) == 2
        assert all(m["repo_name"] == "keep" for m in store.metadata)

    def test_delete_by_files(self):
        store = self._make_store()
        store.add_vectors(self._random_vectors(3), [
            {"id": "1", "repo_name": "repo", "file_path": "a.py"},
            {"id": "2", "repo_name": "repo", "file_path": "b.py"},
            {"id": "3", "repo_name": "repo", "file_path": "c.py"},
        ])
        deleted = store.delete_by_files("repo", ["a.py", "c.py"])
        assert deleted == 2
        assert len(store.metadata) == 1
        assert store.metadata[0]["file_path"] == "b.py"

    def test_clear(self):
        store = self._make_store()
        store.add_vectors(self._random_vectors(3), [{"id": str(i)} for i in range(3)])
        store.clear()
        assert store.get_count() == 0

    def test_search_batch(self):
        store = self._make_store()
        vecs = self._random_vectors(5)
        store.add_vectors(vecs, [{"id": str(i)} for i in range(5)])

        queries = vecs[:2]
        results = store.search_batch(queries, k=2)
        assert len(results) == 2
        assert len(results[0]) == 2

    def test_repo_overview_lifecycle(self):
        store = self._make_store()
        emb = self._random_vectors(1)[0]

        store.save_repo_overview("test_repo", "A test repository", emb, {"summary": "test"})
        overviews = store.load_repo_overviews()
        assert "test_repo" in overviews
        assert overviews["test_repo"]["content"] == "A test repository"

        store.delete_repo_overview("test_repo")
        overviews = store.load_repo_overviews()
        assert "test_repo" not in overviews

    def test_search_repository_overviews(self):
        store = self._make_store()
        emb1 = self._random_vectors(1)[0]
        emb2 = self._random_vectors(1)[0]

        store.save_repo_overview("repo1", "Python ML library", emb1, {})
        store.save_repo_overview("repo2", "JavaScript UI framework", emb2, {})

        results = store.search_repository_overviews(emb1, k=2)
        assert len(results) == 2
        # First result should be most similar to emb1 (itself)
        assert results[0][0]["repo_name"] == "repo1"
