"""
Factory for creating embedding providers from configuration.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import EmbeddingProvider

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES = {
    "local": "fastcode.embedding_providers.local_st.LocalSTProvider",
    "ollama": "fastcode.embedding_providers.ollama.OllamaProvider",
    "api": "fastcode.embedding_providers.api.APIProvider",
}


def create_embedding_provider(config: dict[str, Any]) -> EmbeddingProvider:
    """Create an embedding provider based on configuration.

    Reads ``config["embedding"]["provider"]`` to determine which backend to use.
    Defaults to ``"local"`` (SentenceTransformer) for backwards compatibility.

    Args:
        config: Full FastCode configuration dict.

    Returns:
        An object satisfying the EmbeddingProvider protocol.
    """
    emb_cfg = config.get("embedding", {})
    provider_name = emb_cfg.get("provider", "local")

    qualified = _PROVIDER_CLASSES.get(provider_name)
    if qualified is None:
        msg = (
            f"Unknown embedding provider: {provider_name!r}. "
            f"Available: {', '.join(_PROVIDER_CLASSES)}"
        )
        raise ValueError(msg)

    # Lazy import so we only pull in dependencies for the chosen provider
    module_path, class_name = qualified.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    logger.info("Creating embedding provider: %s (%s)", provider_name, qualified)
    return cls(config)
