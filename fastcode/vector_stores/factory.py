"""
Factory for creating vector store backends from configuration.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_vector_store(config: dict[str, Any]):
    """Create a vector store backend based on configuration.

    Reads ``config["vector_store"]["type"]`` to determine which backend to use.
    Defaults to ``"faiss"`` for backwards compatibility.

    Args:
        config: Full FastCode configuration dict.

    Returns:
        A vector store instance (FaissVectorStore or QdrantVectorStore).
    """
    vs_config = config.get("vector_store", {})
    backend_type = vs_config.get("type", "faiss")

    if backend_type == "faiss":
        from .faiss_store import FaissVectorStore
        logger.info("Creating FAISS vector store backend")
        return FaissVectorStore(config)

    elif backend_type == "qdrant":
        from .qdrant_store import QdrantVectorStore
        logger.info("Creating Qdrant vector store backend")
        return QdrantVectorStore(config)

    else:
        logger.warning("Unknown vector store type: %s, falling back to FAISS", backend_type)
        from .faiss_store import FaissVectorStore
        return FaissVectorStore(config)
