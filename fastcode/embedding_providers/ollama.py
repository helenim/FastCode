"""
Ollama embedding provider.

Calls the Ollama /api/embed endpoint over HTTP.
Supports nomic-embed-text, nomic-embed-code, Qwen3-Embedding, etc.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import — httpx is only needed if this provider is actually used
_httpx = None


def _get_httpx():
    global _httpx
    if _httpx is None:
        import httpx
        _httpx = httpx
    return _httpx


class OllamaProvider:
    """Embedding provider backed by an Ollama instance."""

    def __init__(self, config: dict[str, Any]) -> None:
        emb_cfg = config.get("embedding", {})
        ollama_cfg = emb_cfg.get("ollama", {})

        self._base_url: str = ollama_cfg.get(
            "base_url",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        self._model_name: str = ollama_cfg.get(
            "model",
            os.getenv("FASTCODE_EMBEDDING_MODEL", "nomic-embed-text"),
        )
        self._batch_size: int = ollama_cfg.get(
            "batch_size", emb_cfg.get("batch_size", 32)
        )
        self._normalize: bool = ollama_cfg.get(
            "normalize_embeddings", emb_cfg.get("normalize_embeddings", True)
        )
        self._truncate: bool = ollama_cfg.get("truncate", True)
        self._timeout: float = ollama_cfg.get("timeout", 120.0)

        # Probe dimension by embedding a short test string
        logger.info(
            "Initializing Ollama embedding provider: model=%s url=%s",
            self._model_name, self._base_url,
        )
        probe = self._call_embed(["test"])
        self._embedding_dim: int = probe.shape[1]
        logger.info("Ollama embedding dimension: %d", self._embedding_dim)

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)

        all_embeddings: list[np.ndarray] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            embeddings = self._call_embed(batch)
            all_embeddings.append(embeddings)

        result = np.vstack(all_embeddings).astype(np.float32)

        if self._normalize:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            result = result / norms

        return result

    def _call_embed(self, texts: list[str]) -> np.ndarray:
        """Call the Ollama /api/embed endpoint."""
        httpx = _get_httpx()
        url = f"{self._base_url.rstrip('/')}/api/embed"
        payload = {
            "model": self._model_name,
            "input": texts,
            "truncate": self._truncate,
        }

        resp = httpx.post(url, json=payload, timeout=self._timeout)
        resp.raise_for_status()

        data = resp.json()
        embeddings = data.get("embeddings", [])
        if not embeddings:
            msg = f"Ollama returned no embeddings for model {self._model_name}"
            raise ValueError(msg)

        return np.array(embeddings, dtype=np.float32)
