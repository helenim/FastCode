"""
Base protocol for embedding providers.

All providers must implement embed_batch() and expose embedding_dim.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol that all embedding providers must satisfy."""

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of the embedding vectors produced by this provider."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model identifier (for logging and index metadata)."""
        ...

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts.

        Args:
            texts: Non-empty list of strings.

        Returns:
            np.ndarray of shape (len(texts), embedding_dim), dtype float32,
            L2-normalized if the provider supports it.
        """
        ...
