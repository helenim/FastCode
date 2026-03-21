"""
Qdrant vector store backend.

Provides production-grade CRUD, native metadata filtering, persistence,
snapshots, and replication via the Qdrant vector database.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import — only needed when this backend is actually selected
_qdrant_models = None
_QdrantClient = None


def _import_qdrant():
    global _qdrant_models, _QdrantClient
    if _QdrantClient is None:
        from qdrant_client import QdrantClient
        from qdrant_client import models

        _QdrantClient = QdrantClient
        _qdrant_models = models
    return _QdrantClient, _qdrant_models


class QdrantVectorStore:
    """Vector store backed by Qdrant."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.vector_config = config.get("vector_store", {})
        qdrant_cfg = self.vector_config.get("qdrant", {})

        self.dimension: int | None = None
        self.metadata: list[dict[str, Any]] = []  # Compatibility — may be empty for Qdrant

        self._url: str = qdrant_cfg.get(
            "url", os.getenv("QDRANT_URL", "http://localhost:6333")
        )
        self._collection_name: str = qdrant_cfg.get("collection_name", "fastcode")
        self._overview_collection: str = qdrant_cfg.get(
            "overview_collection", "fastcode_overviews"
        )
        self._on_disk: bool = qdrant_cfg.get("on_disk", True)
        self._hnsw_m: int = qdrant_cfg.get("hnsw_config", {}).get(
            "m", self.vector_config.get("m", 16)
        )
        self._hnsw_ef: int = qdrant_cfg.get("hnsw_config", {}).get(
            "ef_construct", self.vector_config.get("ef_construction", 200)
        )
        self._distance = self.vector_config.get("distance_metric", "cosine")

        self._client = None
        self._index_scan_cache: tuple[float, list[dict[str, Any]]] | None = None
        self._index_scan_cache_ttl = self.vector_config.get("index_scan_cache_ttl", 30.0)

    def _get_client(self):
        if self._client is None:
            QdrantClient, _ = _import_qdrant()
            self._client = QdrantClient(url=self._url)
            logger.info("Connected to Qdrant at %s", self._url)
        return self._client

    def _distance_type(self):
        _, models = _import_qdrant()
        if self._distance == "cosine":
            return models.Distance.COSINE
        return models.Distance.EUCLID

    def initialize(self, dimension: int) -> None:
        self.dimension = dimension
        client = self._get_client()
        _, models = _import_qdrant()

        # Create collection if it doesn't exist
        collections = [c.name for c in client.get_collections().collections]
        if self._collection_name not in collections:
            client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=self._distance_type(),
                    on_disk=self._on_disk,
                    hnsw_config=models.HnswConfigDiff(
                        m=self._hnsw_m,
                        ef_construct=self._hnsw_ef,
                    ),
                ),
            )
            # Create payload indexes for common filter fields
            for field in ("repo_name", "type", "file_path"):
                client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d)", self._collection_name, dimension
            )
        else:
            logger.info("Qdrant collection '%s' already exists", self._collection_name)

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        if self.dimension is None:
            raise RuntimeError("Vector store not initialized")

        client = self._get_client()
        _, models = _import_qdrant()

        vectors = vectors.astype(np.float32)

        # Build points with UUIDs
        points = []
        for vec, meta in zip(vectors, metadata):
            point_id = meta.get("id") or str(uuid.uuid4())
            points.append(
                models.PointStruct(
                    id=point_id if isinstance(point_id, str) and len(point_id) <= 36 else str(uuid.uuid4()),
                    vector=vec.tolist(),
                    payload=meta,
                )
            )

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(
                collection_name=self._collection_name,
                points=batch,
            )

        logger.info("Added %d vectors to Qdrant collection '%s'", len(vectors), self._collection_name)

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        min_score: float | None = None,
        repo_filter: list[str] | None = None,
        element_type_filter: str | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        client = self._get_client()
        _, models = _import_qdrant()

        query_vector = query_vector.astype(np.float32).flatten()

        # Build filter conditions
        conditions = []
        if repo_filter:
            conditions.append(
                models.FieldCondition(
                    key="repo_name",
                    match=models.MatchAny(any=repo_filter),
                )
            )
        if element_type_filter:
            conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=element_type_filter),
                )
            )

        query_filter = models.Filter(must=conditions) if conditions else None

        results = client.search(
            collection_name=self._collection_name,
            query_vector=query_vector.tolist(),
            limit=k,
            query_filter=query_filter,
            score_threshold=min_score,
        )

        return [(hit.payload, hit.score) for hit in results]

    def search_batch(
        self,
        query_vectors: np.ndarray,
        k: int = 10,
        min_score: float | None = None,
    ) -> list[list[tuple[dict[str, Any], float]]]:
        # Simple implementation: iterate over queries
        all_results = []
        for qv in query_vectors:
            all_results.append(self.search(qv, k=k, min_score=min_score))
        return all_results

    def save(self, name: str = "index") -> None:
        # Qdrant persists automatically — no-op
        self.invalidate_scan_cache()
        logger.info("Qdrant auto-persists; save() is a no-op")

    def load(self, name: str = "index") -> bool:
        # Check if collection exists and has data
        try:
            client = self._get_client()
            info = client.get_collection(self._collection_name)
            count = info.points_count or 0
            self.dimension = (
                info.config.params.vectors.size
                if hasattr(info.config.params.vectors, "size")
                else None
            )
            logger.info(
                "Loaded Qdrant collection '%s' with %d points",
                self._collection_name, count,
            )
            return count > 0
        except Exception as e:
            logger.warning("Failed to load Qdrant collection: %s", e)
            return False

    def clear(self) -> None:
        try:
            client = self._get_client()
            client.delete_collection(self._collection_name)
            if self.dimension:
                self.initialize(self.dimension)
            logger.info("Cleared Qdrant collection '%s'", self._collection_name)
        except Exception as e:
            logger.warning("Failed to clear Qdrant collection: %s", e)

    def get_count(self) -> int:
        try:
            client = self._get_client()
            info = client.get_collection(self._collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    def get_repository_names(self) -> list[str]:
        # Scroll through unique repo_name values
        try:
            client = self._get_client()
            _, models = _import_qdrant()

            # Use scroll with a group-by-like approach: get a sample and extract unique names
            results, _ = client.scroll(
                collection_name=self._collection_name,
                limit=10000,
                with_payload=["repo_name"],
                with_vectors=False,
            )
            names = {r.payload.get("repo_name") for r in results if r.payload.get("repo_name")}
            return sorted(names)
        except Exception:
            return []

    def get_count_by_repository(self) -> dict[str, int]:
        try:
            client = self._get_client()
            _, models = _import_qdrant()

            repo_counts: dict[str, int] = {}
            for name in self.get_repository_names():
                count = client.count(
                    collection_name=self._collection_name,
                    count_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="repo_name",
                                match=models.MatchValue(value=name),
                            )
                        ]
                    ),
                )
                repo_counts[name] = count.count
            return repo_counts
        except Exception:
            return {}

    def filter_by_repositories(self, repo_names: list[str]) -> list[int]:
        # Not meaningful for Qdrant (uses native filtering) — return empty
        return []

    def delete_by_filter(self, filter_func: Any) -> int:
        # For Qdrant, prefer delete_by_repo or native filter-based deletion
        logger.warning("delete_by_filter with callable not supported for Qdrant; use delete_by_repo")
        return 0

    def delete_by_repo(self, repo_name: str) -> int:
        """Delete all vectors for a specific repository — native Qdrant operation."""
        try:
            client = self._get_client()
            _, models = _import_qdrant()

            # Count before deletion
            count_before = client.count(
                collection_name=self._collection_name,
                count_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repo_name",
                            match=models.MatchValue(value=repo_name),
                        )
                    ]
                ),
            ).count

            # Delete by filter
            client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="repo_name",
                                match=models.MatchValue(value=repo_name),
                            )
                        ]
                    )
                ),
            )

            self.invalidate_scan_cache()
            logger.info("Deleted %d vectors for repo '%s'", count_before, repo_name)
            return count_before
        except Exception as e:
            logger.error("Failed to delete vectors for repo '%s': %s", repo_name, e)
            return 0

    def delete_by_files(self, repo_name: str, file_paths: list[str]) -> int:
        """Delete vectors for specific files within a repo — enables incremental indexing."""
        try:
            client = self._get_client()
            _, models = _import_qdrant()

            client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="repo_name",
                                match=models.MatchValue(value=repo_name),
                            ),
                            models.FieldCondition(
                                key="file_path",
                                match=models.MatchAny(any=file_paths),
                            ),
                        ]
                    )
                ),
            )
            logger.info("Deleted vectors for %d files in repo '%s'", len(file_paths), repo_name)
            return len(file_paths)  # Approximate
        except Exception as e:
            logger.error("Failed to delete file vectors: %s", e)
            return 0

    def merge_from_index(self, index_name: str) -> bool:
        # Not applicable for Qdrant — all repos share a single collection
        logger.info("merge_from_index not needed for Qdrant (shared collection)")
        return True

    def scan_available_indexes(self, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache and self._index_scan_cache is not None:
            cache_time, cached = self._index_scan_cache
            if time.time() - cache_time < self._index_scan_cache_ttl:
                return cached

        try:
            repos = self.get_count_by_repository()
            results = [
                {
                    "name": name,
                    "element_count": count,
                    "file_count": 0,
                    "size_mb": 0,
                    "url": "N/A",
                }
                for name, count in sorted(repos.items())
            ]
            self._index_scan_cache = (time.time(), results)
            return results
        except Exception:
            return []

    def invalidate_scan_cache(self) -> None:
        self._index_scan_cache = None

    # -- Repo overview management --

    def save_repo_overview(
        self, repo_name: str, overview_content: str,
        embedding: np.ndarray, metadata: dict[str, Any],
    ) -> None:
        client = self._get_client()
        _, models = _import_qdrant()

        embedding = embedding.astype(np.float32).flatten()

        # Ensure overview collection exists
        collections = [c.name for c in client.get_collections().collections]
        if self._overview_collection not in collections:
            client.create_collection(
                collection_name=self._overview_collection,
                vectors_config=models.VectorParams(
                    size=len(embedding),
                    distance=self._distance_type(),
                ),
            )

        payload = {
            "repo_name": repo_name,
            "content": overview_content,
            **metadata,
        }

        # Use repo_name as point ID (deterministic)
        client.upsert(
            collection_name=self._overview_collection,
            points=[
                models.PointStruct(
                    id=repo_name,
                    vector=embedding.tolist(),
                    payload=payload,
                )
            ],
        )
        logger.info("Saved repo overview for '%s' to Qdrant", repo_name)

    def delete_repo_overview(self, repo_name: str) -> bool:
        try:
            client = self._get_client()
            client.delete(
                collection_name=self._overview_collection,
                points_selector=[repo_name],
            )
            return True
        except Exception:
            return False

    def load_repo_overviews(self) -> dict[str, dict[str, Any]]:
        try:
            client = self._get_client()
            results, _ = client.scroll(
                collection_name=self._overview_collection,
                limit=1000,
                with_payload=True,
                with_vectors=True,
            )
            overviews = {}
            for point in results:
                name = point.payload.get("repo_name", str(point.id))
                overviews[name] = {
                    "repo_name": name,
                    "content": point.payload.get("content", ""),
                    "embedding": np.array(point.vector, dtype=np.float32),
                    "metadata": {
                        k: v for k, v in point.payload.items()
                        if k not in ("repo_name", "content")
                    },
                }
            return overviews
        except Exception:
            return {}

    def search_repository_overviews(
        self, query_vector: np.ndarray, k: int = 5,
        min_score: float | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        try:
            client = self._get_client()
            query_vector = query_vector.astype(np.float32).flatten()

            results = client.search(
                collection_name=self._overview_collection,
                query_vector=query_vector.tolist(),
                limit=k,
                score_threshold=min_score,
            )

            return [
                (
                    {"repo_name": hit.payload.get("repo_name"), "type": "repository_overview", **hit.payload},
                    hit.score,
                )
                for hit in results
            ]
        except Exception:
            return []
