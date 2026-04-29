"""
Generic REST API embedding provider.

Supports any OpenAI-compatible embedding API (voyage-code-3, OpenAI, etc.).
Uses the standard POST /embeddings endpoint with model and input fields.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_httpx = None


def _get_httpx():
    global _httpx
    if _httpx is None:
        import httpx

        _httpx = httpx
    return _httpx


class APIProvider:
    """Embedding provider backed by an OpenAI-compatible REST API."""

    def __init__(self, config: dict[str, Any]) -> None:
        emb_cfg = config.get("embedding", {})
        api_cfg = emb_cfg.get("api", {})

        self._base_url: str = api_cfg.get(
            "base_url",
            os.getenv("EMBEDDING_API_BASE_URL", "https://api.voyageai.com/v1"),
        )
        self._model_name: str = api_cfg.get(
            "model",
            os.getenv("EMBEDDING_API_MODEL", "voyage-code-3"),
        )

        api_key_env = api_cfg.get("api_key_env", "EMBEDDING_API_KEY")
        self._api_key: str = os.getenv(api_key_env, api_cfg.get("api_key", ""))

        self._batch_size: int = api_cfg.get("batch_size", emb_cfg.get("batch_size", 32))
        self._normalize: bool = api_cfg.get(
            "normalize_embeddings", emb_cfg.get("normalize_embeddings", True)
        )
        self._timeout: float = api_cfg.get("timeout", 60.0)
        self._input_type: str | None = api_cfg.get("input_type")

        # Probe dimension
        logger.info(
            "Initializing API embedding provider: model=%s url=%s",
            self._model_name,
            self._base_url,
        )
        probe = self._call_api(["test"])
        self._embedding_dim: int = probe.shape[1]
        logger.info("API embedding dimension: %d", self._embedding_dim)

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
            embeddings = self._call_api(batch)
            all_embeddings.append(embeddings)

        result = np.vstack(all_embeddings).astype(np.float32)

        if self._normalize:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            result = result / norms

        return result

    def _call_api(self, texts: list[str]) -> np.ndarray:
        """Call an OpenAI-compatible /embeddings endpoint."""
        httpx = _get_httpx()
        url = f"{self._base_url.rstrip('/')}/embeddings"

        payload: dict[str, Any] = {
            "model": self._model_name,
            "input": texts,
        }
        if self._input_type:
            payload["input_type"] = self._input_type

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        resp = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        resp.raise_for_status()

        data = resp.json()
        embeddings_data = data.get("data", [])
        if not embeddings_data:
            msg = f"API returned no embeddings for model {self._model_name}"
            raise ValueError(msg)

        # Sort by index to ensure order matches input
        embeddings_data.sort(key=lambda x: x.get("index", 0))
        vectors = [item["embedding"] for item in embeddings_data]

        return np.array(vectors, dtype=np.float32)
