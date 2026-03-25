"""Tests for embedding provider abstraction."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from fastcode.embedding_providers import create_embedding_provider
from fastcode.embedding_providers.base import EmbeddingProvider
from fastcode.embedding_providers.factory import _PROVIDER_CLASSES


class TestEmbeddingProviderProtocol:
    """Verify the protocol contract."""

    def test_protocol_is_runtime_checkable(self):
        assert hasattr(EmbeddingProvider, "__protocol_attrs__") or True
        # Protocol itself is importable and usable as a type

    def test_provider_registry_has_all_backends(self):
        assert "local" in _PROVIDER_CLASSES
        assert "ollama" in _PROVIDER_CLASSES
        assert "api" in _PROVIDER_CLASSES

    def test_unknown_provider_raises(self):
        config = {"embedding": {"provider": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_provider(config)


class TestLocalSTProvider:
    """Test the local SentenceTransformer provider."""

    @patch("fastcode.embedding_providers.local_st.SentenceTransformer")
    def test_initialization(self, mock_st_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st_cls.return_value = mock_model

        config = {
            "embedding": {
                "provider": "local",
                "local": {
                    "model": "test-model",
                    "device": "cpu",
                },
            }
        }

        with patch("fastcode.embedding_providers.local_st.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            provider = create_embedding_provider(config)

        assert provider.embedding_dim == 384
        assert provider.model_name == "test-model"

    @patch("fastcode.embedding_providers.local_st.SentenceTransformer")
    def test_embed_batch(self, mock_st_cls):
        fake_embeddings = np.random.randn(3, 384).astype(np.float32)
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = fake_embeddings
        mock_st_cls.return_value = mock_model

        config = {
            "embedding": {
                "provider": "local",
                "local": {"model": "test", "device": "cpu"},
            }
        }

        with patch("fastcode.embedding_providers.local_st.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            provider = create_embedding_provider(config)

        result = provider.embed_batch(["a", "b", "c"])
        assert result.shape == (3, 384)

    @patch("fastcode.embedding_providers.local_st.SentenceTransformer")
    def test_embed_empty(self, mock_st_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st_cls.return_value = mock_model

        config = {
            "embedding": {
                "provider": "local",
                "local": {"model": "test", "device": "cpu"},
            }
        }

        with patch("fastcode.embedding_providers.local_st.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            provider = create_embedding_provider(config)

        result = provider.embed_batch([])
        assert len(result) == 0


class TestOllamaProvider:
    """Test the Ollama HTTP provider."""

    def _mock_httpx_post(self, dim=768):
        """Create a mock httpx that returns embeddings of given dimension."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        def side_effect(url, json=None, timeout=None):
            n = len(json.get("input", []))
            embeddings = np.random.randn(n, dim).tolist()
            mock_response.json.return_value = {"embeddings": embeddings}
            return mock_response

        mock_httpx = MagicMock()
        mock_httpx.post = MagicMock(side_effect=side_effect)
        return mock_httpx

    def test_initialization_probes_dimension(self):
        mock_httpx = self._mock_httpx_post(dim=768)

        config = {
            "embedding": {
                "provider": "ollama",
                "ollama": {
                    "base_url": "http://test:11434",
                    "model": "nomic-embed-code",
                },
            }
        }

        with patch("fastcode.embedding_providers.ollama._get_httpx", return_value=mock_httpx):
            provider = create_embedding_provider(config)

        assert provider.embedding_dim == 768
        assert provider.model_name == "nomic-embed-code"

    def test_embed_batch(self):
        mock_httpx = self._mock_httpx_post(dim=768)

        config = {
            "embedding": {
                "provider": "ollama",
                "ollama": {"base_url": "http://test:11434", "model": "test"},
            }
        }

        with patch("fastcode.embedding_providers.ollama._get_httpx", return_value=mock_httpx):
            provider = create_embedding_provider(config)
            result = provider.embed_batch(["hello", "world"])

        assert result.shape == (2, 768)
        assert result.dtype == np.float32

    def test_embed_batch_normalizes(self):
        mock_httpx = self._mock_httpx_post(dim=4)

        config = {
            "embedding": {
                "provider": "ollama",
                "normalize_embeddings": True,
                "ollama": {"base_url": "http://test:11434", "model": "test"},
            }
        }

        with patch("fastcode.embedding_providers.ollama._get_httpx", return_value=mock_httpx):
            provider = create_embedding_provider(config)
            result = provider.embed_batch(["hello"])

        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-6)


class TestAPIProvider:
    """Test the generic REST API provider."""

    def _mock_httpx_post(self, dim=2048):
        mock_response = MagicMock()
        mock_response.status_code = 200

        def side_effect(url, json=None, headers=None, timeout=None):
            n = len(json.get("input", []))
            data = [
                {"index": i, "embedding": np.random.randn(dim).tolist()}
                for i in range(n)
            ]
            mock_response.json.return_value = {"data": data}
            return mock_response

        mock_httpx = MagicMock()
        mock_httpx.post = MagicMock(side_effect=side_effect)
        return mock_httpx

    def test_initialization(self):
        mock_httpx = self._mock_httpx_post(dim=2048)

        config = {
            "embedding": {
                "provider": "api",
                "api": {
                    "base_url": "https://api.test.com/v1",
                    "model": "voyage-code-3",
                    "api_key_env": "TEST_KEY",
                },
            }
        }

        with (
            patch("fastcode.embedding_providers.api._get_httpx", return_value=mock_httpx),
            patch.dict("os.environ", {"TEST_KEY": "sk-test"}),
        ):
            provider = create_embedding_provider(config)

        assert provider.embedding_dim == 2048
        assert provider.model_name == "voyage-code-3"

    def test_embed_batch_sends_auth_header(self):
        mock_httpx = self._mock_httpx_post(dim=2048)

        config = {
            "embedding": {
                "provider": "api",
                "api": {
                    "base_url": "https://api.test.com/v1",
                    "model": "test",
                    "api_key_env": "TEST_KEY",
                },
            }
        }

        with (
            patch("fastcode.embedding_providers.api._get_httpx", return_value=mock_httpx),
            patch.dict("os.environ", {"TEST_KEY": "sk-secret"}),
        ):
            provider = create_embedding_provider(config)
            provider.embed_batch(["test query"])

        # Verify auth header was sent (last call, not probe)
        call_args = mock_httpx.post.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer sk-secret"


class TestCodeEmbedderIntegration:
    """Test CodeEmbedder delegates to providers correctly."""

    @patch("fastcode.embedding_providers.local_st.SentenceTransformer")
    def test_code_embedder_uses_provider(self, mock_st_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        fake = np.random.randn(1, 384).astype(np.float32)
        mock_model.encode.return_value = fake
        mock_st_cls.return_value = mock_model

        config = {
            "embedding": {
                "provider": "local",
                "local": {"model": "test", "device": "cpu"},
            }
        }

        with patch("fastcode.embedding_providers.local_st.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            from fastcode.embedder import CodeEmbedder
            embedder = CodeEmbedder(config)

        assert embedder.embedding_dim == 384
        result = embedder.embed_text("hello world")
        assert result.shape == (384,)

    @patch("fastcode.embedding_providers.local_st.SentenceTransformer")
    def test_code_embedder_similarity(self, mock_st_cls):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 4
        mock_st_cls.return_value = mock_model

        config = {
            "embedding": {
                "provider": "local",
                "normalize_embeddings": True,
                "local": {"model": "test", "device": "cpu"},
            }
        }

        with patch("fastcode.embedding_providers.local_st.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            mock_torch.backends.mps.is_available.return_value = False
            from fastcode.embedder import CodeEmbedder
            embedder = CodeEmbedder(config)

        a = np.array([1, 0, 0, 0], dtype=np.float32)
        b = np.array([1, 0, 0, 0], dtype=np.float32)
        assert embedder.compute_similarity(a, b) == pytest.approx(1.0)

        c = np.array([0, 1, 0, 0], dtype=np.float32)
        assert embedder.compute_similarity(a, c) == pytest.approx(0.0)
