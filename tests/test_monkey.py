"""Monkey / fuzz tests for FastCode — edge cases, oversized inputs, unicode, concurrency."""

import importlib.util as _ilu
import os
import sys
import threading

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Direct module loading (bypass fastcode/__init__.py to avoid heavy deps)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_mod(name: str, rel_path: str):
    spec = _ilu.spec_from_file_location(name, os.path.join(_PROJECT_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_path_utils = _load_mod("fastcode.path_utils", "fastcode/path_utils.py")
PathUtils = _path_utils.PathUtils
file_path_to_module_path = _path_utils.file_path_to_module_path

# VectorStore requires faiss — conditionally import
try:
    import types as _types

    import faiss as _faiss  # noqa: F401

    _fake_utils = _types.ModuleType("fastcode.utils")

    def _ensure_dir(path):
        os.makedirs(path, exist_ok=True)

    _fake_utils.ensure_dir = _ensure_dir  # type: ignore[attr-defined]
    sys.modules.setdefault("fastcode.utils", _fake_utils)

    _vector_store_mod = _load_mod("fastcode.vector_store", "fastcode/vector_store.py")
    VectorStore = _vector_store_mod.VectorStore
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
    VectorStore = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo_dir(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')")
    return str(repo)


@pytest.fixture()
def path_utils(repo_dir):
    return PathUtils(repo_dir)


@pytest.fixture()
def vector_store(tmp_path):
    """Create a VectorStore with some test vectors (requires faiss)."""
    if not HAS_FAISS:
        pytest.skip("faiss not installed")
    config = {
        "vector_store": {
            "persist_directory": str(tmp_path / "vectors"),
            "distance_metric": "cosine",
            "index_type": "Flat",
        }
    }
    vs = VectorStore(config)
    vs.initialize(dimension=64)

    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((10, 64)).astype(np.float32)
    metadata = [
        {"id": f"elem_{i}", "repo_name": "test_repo", "name": f"func_{i}", "type": "function"}
        for i in range(10)
    ]
    vs.add_vectors(vectors, metadata)
    return vs


# ---------------------------------------------------------------------------
# MONKEY-001: Empty / null inputs
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    """Verify graceful handling of empty and null-like inputs."""

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_empty_query_vector(self, vector_store):
        query = np.zeros((1, 64), dtype=np.float32)
        results = vector_store.search(query)
        assert isinstance(results, list)

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_search_empty_store(self, tmp_path):
        config = {"vector_store": {"persist_directory": str(tmp_path / "empty"), "in_memory": True}}
        vs = VectorStore(config)
        results = vs.search(np.zeros((1, 64), dtype=np.float32))
        assert results == []

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_empty_metadata_list(self, vector_store):
        vectors = np.random.default_rng(0).standard_normal((5, 64)).astype(np.float32)
        with pytest.raises(ValueError):
            vector_store.add_vectors(vectors, [])

    def test_path_utils_empty_path(self, path_utils):
        result = path_utils.resolve_path("")
        assert result == path_utils.repo_root

    def test_path_utils_dot_path(self, path_utils):
        result = path_utils.resolve_path(".")
        assert result == path_utils.repo_root

    def test_file_path_to_module_empty_file(self, repo_dir):
        result = file_path_to_module_path("", repo_dir)
        assert result is None

    def test_file_path_to_module_empty_repo(self):
        result = file_path_to_module_path("/some/file.py", "")
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# MONKEY-002: Oversized inputs
# ---------------------------------------------------------------------------


class TestOversizedInputs:
    """Verify the system handles unusually large inputs without crashing."""

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_large_query_vector(self, vector_store):
        query = np.full((1, 64), 1e10, dtype=np.float32)
        results = vector_store.search(query)
        assert isinstance(results, list)

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_many_vectors(self, tmp_path):
        config = {"vector_store": {"persist_directory": str(tmp_path / "big"), "in_memory": True}}
        vs = VectorStore(config)
        vs.initialize(64)
        rng = np.random.default_rng(42)
        vectors = rng.standard_normal((1000, 64)).astype(np.float32)
        metadata = [{"id": f"e_{i}", "repo_name": "r"} for i in range(1000)]
        vs.add_vectors(vectors, metadata)
        assert vs.get_count() == 1000

    def test_long_path(self, path_utils):
        long_path = "/".join(["a"] * 500)
        result = path_utils.is_safe_path(long_path)
        assert isinstance(result, bool)

    def test_long_file_path_to_module(self, repo_dir):
        long_path = os.path.join(repo_dir, "/".join(["dir"] * 200), "mod.py")
        result = file_path_to_module_path(long_path, repo_dir)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# MONKEY-003: Unicode edge cases
# ---------------------------------------------------------------------------


class TestUnicodeEdgeCases:
    """Verify unicode handling in paths and queries."""

    def test_emoji_in_path(self, path_utils):
        result = path_utils.is_safe_path("src/\U0001f600/main.py")
        assert isinstance(result, bool)

    def test_cjk_in_path(self, path_utils):
        result = path_utils.is_safe_path("src/\u4e2d\u6587/main.py")
        assert isinstance(result, bool)

    def test_rtl_in_path(self, path_utils):
        result = path_utils.is_safe_path("src/\u0627\u0644\u0639\u0631\u0628\u064a\u0629/main.py")
        assert isinstance(result, bool)

    def test_combining_characters(self, path_utils):
        result = path_utils.is_safe_path("src/te\u0301st/main.py")
        assert isinstance(result, bool)

    def test_null_byte_in_path(self, path_utils):
        result = path_utils.is_safe_path("src/\x00main.py")
        assert isinstance(result, bool)

    def test_unicode_module_path(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo, exist_ok=True)
        result = file_path_to_module_path(os.path.join(repo, "\u00e9\u00e8\u00ea.py"), repo)
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# MONKEY-004: Injection patterns (should be treated as literal text)
# ---------------------------------------------------------------------------


class TestInjectionPatterns:
    """Verify injection patterns are treated as literal text, not executed."""

    @pytest.mark.parametrize("injection", [
        "'; DROP TABLE users; --",
        '" OR 1=1 --',
        "<script>alert('xss')</script>",
        "{{7*7}}",
        "${7*7}",
        "__import__('os').system('rm -rf /')",
        "; cat /etc/passwd",
        "| ls -la",
        "$(whoami)",
        "`whoami`",
    ])
    def test_injection_in_path(self, path_utils, injection):
        result = path_utils.is_safe_path(injection)
        assert isinstance(result, bool)

    @pytest.mark.parametrize("injection", [
        "'; DROP TABLE users; --",
        "__import__('os').system('rm -rf /')",
        "{{config.__class__.__init__.__globals__}}",
    ])
    def test_injection_in_module_path(self, repo_dir, injection):
        result = file_path_to_module_path(os.path.join(repo_dir, injection + ".py"), repo_dir)
        assert result is None or isinstance(result, str)

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    @pytest.mark.parametrize("injection", [
        "'; DROP TABLE users; --",
        "a" * 100000,
        "\x00\x01\x02\x03",
        "\U0001f600\U0001f525\U0001f4a5",
    ])
    def test_injection_in_repo_filter(self, vector_store, injection):
        query = np.random.default_rng(99).standard_normal((1, 64)).astype(np.float32)
        results = vector_store.search(query, repo_filter=[injection])
        assert isinstance(results, list)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# MONKEY-005: Concurrent access
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    """Verify thread-safety of core components."""

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_concurrent_vector_search(self, vector_store):
        errors = []
        results_count = []

        def search_worker(seed):
            try:
                rng = np.random.default_rng(seed)
                query = rng.standard_normal((1, 64)).astype(np.float32)
                results = vector_store.search(query, k=5)
                results_count.append(len(results))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=search_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent search errors: {errors}"
        assert len(results_count) == 10

    def test_concurrent_path_resolution(self, path_utils):
        errors = []
        results = []
        paths = [".", "main.py", "nonexistent", "../..", "src"]

        def resolve_worker(p):
            try:
                r = path_utils.resolve_path(p)
                results.append((p, r))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=resolve_worker, args=(p,)) for p in paths * 3]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Concurrent path resolution errors: {errors}"
        assert len(results) == 15


# ---------------------------------------------------------------------------
# MONKEY-006: VectorStore edge cases
# ---------------------------------------------------------------------------


class TestVectorStoreEdgeCases:
    """Additional edge cases for VectorStore."""

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_search_k_larger_than_store(self, vector_store):
        query = np.random.default_rng(0).standard_normal((1, 64)).astype(np.float32)
        results = vector_store.search(query, k=1000)
        assert len(results) <= 10

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_nan_query_vector(self, vector_store):
        query = np.full((1, 64), np.nan, dtype=np.float32)
        results = vector_store.search(query)
        assert isinstance(results, list)

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_inf_query_vector(self, vector_store):
        query = np.full((1, 64), np.inf, dtype=np.float32)
        results = vector_store.search(query)
        assert isinstance(results, list)

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_save_and_load_roundtrip(self, vector_store):
        vector_store.save("test_index")
        config = {
            "vector_store": {
                "persist_directory": vector_store.persist_dir,
                "distance_metric": "cosine",
                "index_type": "Flat",
            }
        }
        vs2 = VectorStore(config)
        loaded = vs2.load("test_index")
        assert loaded is True
        assert vs2.get_count() == 10

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_clear_and_reinitialize(self, vector_store):
        assert vector_store.get_count() == 10
        vector_store.clear()
        assert vector_store.get_count() == 0

    @pytest.mark.skipif(not HAS_FAISS, reason="faiss not installed")
    def test_batch_search(self, vector_store):
        queries = np.random.default_rng(0).standard_normal((5, 64)).astype(np.float32)
        results = vector_store.search_batch(queries, k=3)
        assert len(results) == 5
        for r in results:
            assert isinstance(r, list)
