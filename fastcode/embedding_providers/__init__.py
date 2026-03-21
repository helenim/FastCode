"""
Embedding Providers — pluggable backends for code embedding generation.

Supported providers:
- local: SentenceTransformer models (default, runs on-device)
- ollama: Ollama embedding API (HTTP, for nomic-embed-code / Qwen3-Embedding)
- api: Generic REST embedding API (voyage-code-3, OpenAI, etc.)
"""

from .base import EmbeddingProvider
from .factory import create_embedding_provider

__all__ = ["EmbeddingProvider", "create_embedding_provider"]
