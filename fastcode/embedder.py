"""
Code Embedder - Generate embeddings for code snippets.

Delegates to pluggable embedding providers (local, ollama, api).
"""

import logging
from typing import Any

import numpy as np

from .embedding_providers import EmbeddingProvider, create_embedding_provider


class CodeEmbedder:
    """Generate embeddings for code using a pluggable embedding provider.

    The provider is selected via ``config["embedding"]["provider"]``:
      - ``"local"`` — SentenceTransformer on-device (default, backwards-compatible)
      - ``"ollama"`` — Ollama HTTP API
      - ``"api"`` — OpenAI-compatible REST API (voyage-code-3, etc.)
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)

        self._provider: EmbeddingProvider = create_embedding_provider(config)
        self.model_name: str = self._provider.model_name

        # Matryoshka dimensionality reduction
        emb_cfg = config.get("embedding", {})
        self._matryoshka_dim: int | None = emb_cfg.get("matryoshka_dim")
        self._full_dim: int = self._provider.embedding_dim

        if self._matryoshka_dim and self._matryoshka_dim < self._full_dim:
            self.embedding_dim = self._matryoshka_dim
            self.logger.info(
                "Matryoshka truncation enabled: %d → %d dimensions",
                self._full_dim,
                self._matryoshka_dim,
            )
        else:
            self.embedding_dim = self._full_dim
            self._matryoshka_dim = None

        self.logger.info(
            "CodeEmbedder ready: provider=%s model=%s dim=%d%s",
            emb_cfg.get("provider", "local"),
            self.model_name,
            self.embedding_dim,
            f" (truncated from {self._full_dim})" if self._matryoshka_dim else "",
        )

    @property
    def normalize(self) -> bool:
        return self.config.get("embedding", {}).get("normalize_embeddings", True)

    def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return np.array([], dtype=np.float32)
        embeddings = self._provider.embed_batch(texts)
        return self._maybe_truncate(embeddings)

    def _maybe_truncate(self, embeddings: np.ndarray) -> np.ndarray:
        """Apply Matryoshka dimensionality reduction if configured.

        Truncates embeddings to the first N dimensions and re-normalizes.
        Matryoshka-trained models (nomic-embed-code, voyage-code-3, Qwen3-Embedding)
        produce embeddings where leading dimensions carry the most information.
        """
        if self._matryoshka_dim is None or embeddings.ndim < 2:
            return embeddings

        truncated = embeddings[:, : self._matryoshka_dim].copy()

        # Re-normalize after truncation
        if self.normalize:
            norms = np.linalg.norm(truncated, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            truncated = truncated / norms

        return truncated

    def embed_code_elements(
        self, elements: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Generate embeddings for code elements (functions, classes, etc.)."""
        if not elements:
            return []

        texts = [self._prepare_code_text(elem) for elem in elements]

        self.logger.info("Generating embeddings for %d code elements", len(texts))
        embeddings = self._provider.embed_batch(texts)
        self.logger.info(
            "Successfully generated embeddings for %d code elements", len(embeddings)
        )

        for elem, embedding in zip(elements, embeddings, strict=False):
            elem["embedding"] = embedding
            elem["embedding_text"] = texts[elements.index(elem)]

        return elements

    def _prepare_code_text(self, element: dict[str, Any]) -> str:
        """Prepare code element for embedding.

        Combines various parts of the code element into a single text
        suitable for embedding.
        """
        parts = []

        if "type" in element:
            parts.append(f"Type: {element['type']}")

        if "name" in element:
            parts.append(f"Name: {element['name']}")

        if "signature" in element:
            parts.append(f"Signature: {element['signature']}")

        if element.get("docstring"):
            parts.append(f"Documentation: {element['docstring']}")

        if element.get("summary"):
            parts.append(element["summary"])

        if "code" in element:
            code = element["code"]
            if len(code) > 10000:
                code = code[:10000] + "..."
            parts.append(f"Code:\n{code}")

        return "\n".join(parts)

    def compute_similarity(
        self, embedding1: np.ndarray, embedding2: np.ndarray
    ) -> float:
        """Compute cosine similarity between two embeddings."""
        if self.normalize:
            return float(np.dot(embedding1, embedding2))
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(embedding1, embedding2) / (norm1 * norm2))

    def compute_similarities(
        self, query_embedding: np.ndarray, embeddings: np.ndarray
    ) -> np.ndarray:
        """Compute similarities between query and multiple embeddings."""
        if self.normalize:
            return np.dot(embeddings, query_embedding)
        norms = np.linalg.norm(embeddings, axis=1)
        query_norm = np.linalg.norm(query_embedding)
        if query_norm == 0:
            return np.zeros(len(embeddings))
        return np.dot(embeddings, query_embedding) / (norms * query_norm)
