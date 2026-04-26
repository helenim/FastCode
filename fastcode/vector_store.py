"""
Vector Store - Store and retrieve code embeddings
"""

import json
import logging
import os
import pickle
import warnings
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from .tenant_context import current_tenant_id
from .utils import ensure_dir

# ---------------------------------------------------------------------------
# Metadata serialization helpers (JSONL replacement for pickle).
#
# Historical format: `{repo}_metadata.pkl` containing a dict with keys
#   {"metadata": list[dict], "dimension": int, "distance_metric": str,
#    "index_type": str}
# New format: `{repo}_metadata.jsonl` — one JSON record per line.
#   Line 0: header dict with keys {"__header__": True, "dimension": int,
#           "distance_metric": str, "index_type": str, "count": int}
#   Lines 1..N: one metadata dict per vector (same shape as before).
# ---------------------------------------------------------------------------

_PICKLE_DEPRECATION_MSG = (
    "Loading vector-store metadata from pickle is deprecated due to the "
    "pickle RCE risk (arbitrary code execution on attacker-controlled files). "
    "The file will be auto-migrated to JSONL. See FINDING-EXT-C-004."
)


def _jsonl_path_for(pkl_path: str | os.PathLike) -> Path:
    """Return the sibling .jsonl path for a given .pkl metadata path."""
    p = Path(pkl_path)
    if p.suffix == ".pkl":
        return p.with_suffix(".jsonl")
    # generic fallback: append .jsonl
    return p.parent / (p.name + ".jsonl")


def _metadata_to_jsonable(meta: Any) -> Any:
    """Best-effort coercion of a metadata value to a JSON-safe representation.

    Handles numpy scalars (converted via .item()) and ndarray (converted to
    list). Falls back to str() for unknown types so a migration never fails
    on a single bad row; a warning is logged by the caller if coercion
    happens.
    """
    if isinstance(meta, dict):
        return {str(k): _metadata_to_jsonable(v) for k, v in meta.items()}
    if isinstance(meta, (list, tuple)):
        return [_metadata_to_jsonable(v) for v in meta]
    if isinstance(meta, (str, int, float, bool)) or meta is None:
        return meta
    # numpy scalar types expose .item()
    if hasattr(meta, "item") and callable(meta.item):
        try:
            return meta.item()
        except Exception:
            pass
    if isinstance(meta, np.ndarray):
        return meta.tolist()
    # final fallback: stringify
    return str(meta)


def save_metadata_jsonl(
    jsonl_path: str | os.PathLike,
    metadata: list[dict[str, Any]],
    *,
    dimension: int | None,
    distance_metric: str,
    index_type: str,
) -> None:
    """Write metadata to JSONL (header + one record per vector).

    Writes atomically via a tmp file + rename so a crash mid-write cannot
    leave a partially-written file.
    """
    path = Path(jsonl_path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    header = {
        "__header__": True,
        "dimension": dimension,
        "distance_metric": distance_metric,
        "index_type": index_type,
        "count": len(metadata),
    }
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for meta in metadata:
            f.write(
                json.dumps(_metadata_to_jsonable(meta), ensure_ascii=False) + "\n"
            )
    os.replace(tmp, path)


def load_metadata_jsonl(jsonl_path: str | os.PathLike) -> dict[str, Any]:
    """Read a JSONL metadata file and return the same shape the old pickle
    wrapper produced: {"metadata": [...], "dimension": ..., "distance_metric":
    ..., "index_type": ...}.
    """
    path = Path(jsonl_path)
    metadata: list[dict[str, Any]] = []
    header: dict[str, Any] = {}
    with open(path, encoding="utf-8") as f:
        first = f.readline()
        if not first:
            return {
                "metadata": [],
                "dimension": None,
                "distance_metric": "cosine",
                "index_type": "HNSW",
            }
        parsed = json.loads(first)
        if isinstance(parsed, dict) and parsed.get("__header__"):
            header = parsed
        else:
            # No header — treat first line as a data row (tolerant mode).
            metadata.append(parsed)
        for line in f:
            line = line.strip()
            if not line:
                continue
            metadata.append(json.loads(line))
    return {
        "metadata": metadata,
        "dimension": header.get("dimension"),
        "distance_metric": header.get("distance_metric", "cosine"),
        "index_type": header.get("index_type", "HNSW"),
    }


def load_metadata(
    pkl_path: str | os.PathLike,
    *,
    logger: logging.Logger | None = None,
    auto_migrate: bool = True,
) -> dict[str, Any]:
    """Load metadata from disk, preferring JSONL and falling back to pickle.

    If the .jsonl sibling exists it is used directly. Otherwise the .pkl file
    is loaded with a CRITICAL log + DeprecationWarning (tracks metric
    ``fastcode_metadata_pickle_load_total``). On a successful pickle load,
    the data is auto-migrated to JSONL and the old file is renamed to
    ``.pkl.legacy`` so subsequent scans prefer the safe format.

    Returns a dict with keys {"metadata", "dimension", "distance_metric",
    "index_type"} regardless of source format.
    """
    logger = logger or logging.getLogger(__name__)
    jsonl_path = _jsonl_path_for(pkl_path)

    if jsonl_path.exists():
        return load_metadata_jsonl(jsonl_path)

    pkl = Path(pkl_path)
    if not pkl.exists():
        raise FileNotFoundError(f"No metadata file found: {pkl_path} or {jsonl_path}")

    # Legacy pickle path — emit loud deprecation signals.
    logger.critical(
        "fastcode.metadata.pickle_load.deprecated",
        extra={
            "event": "fastcode.metadata.pickle_load.deprecated",
            "metric": "fastcode_metadata_pickle_load_total",
            "path": str(pkl),
        },
    )
    warnings.warn(_PICKLE_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)

    with open(pkl, "rb") as f:
        data = pickle.load(f)  # nosec B301 - legacy read-only path, see FINDING-EXT-C-004

    if not isinstance(data, dict) or "metadata" not in data:
        raise ValueError(
            f"Unexpected pickle payload in {pkl}: expected dict with 'metadata' key"
        )

    if auto_migrate:
        try:
            save_metadata_jsonl(
                jsonl_path,
                data.get("metadata", []),
                dimension=data.get("dimension"),
                distance_metric=data.get("distance_metric", "cosine"),
                index_type=data.get("index_type", "HNSW"),
            )
            legacy = pkl.with_suffix(pkl.suffix + ".legacy")
            os.replace(pkl, legacy)
            logger.warning(
                "fastcode.metadata.pickle_load.migrated",
                extra={
                    "event": "fastcode.metadata.pickle_load.migrated",
                    "legacy_path": str(legacy),
                    "jsonl_path": str(jsonl_path),
                },
            )
        except Exception as exc:
            logger.error(
                "fastcode.metadata.pickle_load.migration_failed",
                extra={
                    "event": "fastcode.metadata.pickle_load.migration_failed",
                    "error": str(exc),
                },
            )
    return data


class VectorStore:
    """Vector database for code embeddings using FAISS"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.vector_config = config.get("vector_store", {})
        self.logger = logging.getLogger(__name__)

        # Evaluation mode can request a purely in-memory index that never touches disk.
        self.in_memory = self.vector_config.get(
            "in_memory",
            config.get("evaluation", {}).get("in_memory_index", False),
        )
        # Keep repo overviews in-memory when persistence is disabled.
        self._in_memory_repo_overviews: dict[str, dict[str, Any]] = {}

        self.dimension = None
        self.index = None
        self.metadata = []  # Store metadata for each vector

        self.persist_dir = self.vector_config.get(
            "persist_directory", "./data/vector_store"
        )
        self.distance_metric = self.vector_config.get("distance_metric", "cosine")
        self.index_type = self.vector_config.get("index_type", "HNSW")

        # HNSW parameters
        self.m = self.vector_config.get("m", 16)
        self.ef_construction = self.vector_config.get("ef_construction", 200)
        self.ef_search = self.vector_config.get("ef_search", 50)

        # Cache for scan_available_indexes to avoid repeated file I/O
        self._index_scan_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._index_scan_cache_ttl = self.vector_config.get(
            "index_scan_cache_ttl", 30.0
        )
        self._index_scan_sample_size = self.vector_config.get(
            "index_scan_sample_size", 100
        )

        if not self.in_memory:
            ensure_dir(self.persist_dir)
        else:
            self.logger.info(
                "VectorStore running in in-memory mode; persistence disabled."
            )

    # ------------------------------------------------------------------
    # Tenant-scoped artifact paths
    # ------------------------------------------------------------------
    def _tenant_dir(self) -> str:
        """Return the artifact directory for the active tenant.

        Resolves to ``<persist_dir>/<tenant_id>/`` and ensures the directory
        exists. ``tenant_id`` is read from the request-scoped contextvar in
        ``fastcode.tenant_context`` (falls back to the ``EBRIDGE_TENANT_ID``
        env var, then to the workspace-default ``"_default"``).
        """
        tenant = current_tenant_id()
        path = os.path.join(self.persist_dir, tenant)
        if not self.in_memory:
            ensure_dir(path)
        return path

    def initialize(self, dimension: int):
        """
        Initialize the vector store

        Args:
            dimension: Dimension of embedding vectors
        """
        self.dimension = dimension
        self.logger.info(f"Initializing vector store with dimension {dimension}")

        if self.index_type == "HNSW":
            # HNSW index for fast approximate search
            if self.distance_metric == "cosine":
                # Use inner product for cosine with normalized vectors
                index = faiss.IndexHNSWFlat(
                    dimension, self.m, faiss.METRIC_INNER_PRODUCT
                )
            else:
                # L2 distance
                index = faiss.IndexHNSWFlat(dimension, self.m, faiss.METRIC_L2)

            index.hnsw.efConstruction = self.ef_construction
            index.hnsw.efSearch = self.ef_search
            self.index = index

        else:
            # Flat index for exact search (slower but more accurate)
            if self.distance_metric == "cosine":
                self.index = faiss.IndexFlatIP(dimension)  # Inner product
            else:
                self.index = faiss.IndexFlatL2(dimension)  # L2 distance

        self.metadata = []
        self.logger.info(
            f"Initialized {self.index_type} index with {self.distance_metric} distance"
        )

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict[str, Any]]):
        """
        Add vectors to the store

        Args:
            vectors: Array of embedding vectors (N x dimension)
            metadata: List of metadata dictionaries for each vector
        """
        if self.index is None:
            raise RuntimeError("Vector store not initialized")

        if len(vectors) != len(metadata):
            raise ValueError("Number of vectors must match number of metadata entries")

        # Ensure vectors are float32
        vectors = vectors.astype(np.float32)

        # Normalize if using cosine similarity
        if self.distance_metric == "cosine":
            faiss.normalize_L2(vectors)

        # Add to index
        self.index.add(vectors)
        self.metadata.extend(metadata)

        self.logger.info(
            f"Added {len(vectors)} vectors to store (total: {len(self.metadata)})"
        )

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        min_score: float | None = None,
        repo_filter: list[str] | None = None,
        element_type_filter: str | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Search for similar vectors

        Args:
            query_vector: Query embedding vector
            k: Number of results to return
            min_score: Minimum similarity score (optional)
            repo_filter: Optional list of repository names to filter by
            element_type_filter: Optional element type to filter by (e.g., "repository_overview")

        Returns:
            List of (metadata, score) tuples
        """
        if self.index is None or len(self.metadata) == 0:
            return []

        # Ensure query is float32 and 2D
        query_vector = query_vector.astype(np.float32).reshape(1, -1)

        # Normalize if using cosine similarity
        if self.distance_metric == "cosine":
            faiss.normalize_L2(query_vector)

        # Search with larger k only for element_type_filter (not repo_filter)
        # Note: repo_filter now uses reloaded indexes, so no need to multiply k
        search_k = k * 5 if element_type_filter else k
        search_k = min(search_k, len(self.metadata))
        distances, indices = self.index.search(query_vector, search_k)

        # Prepare results
        results = []
        for dist, idx in zip(distances[0], indices[0], strict=False):
            if idx == -1:  # FAISS returns -1 for empty slots
                continue

            # Apply repository filter
            if repo_filter:
                repo_name = self.metadata[idx].get("repo_name")
                if repo_name not in repo_filter:
                    continue

            # Apply element type filter
            if element_type_filter:
                elem_type = self.metadata[idx].get("type")
                if elem_type != element_type_filter:
                    continue

            # Convert distance to similarity score
            if self.distance_metric == "cosine":
                score = float(dist)  # Inner product (already similarity)
            else:
                # Convert L2 distance to similarity
                score = 1.0 / (1.0 + float(dist))

            # Filter by minimum score
            if min_score is not None and score < min_score:
                continue

            results.append((self.metadata[idx], score))

            # Stop if we have enough results
            if len(results) >= k:
                break

        return results

    def save_repo_overview(
        self,
        repo_name: str,
        overview_content: str,
        embedding: np.ndarray,
        metadata: dict[str, Any],
    ):
        """
        Save a single repository overview to a separate file

        Args:
            repo_name: Name of the repository
            overview_content: Text content of the overview
            embedding: Embedding vector for the overview
            metadata: Additional metadata (repo_url, summary, structure, etc.)
        """
        if self.in_memory:
            # Keep entirely in memory during evaluation.
            self._in_memory_repo_overviews[repo_name] = {
                "repo_name": repo_name,
                "content": overview_content,
                "embedding": embedding.astype(np.float32),
                "metadata": metadata,
            }
            self.logger.info(f"Stored repository overview for {repo_name} (in-memory)")
            return

        overview_path = os.path.join(self._tenant_dir(), "repo_overviews.pkl")

        # Load existing overviews if they exist
        overviews = {}
        if os.path.exists(overview_path):
            try:
                with open(overview_path, "rb") as f:
                    overviews = pickle.load(f)  # nosec B301
            except Exception as e:
                self.logger.warning(f"Failed to load existing repo overviews: {e}")

        # Add/update this repository's overview
        overviews[repo_name] = {
            "repo_name": repo_name,
            "content": overview_content,
            "embedding": embedding.astype(np.float32),
            "metadata": metadata,
        }

        # Save back to file
        try:
            with open(overview_path, "wb") as f:
                pickle.dump(overviews, f)
            self.logger.info(f"Saved repository overview for {repo_name}")
        except Exception as e:
            self.logger.error(f"Failed to save repository overview: {e}")

    def delete_repo_overview(self, repo_name: str) -> bool:
        """
        Delete a repository overview from storage

        Args:
            repo_name: Name of the repository to remove

        Returns:
            True if the overview was found and removed
        """
        if self.in_memory:
            if repo_name in self._in_memory_repo_overviews:
                del self._in_memory_repo_overviews[repo_name]
                self.logger.info(f"Deleted in-memory overview for {repo_name}")
                return True
            return False

        overview_path = os.path.join(self._tenant_dir(), "repo_overviews.pkl")
        if not os.path.exists(overview_path):
            return False

        try:
            with open(overview_path, "rb") as f:
                overviews = pickle.load(f)  # nosec B301

            if repo_name not in overviews:
                return False

            del overviews[repo_name]

            with open(overview_path, "wb") as f:
                pickle.dump(overviews, f)
            self.logger.info(f"Deleted repository overview for {repo_name}")
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to delete repository overview for {repo_name}: {e}"
            )
            return False

    def load_repo_overviews(self) -> dict[str, dict[str, Any]]:
        """
        Load all repository overviews from storage

        Returns:
            Dictionary mapping repo_name to overview data
        """
        if self.in_memory:
            # Return the in-memory overviews when persistence is disabled.
            return self._in_memory_repo_overviews

        overview_path = os.path.join(self._tenant_dir(), "repo_overviews.pkl")

        if not os.path.exists(overview_path):
            self.logger.info("No repository overviews found")
            return {}

        try:
            with open(overview_path, "rb") as f:
                overviews = pickle.load(f)  # nosec B301
            self.logger.info(f"Loaded {len(overviews)} repository overviews")
            return overviews
        except Exception as e:
            self.logger.error(f"Failed to load repository overviews: {e}")
            return {}

    def search_repository_overviews(
        self, query_vector: np.ndarray, k: int = 5, min_score: float | None = None
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Search specifically for repository overview elements using separate storage

        Args:
            query_vector: Query embedding vector
            k: Number of repositories to return
            min_score: Minimum similarity score

        Returns:
            List of (metadata, score) tuples for repository overviews only
        """
        overviews = self.load_repo_overviews()

        if not overviews:
            self.logger.warning("No repository overviews available for search")
            return []

        # Ensure query is float32 and normalized
        query_vector = query_vector.astype(np.float32).reshape(1, -1)
        if self.distance_metric == "cosine":
            faiss.normalize_L2(query_vector)

        # Calculate similarities with all repo overviews
        results = []
        for repo_name, overview_data in overviews.items():
            embedding = overview_data["embedding"].reshape(1, -1)

            # Normalize embedding if using cosine
            if self.distance_metric == "cosine":
                faiss.normalize_L2(embedding)

            # Calculate similarity
            if self.distance_metric == "cosine":
                # Inner product (cosine similarity for normalized vectors)
                similarity = float(np.dot(query_vector, embedding.T)[0, 0])
            else:
                # L2 distance converted to similarity
                distance = float(np.linalg.norm(query_vector - embedding))
                similarity = 1.0 / (1.0 + distance)

            self.logger.debug(
                f"Repository overview similarity for {repo_name}: {similarity:.4f}"
            )

            # Apply minimum score filter
            if min_score is not None and similarity < min_score:
                continue

            # Prepare metadata for result
            result_metadata = {
                "repo_name": repo_name,
                "type": "repository_overview",
                **overview_data["metadata"],
            }

            results.append((result_metadata, similarity))

        # Sort by similarity and return top k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def search_batch(
        self, query_vectors: np.ndarray, k: int = 10, min_score: float | None = None
    ) -> list[list[tuple[dict[str, Any], float]]]:
        """
        Search for multiple queries at once

        Args:
            query_vectors: Array of query vectors (N x dimension)
            k: Number of results per query
            min_score: Minimum similarity score

        Returns:
            List of result lists (one per query)
        """
        if self.index is None or len(self.metadata) == 0:
            return [[] for _ in range(len(query_vectors))]

        # Ensure float32
        query_vectors = query_vectors.astype(np.float32)

        # Normalize if using cosine
        if self.distance_metric == "cosine":
            faiss.normalize_L2(query_vectors)

        # Search
        k = min(k, len(self.metadata))
        distances, indices = self.index.search(query_vectors, k)

        # Prepare results for each query
        all_results = []
        for query_distances, query_indices in zip(distances, indices, strict=False):
            results = []
            for dist, idx in zip(query_distances, query_indices, strict=False):
                if idx == -1:
                    continue

                # Convert distance to score
                if self.distance_metric == "cosine":
                    score = float(dist)
                else:
                    score = 1.0 / (1.0 + float(dist))

                if min_score is not None and score < min_score:
                    continue

                results.append((self.metadata[idx], score))

            all_results.append(results)

        return all_results

    def get_count(self) -> int:
        """Get number of vectors in store"""
        return len(self.metadata)

    def get_repository_names(self) -> list[str]:
        """Get list of unique repository names in the store"""
        repo_names = set()
        for meta in self.metadata:
            repo_name = meta.get("repo_name")
            if repo_name:
                repo_names.add(repo_name)
        return sorted(list(repo_names))

    def get_count_by_repository(self) -> dict[str, int]:
        """Get count of vectors per repository"""
        repo_counts = {}
        for meta in self.metadata:
            repo_name = meta.get("repo_name", "unknown")
            repo_counts[repo_name] = repo_counts.get(repo_name, 0) + 1
        return repo_counts

    def filter_by_repositories(self, repo_names: list[str]) -> list[int]:
        """
        Get indices of vectors belonging to specific repositories

        Args:
            repo_names: List of repository names to filter by

        Returns:
            List of indices
        """
        indices = []
        for i, meta in enumerate(self.metadata):
            if meta.get("repo_name") in repo_names:
                indices.append(i)
        return indices

    def save(self, name: str = "index"):
        """
        Save index and metadata to disk

        Args:
            name: Name for the saved files
        """
        if self.in_memory:
            self.logger.info("Skipping vector store save (in-memory mode enabled)")
            return

        if self.index is None:
            self.logger.warning("No index to save")
            return

        tenant_dir = self._tenant_dir()
        index_path = os.path.join(tenant_dir, f"{name}.faiss")
        metadata_path = os.path.join(tenant_dir, f"{name}_metadata.jsonl")

        # Save FAISS index
        faiss.write_index(self.index, index_path)

        # Save metadata as JSONL (see FINDING-EXT-C-004 for migration away
        # from pickle).
        save_metadata_jsonl(
            metadata_path,
            self.metadata,
            dimension=self.dimension,
            distance_metric=self.distance_metric,
            index_type=self.index_type,
        )

        # Invalidate cache since we just modified the indexes
        self.invalidate_scan_cache()

        self.logger.info(f"Saved vector store to {self.persist_dir}")

    def load(self, name: str = "index") -> bool:
        """
        Load index and metadata from disk

        Args:
            name: Name of the saved files

        Returns:
            True if successful, False otherwise
        """
        if self.in_memory:
            self.logger.info("Skipping vector store load (in-memory mode enabled)")
            return False

        tenant_dir = self._tenant_dir()
        index_path = os.path.join(tenant_dir, f"{name}.faiss")
        jsonl_path = os.path.join(tenant_dir, f"{name}_metadata.jsonl")
        pkl_path = os.path.join(tenant_dir, f"{name}_metadata.pkl")

        if not os.path.exists(index_path):
            self.logger.warning(f"Index files not found in {tenant_dir}")
            return False
        if not os.path.exists(jsonl_path) and not os.path.exists(pkl_path):
            self.logger.warning(f"Metadata files not found in {tenant_dir}")
            return False

        try:
            # Load FAISS index
            self.index = faiss.read_index(index_path)

            # Load metadata — prefers JSONL, falls back to pickle with a
            # deprecation warning (see FINDING-EXT-C-004).
            data = load_metadata(pkl_path, logger=self.logger)
            self.metadata = data["metadata"]
            self.dimension = data["dimension"]
            self.distance_metric = data.get("distance_metric", "cosine")
            self.index_type = data.get("index_type", "HNSW")

            # Set search parameters for HNSW
            if self.index_type == "HNSW" and hasattr(self.index, "hnsw"):
                self.index.hnsw.efSearch = self.ef_search

            self.logger.info(
                f"Loaded vector store with {len(self.metadata)} vectors "
                f"from {self.persist_dir}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to load vector store: {e}")
            return False

    def clear(self):
        """Clear all vectors and metadata"""
        if self.dimension:
            self.initialize(self.dimension)
        else:
            self.index = None
            self.metadata = []
        self.logger.info("Cleared vector store")

    def merge_from_index(self, index_name: str) -> bool:
        """
        Merge vectors from another saved index into this store

        Args:
            index_name: Name of the index to merge from

        Returns:
            True if successful, False otherwise
        """
        if self.in_memory:
            self.logger.info("Skipping merge_from_index (in-memory mode enabled)")
            return False

        tenant_dir = self._tenant_dir()
        index_path = os.path.join(tenant_dir, f"{index_name}.faiss")
        jsonl_path = os.path.join(tenant_dir, f"{index_name}_metadata.jsonl")
        pkl_path = os.path.join(tenant_dir, f"{index_name}_metadata.pkl")

        if not os.path.exists(index_path):
            self.logger.warning(f"Index files not found for {index_name}")
            return False
        if not os.path.exists(jsonl_path) and not os.path.exists(pkl_path):
            self.logger.warning(f"Metadata files not found for {index_name}")
            return False

        try:
            # Load the other index
            other_index = faiss.read_index(index_path)

            # Load metadata (JSONL preferred, pickle fallback).
            data = load_metadata(pkl_path, logger=self.logger)
            other_metadata = data["metadata"]
            other_dimension = data["dimension"]

            # Verify dimensions match
            if self.dimension and self.dimension != other_dimension:
                self.logger.error(
                    f"Dimension mismatch: {self.dimension} vs {other_dimension}"
                )
                return False

            # Initialize if needed
            if self.index is None:
                self.initialize(other_dimension)

            # Reconstruct vectors from the FAISS index
            # For flat indices, we can access vectors directly
            # For HNSW, we need to reconstruct
            n_vectors = other_index.ntotal

            if n_vectors == 0:
                self.logger.warning(f"No vectors in {index_name}")
                return False

            # Try to reconstruct all vectors efficiently
            try:
                # Reconstruct vectors - do it in batches for better performance
                vectors = np.zeros((n_vectors, other_dimension), dtype=np.float32)

                # Reconstruct all vectors at once
                for i in range(n_vectors):
                    other_index.reconstruct(int(i), vectors[i])

                # Add to our index in one batch operation
                self.add_vectors(vectors, other_metadata)
                self.logger.info(f"Merged {n_vectors} vectors from {index_name}")
                return True

            except Exception as e:
                self.logger.error(
                    f"Failed to reconstruct vectors from {index_name}: {e}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Failed to merge from {index_name}: {e}")
            return False

    def delete_by_filter(self, filter_func) -> int:
        """
        Delete vectors matching a filter function.

        FAISS does not support in-place deletion of arbitrary rows for
        every index type; this implementation reconstructs the surviving
        embeddings and rebuilds a fresh index so that subsequent searches
        cannot return indices belonging to deleted rows.

        Fixes FINDING-EXT-C-003 (data loss + cross-tenant leakage).

        Args:
            filter_func: Function that takes metadata and returns True to
                delete. Only rows for which ``filter_func(meta)`` is
                truthy are removed.

        Returns:
            Number of vectors deleted.
        """
        if self.index is None or not self.metadata:
            return 0

        indices_to_keep: list[int] = []
        metadata_to_keep: list[dict[str, Any]] = []

        for i, meta in enumerate(self.metadata):
            if not filter_func(meta):
                indices_to_keep.append(i)
                metadata_to_keep.append(meta)

        num_deleted = len(self.metadata) - len(metadata_to_keep)
        if num_deleted == 0:
            return 0

        self.logger.info(
            f"Rebuilding index after deleting {num_deleted} vectors "
            f"(keeping {len(indices_to_keep)} of {len(self.metadata)})"
        )

        dimension = self.index.d

        # Reconstruct surviving vectors from the existing FAISS index. All
        # index types that FastCode instantiates (IndexFlatIP, IndexFlatL2,
        # IndexHNSWFlat) support reconstruct(); if a future backend adds a
        # non-reconstructable index this will raise and prevent silent
        # corruption (the old behaviour).
        surviving_vectors = np.zeros(
            (len(indices_to_keep), dimension), dtype=np.float32
        )
        for new_pos, old_idx in enumerate(indices_to_keep):
            self.index.reconstruct(int(old_idx), surviving_vectors[new_pos])

        # Build a fresh index matching the current configuration.
        if self.index_type == "HNSW":
            if self.distance_metric == "cosine":
                new_index = faiss.IndexHNSWFlat(
                    dimension, self.m, faiss.METRIC_INNER_PRODUCT
                )
            else:
                new_index = faiss.IndexHNSWFlat(dimension, self.m, faiss.METRIC_L2)
            new_index.hnsw.efConstruction = self.ef_construction
            new_index.hnsw.efSearch = self.ef_search
        else:
            if self.distance_metric == "cosine":
                new_index = faiss.IndexFlatIP(dimension)
            else:
                new_index = faiss.IndexFlatL2(dimension)

        if len(indices_to_keep) > 0:
            # Vectors were already normalized on add for cosine metric, so
            # they remain valid after reconstruction — no re-normalization
            # required here.
            new_index.add(surviving_vectors)

        # Swap in the rebuilt index + pruned metadata atomically from the
        # caller's perspective (no yield points in between).
        self.index = new_index
        self.metadata = metadata_to_keep

        return num_deleted

    def scan_available_indexes(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """
        Scan persist directory for available index files (with caching)

        Args:
            use_cache: Use cached results if available (default: True)

        Returns:
            List of dictionaries with repository information
        """
        import time

        available_repos = []

        if self.in_memory:
            self.logger.info("Skipping index scan (in-memory mode enabled)")
            return available_repos

        if not os.path.exists(self.persist_dir):
            return available_repos

        # Check cache
        if use_cache and self._index_scan_cache is not None:
            cache_time, cached_results = self._index_scan_cache
            if time.time() - cache_time < self._index_scan_cache_ttl:
                self.logger.debug("Using cached index scan results")
                return cached_results

        # Perform actual scan
        self.logger.info("Scanning available indexes...")

        tenant_dir = self._tenant_dir()
        if not os.path.isdir(tenant_dir):
            return []
        for file in os.listdir(tenant_dir):
            if file.endswith(".faiss"):
                repo_name = file.replace(".faiss", "")
                jsonl_file = os.path.join(
                    tenant_dir, f"{repo_name}_metadata.jsonl"
                )
                pkl_file = os.path.join(
                    tenant_dir, f"{repo_name}_metadata.pkl"
                )
                # Prefer JSONL when available; fall back to pickle for
                # legacy deployments.
                metadata_file = (
                    jsonl_file if os.path.exists(jsonl_file) else pkl_file
                )

                if os.path.exists(metadata_file):
                    try:
                        # Get file sizes (fast operation)
                        index_path = os.path.join(tenant_dir, file)
                        file_size = os.path.getsize(index_path)
                        metadata_size = os.path.getsize(metadata_file)
                        total_size_mb = (file_size + metadata_size) / (1024 * 1024)

                        # Optimized: Only read first chunk of metadata for basic info
                        # This avoids loading potentially huge metadata files
                        element_count = 0
                        file_count = 0
                        repo_url = "N/A"

                        try:
                            # Prefers JSONL, falls back to pickle with a
                            # deprecation warning + auto-migration.
                            data = load_metadata(pkl_file, logger=self.logger)
                            metadata_list = data.get("metadata", [])
                            element_count = len(metadata_list)

                            # Sample first few entries to get URL and estimate file count
                            # (much faster than iterating through all)
                            sample_size = min(
                                self._index_scan_sample_size, len(metadata_list)
                            )
                            seen_files = set()

                            for i in range(sample_size):
                                meta = metadata_list[i]
                                file_path = meta.get("file_path")
                                if file_path:
                                    seen_files.add(file_path)
                                if not repo_url or repo_url == "N/A":
                                    repo_url = meta.get("repo_url", "N/A")

                            # Estimate total file count based on sample
                            if sample_size > 0 and sample_size < len(metadata_list):
                                file_count = int(
                                    len(seen_files)
                                    * (len(metadata_list) / sample_size)
                                )
                            else:
                                file_count = len(seen_files)

                        except Exception as load_error:
                            self.logger.warning(
                                f"Failed to parse metadata for {repo_name}: {load_error}"
                            )

                        available_repos.append(
                            {
                                "name": repo_name,
                                "element_count": element_count,
                                "file_count": file_count,
                                "size_mb": round(total_size_mb, 2),
                                "url": repo_url,
                            }
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to read metadata for {repo_name}: {e}"
                        )
                        # Still add it with minimal info
                        available_repos.append(
                            {
                                "name": repo_name,
                                "element_count": 0,
                                "file_count": 0,
                                "size_mb": 0,
                                "url": "N/A",
                            }
                        )

        results = sorted(available_repos, key=lambda x: x["name"])

        # Update cache
        self._index_scan_cache = (time.time(), results)
        self.logger.info(f"Index scan complete: found {len(results)} repositories")

        return results

    def invalidate_scan_cache(self):
        """Invalidate the scan cache (call this when indexes change)"""
        self._index_scan_cache = None
        self.logger.debug("Invalidated index scan cache")
