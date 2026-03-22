"""
FAISS vector store backend — thin wrapper around the original VectorStore.

Adds the delete_by_repo and delete_by_files methods for interface compatibility.
"""

from __future__ import annotations

import logging

from ..vector_store import VectorStore

logger = logging.getLogger(__name__)


class FaissVectorStore(VectorStore):
    """FAISS backend with additional methods for protocol compatibility."""

    def delete_by_repo(self, repo_name: str) -> int:
        """Delete all vectors for a specific repo (requires index rebuild)."""
        return self.delete_by_filter(lambda meta: meta.get("repo_name") == repo_name)

    def delete_by_files(self, repo_name: str, file_paths: list[str]) -> int:
        """Delete vectors for specific files (requires index rebuild)."""
        file_set = set(file_paths)
        return self.delete_by_filter(
            lambda meta: (
                meta.get("repo_name") == repo_name
                and meta.get("file_path") in file_set
            )
        )
