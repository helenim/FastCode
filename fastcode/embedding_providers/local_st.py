"""
Local SentenceTransformer embedding provider.

Runs models on-device (CUDA > MPS > CPU auto-detection).
"""

from __future__ import annotations

import logging
import platform
from typing import Any

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class LocalSTProvider:
    """Embedding provider backed by sentence-transformers."""

    def __init__(self, config: dict[str, Any]) -> None:
        emb_cfg = config.get("embedding", {})
        local_cfg = emb_cfg.get("local", {})

        self._model_name: str = local_cfg.get(
            "model",
            emb_cfg.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
        )
        self._batch_size: int = local_cfg.get(
            "batch_size", emb_cfg.get("batch_size", 32)
        )
        self._max_seq_length: int = local_cfg.get(
            "max_seq_length", emb_cfg.get("max_seq_length", 512)
        )
        self._normalize: bool = local_cfg.get(
            "normalize_embeddings", emb_cfg.get("normalize_embeddings", True)
        )

        device = local_cfg.get("device", emb_cfg.get("device", "auto"))
        if device == "auto" or device != "cpu":
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "mps"
                if torch.backends.mps.is_available()
                else "cpu"
            )
        self._device = device

        logger.info("Loading local embedding model: %s (device=%s)", self._model_name, self._device)
        self._model = SentenceTransformer(self._model_name, device=self._device)
        self._model.max_seq_length = self._max_seq_length
        self._embedding_dim: int = self._model.get_sentence_embedding_dimension()
        logger.info("Local embedding dimension: %d", self._embedding_dim)

    @property
    def embedding_dim(self) -> int:
        return self._embedding_dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([], dtype=np.float32)

        encode_kwargs: dict[str, Any] = {
            "batch_size": self._batch_size,
            "show_progress_bar": len(texts) > 100,
            "normalize_embeddings": self._normalize,
            "convert_to_numpy": True,
            "device": self._device,
            "convert_to_tensor": False,
        }

        if platform.system() == "Darwin":
            encode_kwargs["pool"] = None

        return self._model.encode(texts, **encode_kwargs)
