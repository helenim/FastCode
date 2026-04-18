"""Tests for the pickle → JSONL metadata migration.

Covers FINDING-EXT-C-004 (pickle RCE via disk-adjacent attacker). The
load_metadata helper must:
  1. Prefer a `.jsonl` sibling when present.
  2. Fall back to `.pkl` with a DeprecationWarning + critical log.
  3. Auto-migrate a loaded pickle to JSONL and rename the old file to
     `.pkl.legacy` so subsequent scans pick the safe format.
  4. Leave the behavioural interface of VectorStore.save() unchanged
     except that it now writes JSONL.
"""

from __future__ import annotations

import json
import pickle
import warnings
from pathlib import Path

import numpy as np
import pytest

from fastcode.vector_store import (
    _jsonl_path_for,
    load_metadata,
    load_metadata_jsonl,
    save_metadata_jsonl,
)
from fastcode.vector_stores.factory import create_vector_store


@pytest.fixture
def persist_dir(tmp_path: Path) -> Path:
    return tmp_path


def _write_legacy_pickle(path: Path, metadata: list[dict]) -> None:
    payload = {
        "metadata": metadata,
        "dimension": 16,
        "distance_metric": "cosine",
        "index_type": "Flat",
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f)


def test_jsonl_round_trip(persist_dir: Path):
    target = persist_dir / "repo_metadata.jsonl"
    metadata = [
        {"id": "a", "repo_name": "r1", "file_path": "a.py"},
        {"id": "b", "repo_name": "r1", "file_path": "b.py", "score": 0.5},
    ]
    save_metadata_jsonl(
        target,
        metadata,
        dimension=16,
        distance_metric="cosine",
        index_type="Flat",
    )
    assert target.exists()

    loaded = load_metadata_jsonl(target)
    assert loaded["metadata"] == metadata
    assert loaded["dimension"] == 16
    assert loaded["distance_metric"] == "cosine"
    assert loaded["index_type"] == "Flat"


def test_load_metadata_prefers_jsonl_when_present(persist_dir: Path):
    """If both .jsonl and .pkl exist, .jsonl must win (no pickle load)."""
    pkl_path = persist_dir / "repo_metadata.pkl"
    jsonl_path = persist_dir / "repo_metadata.jsonl"

    # Write a .pkl that would look different if we accidentally loaded it.
    _write_legacy_pickle(pkl_path, [{"id": "from-pkl"}])
    save_metadata_jsonl(
        jsonl_path,
        [{"id": "from-jsonl"}],
        dimension=16,
        distance_metric="cosine",
        index_type="Flat",
    )

    data = load_metadata(pkl_path)
    assert data["metadata"] == [{"id": "from-jsonl"}]


def test_pickle_fallback_auto_migrates_and_renames(persist_dir: Path):
    pkl_path = persist_dir / "repo_metadata.pkl"
    jsonl_path = _jsonl_path_for(pkl_path)
    legacy_path = pkl_path.with_suffix(pkl_path.suffix + ".legacy")

    metadata = [
        {"id": "1", "repo_name": "r", "file_path": "a.py"},
        {"id": "2", "repo_name": "r", "file_path": "b.py"},
    ]
    _write_legacy_pickle(pkl_path, metadata)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = load_metadata(pkl_path)
    # DeprecationWarning fired for the legacy format.
    assert any(
        issubclass(w.category, DeprecationWarning) for w in caught
    ), f"expected DeprecationWarning, got: {[str(w.message) for w in caught]}"

    assert data["metadata"] == metadata
    # Auto-migration wrote the .jsonl sibling...
    assert jsonl_path.exists(), "load_metadata should write a .jsonl sibling"
    # ...and renamed the original .pkl so it will not be re-loaded on next scan.
    assert not pkl_path.exists(), ".pkl should have been renamed after migration"
    assert legacy_path.exists(), ".pkl.legacy should exist as a rollback artefact"

    # JSONL content must match the original metadata.
    with open(jsonl_path, encoding="utf-8") as f:
        header = json.loads(f.readline())
        assert header.get("__header__") is True
        records = [json.loads(line) for line in f if line.strip()]
    assert records == metadata


def test_second_load_uses_jsonl_no_warning(persist_dir: Path):
    """After the first load auto-migrates, subsequent loads should use JSONL
    silently (no deprecation warning, no pickle touched)."""
    pkl_path = persist_dir / "repo_metadata.pkl"
    _write_legacy_pickle(pkl_path, [{"id": "x"}])

    # First call triggers migration.
    load_metadata(pkl_path)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = load_metadata(pkl_path)
    assert data["metadata"] == [{"id": "x"}]
    assert not any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_missing_metadata_file_raises(persist_dir: Path):
    with pytest.raises(FileNotFoundError):
        load_metadata(persist_dir / "does_not_exist_metadata.pkl")


def test_vectorstore_save_uses_jsonl(persist_dir: Path):
    """End-to-end: VectorStore.save() writes a .jsonl file, not .pkl."""
    store = create_vector_store(
        {
            "vector_store": {
                "type": "faiss",
                "distance_metric": "cosine",
                "index_type": "Flat",
                "persist_directory": str(persist_dir),
            }
        }
    )
    store.initialize(8)
    rng = np.random.default_rng(7)
    vecs = rng.standard_normal((3, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store.add_vectors(
        vecs,
        [
            {"id": "1", "repo_name": "demo", "file_path": "a.py"},
            {"id": "2", "repo_name": "demo", "file_path": "b.py"},
            {"id": "3", "repo_name": "demo", "file_path": "c.py"},
        ],
    )
    store.save(name="demo")

    assert (persist_dir / "demo.faiss").exists()
    assert (persist_dir / "demo_metadata.jsonl").exists()
    assert not (persist_dir / "demo_metadata.pkl").exists()


def test_vectorstore_load_accepts_legacy_pickle(persist_dir: Path):
    """Load path must still work when only a .pkl exists (back-compat)."""
    import faiss

    # Build a matching FAISS index manually so load() finds both files.
    rng = np.random.default_rng(11)
    vecs = rng.standard_normal((2, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    index = faiss.IndexFlatIP(8)
    index.add(vecs)
    faiss.write_index(index, str(persist_dir / "legacy.faiss"))

    legacy_pkl = persist_dir / "legacy_metadata.pkl"
    _write_legacy_pickle(
        legacy_pkl,
        [
            {"id": "p1", "repo_name": "legacy"},
            {"id": "p2", "repo_name": "legacy"},
        ],
    )

    store = create_vector_store(
        {
            "vector_store": {
                "type": "faiss",
                "distance_metric": "cosine",
                "index_type": "Flat",
                "persist_directory": str(persist_dir),
            }
        }
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert store.load(name="legacy") is True
    assert any(
        issubclass(w.category, DeprecationWarning) for w in caught
    ), "loading a legacy .pkl must emit DeprecationWarning"

    assert len(store.metadata) == 2
    # After load, auto-migration should have produced the .jsonl sibling.
    assert (persist_dir / "legacy_metadata.jsonl").exists()
    assert (persist_dir / "legacy_metadata.pkl.legacy").exists()
