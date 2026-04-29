"""
Base protocol for vector store backends.

All backends must implement the core operations: initialize, add, search,
save, load, delete, and repo overview management.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VectorStoreBackend(Protocol):
    """Protocol that all vector store backends must satisfy."""

    dimension: int | None
    metadata: list[dict[str, Any]]

    def initialize(self, dimension: int) -> None:
        """Initialize the store with a given embedding dimension."""
        ...

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict[str, Any]]) -> None:
        """Add vectors with metadata to the store."""
        ...

    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        min_score: float | None = None,
        repo_filter: list[str] | None = None,
        element_type_filter: str | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Search for similar vectors. Returns (metadata, score) tuples."""
        ...

    def search_batch(
        self,
        query_vectors: np.ndarray,
        k: int = 10,
        min_score: float | None = None,
    ) -> list[list[tuple[dict[str, Any], float]]]:
        """Search for multiple queries at once."""
        ...

    def save(self, name: str = "index") -> None:
        """Persist the index and metadata to storage."""
        ...

    def load(self, name: str = "index") -> bool:
        """Load index and metadata from storage. Returns True if successful."""
        ...

    def clear(self) -> None:
        """Clear all vectors and metadata."""
        ...

    def get_count(self) -> int:
        """Get total number of vectors."""
        ...

    def get_repository_names(self) -> list[str]:
        """Get list of unique repository names."""
        ...

    def get_count_by_repository(self) -> dict[str, int]:
        """Get count of vectors per repository."""
        ...

    def filter_by_repositories(self, repo_names: list[str]) -> list[int]:
        """Get indices of vectors belonging to specific repositories."""
        ...

    def delete_by_filter(self, filter_func: Any) -> int:
        """Delete vectors matching a filter function. Returns count deleted."""
        ...

    def delete_by_repo(self, repo_name: str) -> int:
        """Delete all vectors for a specific repository. Returns count deleted."""
        ...

    def merge_from_index(self, index_name: str) -> bool:
        """Merge vectors from another saved index into this store."""
        ...

    def scan_available_indexes(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """Scan for available index files."""
        ...

    def invalidate_scan_cache(self) -> None:
        """Invalidate any cached scan results."""
        ...

    # Repo overview management
    def save_repo_overview(
        self,
        repo_name: str,
        overview_content: str,
        embedding: np.ndarray,
        metadata: dict[str, Any],
    ) -> None:
        """Save a repository overview."""
        ...

    def delete_repo_overview(self, repo_name: str) -> bool:
        """Delete a repository overview."""
        ...

    def load_repo_overviews(self) -> dict[str, dict[str, Any]]:
        """Load all repository overviews."""
        ...

    def search_repository_overviews(
        self,
        query_vector: np.ndarray,
        k: int = 5,
        min_score: float | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Search repository overviews."""
        ...
