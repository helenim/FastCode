"""Tests for Phase 10: Matryoshka dimensionality reduction."""

from unittest.mock import MagicMock, patch

import numpy as np


class TestMatryoshkaTruncation:
    """Test embedding truncation in CodeEmbedder."""

    def _make_embedder(self, matryoshka_dim=None, full_dim=384):
        """Create a CodeEmbedder with a mock provider."""
        config = {
            "embedding": {
                "provider": "local",
                "normalize_embeddings": True,
                "local": {"model": "test", "device": "cpu"},
            }
        }
        if matryoshka_dim is not None:
            config["embedding"]["matryoshka_dim"] = matryoshka_dim

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = full_dim
        mock_model.encode.return_value = np.random.randn(1, full_dim).astype(np.float32)

        with (
            patch("fastcode.embedding_providers.local_st.SentenceTransformer", return_value=mock_model),
            patch("fastcode.embedding_providers.local_st.torch") as mock_torch,
        ):
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            from fastcode.embedder import CodeEmbedder
            embedder = CodeEmbedder(config)

        # Override the provider's embed_batch to return controlled data
        def mock_embed(texts):
            n = len(texts)
            return np.random.randn(n, full_dim).astype(np.float32)

        embedder._provider.embed_batch = mock_embed
        return embedder

    def test_no_truncation_by_default(self):
        embedder = self._make_embedder(matryoshka_dim=None, full_dim=384)
        assert embedder.embedding_dim == 384

        result = embedder.embed_batch(["hello"])
        assert result.shape == (1, 384)

    def test_truncation_to_256(self):
        embedder = self._make_embedder(matryoshka_dim=256, full_dim=384)
        assert embedder.embedding_dim == 256

        result = embedder.embed_batch(["hello"])
        assert result.shape == (1, 256)

    def test_truncation_to_128(self):
        embedder = self._make_embedder(matryoshka_dim=128, full_dim=768)
        assert embedder.embedding_dim == 128

        result = embedder.embed_batch(["a", "b", "c"])
        assert result.shape == (3, 128)

    def test_truncated_embeddings_are_normalized(self):
        embedder = self._make_embedder(matryoshka_dim=64, full_dim=384)
        result = embedder.embed_batch(["hello"])

        norm = np.linalg.norm(result[0])
        np.testing.assert_allclose(norm, 1.0, atol=1e-5)

    def test_no_truncation_when_dim_equals_full(self):
        embedder = self._make_embedder(matryoshka_dim=384, full_dim=384)
        # matryoshka_dim == full_dim means no truncation
        assert embedder._matryoshka_dim is None
        assert embedder.embedding_dim == 384

    def test_no_truncation_when_dim_exceeds_full(self):
        embedder = self._make_embedder(matryoshka_dim=512, full_dim=384)
        # matryoshka_dim > full_dim means no truncation
        assert embedder._matryoshka_dim is None
        assert embedder.embedding_dim == 384

    def test_embed_text_uses_truncation(self):
        embedder = self._make_embedder(matryoshka_dim=64, full_dim=384)
        result = embedder.embed_text("hello")
        assert result.shape == (64,)

    def test_empty_batch(self):
        embedder = self._make_embedder(matryoshka_dim=64, full_dim=384)
        result = embedder.embed_batch([])
        assert len(result) == 0
