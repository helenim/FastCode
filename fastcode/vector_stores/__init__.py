"""
Vector Store backends — pluggable storage for code embeddings.

Supported backends:
- faiss: FAISS HNSW/Flat (default, no infrastructure needed)
- qdrant: Qdrant vector database (production-grade CRUD, filtering, persistence)
"""

from .base import VectorStoreBackend
from .factory import create_vector_store

__all__ = ["VectorStoreBackend", "create_vector_store"]
