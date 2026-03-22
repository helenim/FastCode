"""
Caching Module - Cache embeddings, queries, and results.

Includes:
- CacheManager: Exact-key caching (disk/redis) for embeddings and dialogue history
- SemanticCache: Vector-similarity caching for repeated/similar queries
"""

import hashlib
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np


class _PickleFileCache:
    """File-backed key-value cache with TTL and optional total size limit.

    Replaces the ``diskcache`` dependency (CVE surface in pip-audit). Values are
    pickled; the cache directory must not be writable by untrusted parties.
    """

    def __init__(self, directory: str, size_limit: int | None = None) -> None:
        self._root = Path(directory)
        self._entries = self._root / "entries"
        self._entries.mkdir(parents=True, exist_ok=True)
        self._size_limit = size_limit

    @staticmethod
    def _path(entries: Path, key: str) -> Path:
        h = hashlib.sha256(key.encode("utf-8", errors="replace")).hexdigest()
        return entries / f"{h}.fcache"

    def get(self, key: str) -> Any | None:
        path = self._path(self._entries, key)
        if not path.is_file():
            return None
        try:
            with path.open("rb") as f:
                payload = pickle.load(f)  # nosec B301
            exp = payload.get("exp")
            if exp is not None and time.time() > exp:
                path.unlink(missing_ok=True)
                return None
            return payload.get("val")
        except (OSError, pickle.PickleError, EOFError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def set(self, key: str, value: Any, expire: int | None = None) -> None:
        if self._size_limit:
            self._prune_to_limit()
        exp = time.time() + expire if expire else None
        path = self._path(self._entries, key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp.open("wb") as f:
                pickle.dump({"exp": exp, "val": value, "key": key}, f, protocol=5)
            tmp.replace(path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def delete(self, key: str) -> bool:
        path = self._path(self._entries, key)
        if path.is_file():
            path.unlink()
            return True
        return False

    def clear(self) -> None:
        for path in self._entries.glob("*.fcache"):
            path.unlink(missing_ok=True)

    def __len__(self) -> int:
        return sum(1 for _ in self._entries.glob("*.fcache"))

    def volume(self) -> int:
        return sum(p.stat().st_size for p in self._entries.glob("*.fcache"))

    def iterkeys(self) -> Iterator[str]:
        for path in self._entries.glob("*.fcache"):
            try:
                with path.open("rb") as f:
                    payload = pickle.load(f)  # nosec B301
                k = payload.get("key")
                if isinstance(k, str):
                    yield k
            except (OSError, pickle.PickleError, EOFError, KeyError):
                continue

    def _prune_to_limit(self) -> None:
        if not self._size_limit or self.volume() <= self._size_limit:
            return
        files = sorted(
            self._entries.glob("*.fcache"), key=lambda p: p.stat().st_mtime
        )
        target = int(self._size_limit * 0.85)
        for path in files:
            if self.volume() <= target:
                break
            path.unlink(missing_ok=True)


class CacheManager:
    """Manage caching for FastCode"""

    def __init__(self, config: dict):
        self.config = config
        self.cache_config = config.get("cache", {})
        self.logger = logging.getLogger(__name__)

        self.enabled = self.cache_config.get("enabled", True)
        self.backend = self.cache_config.get("backend", "disk")
        self.ttl = self.cache_config.get("ttl", 3600)
        self.max_size_mb = self.cache_config.get("max_size_mb", 1000)
        self.cache_directory = self.cache_config.get("cache_directory", "./data/cache")

        self.cache_embeddings = self.cache_config.get("cache_embeddings", True)
        self.cache_queries = self.cache_config.get("cache_queries", False)

        # Dialogue history TTL (default: 30 days for long-term conversation history)
        self.dialogue_ttl = self.cache_config.get(
            "dialogue_ttl", 2592000
        )  # 30 days in seconds

        self.cache = None

        if self.enabled:
            self._initialize_cache()

    def _initialize_cache(self):
        """Initialize cache backend"""
        if self.backend == "disk":
            Path(self.cache_directory).mkdir(parents=True, exist_ok=True)
            max_size_bytes = self.max_size_mb * 1024 * 1024
            self.cache = _PickleFileCache(self.cache_directory, size_limit=max_size_bytes)
            self.logger.info(f"Initialized disk cache at {self.cache_directory}")

        elif self.backend == "redis":
            try:
                import redis

                self.cache = redis.Redis(
                    host=os.getenv("REDIS_HOST", "localhost"),
                    port=int(os.getenv("REDIS_PORT", 6379)),
                    db=0,
                    decode_responses=False,
                )
                self.cache.ping()
                self.logger.info("Initialized Redis cache")
            except Exception as e:
                self.logger.error(f"Failed to initialize Redis cache: {e}")
                self.enabled = False

        else:
            self.logger.warning(f"Unknown cache backend: {self.backend}")
            self.enabled = False

    def _generate_key(self, prefix: str, *args) -> str:
        """Generate cache key from arguments"""
        # Create a hash of all arguments
        content = "_".join(str(arg) for arg in args)
        hash_val = hashlib.md5(
            content.encode(),
            usedforsecurity=False,
        ).hexdigest()
        return f"{prefix}_{hash_val}"

    def get(self, key: str) -> Any | None:
        """Get value from cache"""
        if not self.enabled or self.cache is None:
            return None

        try:
            if self.backend == "disk":
                value = self.cache.get(key)
                if value is not None:
                    self.logger.debug(f"Cache hit: {key}")
                return value

            elif self.backend == "redis":
                value = self.cache.get(key)
                if value:
                    self.logger.debug(f"Cache hit: {key}")
                    return pickle.loads(value)  # nosec B301
                return None

        except Exception as e:
            self.logger.warning(f"Cache get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache"""
        if not self.enabled or self.cache is None:
            return False

        if ttl is None:
            ttl = self.ttl

        try:
            if self.backend == "disk":
                self.cache.set(key, value, expire=ttl)
                return True

            elif self.backend == "redis":
                self.cache.setex(key, ttl, pickle.dumps(value))
                return True

        except Exception as e:
            self.logger.warning(f"Cache set error: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled or self.cache is None:
            return False

        try:
            if self.backend == "disk":
                return self.cache.delete(key)
            elif self.backend == "redis":
                return bool(self.cache.delete(key))
        except Exception as e:
            self.logger.warning(f"Cache delete error: {e}")
            return False

    def clear(self) -> bool:
        """Clear all cache"""
        if not self.enabled or self.cache is None:
            return False

        try:
            if self.backend == "disk":
                self.cache.clear()
                self.logger.info("Cleared disk cache")
                return True
            elif self.backend == "redis":
                self.cache.flushdb()
                self.logger.info("Cleared Redis cache")
                return True
        except Exception as e:
            self.logger.error(f"Cache clear error: {e}")
            return False

    def get_embedding(self, text: str) -> Any | None:
        """Get cached embedding"""
        if not self.cache_embeddings:
            return None
        key = self._generate_key("embedding", text)
        return self.get(key)

    def set_embedding(self, text: str, embedding: Any) -> bool:
        """Cache embedding"""
        if not self.cache_embeddings:
            return False
        key = self._generate_key("embedding", text)
        return self.set(key, embedding)

    def get_query_result(self, query: str, repo_hash: str) -> Any | None:
        """Get cached query result"""
        if not self.cache_queries:
            return None
        key = self._generate_key("query", query, repo_hash)
        return self.get(key)

    def set_query_result(self, query: str, repo_hash: str, result: Any) -> bool:
        """Cache query result"""
        if not self.cache_queries:
            return False
        key = self._generate_key("query", query, repo_hash)
        return self.set(key, result)

    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled or self.cache is None:
            return {"enabled": False}

        try:
            if self.backend == "disk":
                return {
                    "enabled": True,
                    "backend": "disk",
                    "size": self.cache.volume(),
                    "items": len(self.cache),
                }
            elif self.backend == "redis":
                info = self.cache.info()
                return {
                    "enabled": True,
                    "backend": "redis",
                    "size": info.get("used_memory", 0),
                    "items": self.cache.dbsize(),
                }
        except Exception as e:
            self.logger.error(f"Failed to get cache stats: {e}")
            return {"enabled": True, "error": str(e)}

    # ===== Multi-turn Dialogue Session Cache Methods =====

    def save_dialogue_turn(
        self,
        session_id: str,
        turn_number: int,
        query: str,
        answer: str,
        summary: str,
        retrieved_elements: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Save a single dialogue turn to cache

        Args:
            session_id: Unique session identifier
            turn_number: Turn number (1-indexed)
            query: User query
            answer: Generated answer
            summary: Brief summary of the dialogue turn
            retrieved_elements: Retrieved code elements (optional)
            metadata: Additional metadata (optional)

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Create turn data
            turn_data = {
                "session_id": session_id,
                "turn_number": turn_number,
                "timestamp": time.time(),
                "query": query,
                "answer": answer,
                "summary": summary,
                "retrieved_elements": retrieved_elements or [],
                "metadata": metadata or {},
            }

            # Generate key
            key = f"dialogue_{session_id}_turn_{turn_number}"

            # Save to cache (with longer TTL for dialogue history)
            # Use configurable dialogue_ttl instead of hardcoded value
            self.set(key, turn_data, ttl=self.dialogue_ttl)

            # Update session index (propagate multi_turn flag from metadata)
            multi_turn = (metadata or {}).get("multi_turn")
            self._update_session_index(session_id, turn_number, multi_turn=multi_turn)

            self.logger.debug(f"Saved dialogue turn: {session_id} turn {turn_number}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save dialogue turn: {e}")
            return False

    def get_dialogue_turn(
        self, session_id: str, turn_number: int
    ) -> dict[str, Any] | None:
        """
        Get a specific dialogue turn from cache

        Args:
            session_id: Session identifier
            turn_number: Turn number to retrieve

        Returns:
            Turn data dictionary or None
        """
        if not self.enabled:
            return None

        key = f"dialogue_{session_id}_turn_{turn_number}"
        return self.get(key)

    def get_dialogue_history(
        self, session_id: str, max_turns: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Get dialogue history for a session

        Args:
            session_id: Session identifier
            max_turns: Maximum number of recent turns to retrieve (None = all)

        Returns:
            List of turn data dictionaries, ordered from oldest to newest
        """
        if not self.enabled:
            return []

        try:
            # Get session index
            session_index = self._get_session_index(session_id)
            if not session_index:
                return []

            total_turns = session_index.get("total_turns", 0)
            if total_turns == 0:
                return []

            # Determine which turns to retrieve
            if max_turns is None or max_turns >= total_turns:
                start_turn = 1
            else:
                start_turn = total_turns - max_turns + 1

            # Retrieve turns
            history = []
            for turn_num in range(start_turn, total_turns + 1):
                turn_data = self.get_dialogue_turn(session_id, turn_num)
                if turn_data:
                    history.append(turn_data)

            return history

        except Exception as e:
            self.logger.error(f"Failed to get dialogue history: {e}")
            return []

    def get_recent_summaries(
        self, session_id: str, num_rounds: int
    ) -> list[dict[str, Any]]:
        """
        Get recent dialogue summaries for context

        Args:
            session_id: Session identifier
            num_rounds: Number of recent rounds to retrieve

        Returns:
            List of summary data with turn_number, query, and summary
        """
        if not self.enabled:
            return []

        try:
            history = self.get_dialogue_history(session_id, max_turns=num_rounds)

            summaries = []
            for turn in history:
                summaries.append(
                    {
                        "turn_number": turn.get("turn_number"),
                        "query": turn.get("query"),
                        "summary": turn.get("summary"),
                    }
                )

            return summaries

        except Exception as e:
            self.logger.error(f"Failed to get recent summaries: {e}")
            return []

    def _update_session_index(
        self, session_id: str, turn_number: int, multi_turn: bool | None = None
    ) -> bool:
        """Update session index with new turn"""
        try:
            key = f"dialogue_session_{session_id}_index"
            session_index = self.get(key) or {
                "session_id": session_id,
                "created_at": time.time(),
                "total_turns": 0,
                "last_updated": time.time(),
                "multi_turn": False,
            }

            session_index["total_turns"] = max(
                session_index["total_turns"], turn_number
            )
            session_index["last_updated"] = time.time()

            # Once a session is marked as multi_turn, keep it that way
            if multi_turn is True:
                session_index["multi_turn"] = True

            # Use configurable dialogue_ttl instead of hardcoded value
            self.set(key, session_index, ttl=self.dialogue_ttl)
            return True

        except Exception as e:
            self.logger.error(f"Failed to update session index: {e}")
            return False

    def _get_session_index(self, session_id: str) -> dict[str, Any] | None:
        """Get session index"""
        key = f"dialogue_session_{session_id}_index"
        return self.get(key)

    def delete_session(self, session_id: str) -> bool:
        """
        Delete an entire dialogue session

        Args:
            session_id: Session identifier

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Get session index
            session_index = self._get_session_index(session_id)
            if not session_index:
                return False

            total_turns = session_index.get("total_turns", 0)

            # Delete all turns
            for turn_num in range(1, total_turns + 1):
                key = f"dialogue_{session_id}_turn_{turn_num}"
                self.delete(key)

            # Delete session index
            index_key = f"dialogue_session_{session_id}_index"
            self.delete(index_key)

            self.logger.info(f"Deleted session {session_id} with {total_turns} turns")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete session: {e}")
            return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all dialogue sessions

        Returns:
            List of session metadata dictionaries
        """
        if not self.enabled or self.cache is None:
            return []

        try:
            sessions = []

            if self.backend == "disk":
                # Scan for session index keys
                for key in self.cache.iterkeys():
                    if (
                        isinstance(key, str)
                        and key.startswith("dialogue_session_")
                        and key.endswith("_index")
                    ):
                        session_data = self.get(key)
                        if session_data:
                            sessions.append(session_data)

            elif self.backend == "redis":
                # Scan for session index keys
                for key in self.cache.scan_iter(match="dialogue_session_*_index"):
                    session_data = self.get(
                        key.decode() if isinstance(key, bytes) else key
                    )
                    if session_data:
                        sessions.append(session_data)

            # Sort by creation time descending (fallback to last_updated)
            sessions.sort(
                key=lambda x: (x.get("created_at", 0), x.get("last_updated", 0)),
                reverse=True,
            )
            return sessions

        except Exception as e:
            self.logger.error(f"Failed to list sessions: {e}")
            return []


class SemanticCache:
    """Vector-similarity cache for code retrieval queries.

    Uses a small in-memory FAISS FlatIP index of past query embeddings.
    When a new query arrives, it checks if a semantically similar query
    has been seen before (cosine similarity >= threshold). On a hit,
    the cached result is returned instantly.

    Cache is scoped by a sorted repo-name key to avoid cross-repo false hits.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.logger = logging.getLogger(__name__)

        sem_cfg = config.get("cache", {}).get("semantic_cache", {})
        self.enabled: bool = sem_cfg.get("enabled", False)
        self.threshold: float = sem_cfg.get("similarity_threshold", 0.90)
        self.max_entries: int = sem_cfg.get("max_entries", 10000)
        self.ttl: int = sem_cfg.get("ttl", 3600)

        # Per-scope caches: scope_key -> (faiss_index, entries_list)
        self._scopes: dict[str, _ScopedCache] = {}

    def lookup(
        self,
        query_embedding: np.ndarray,
        repo_names: list[str],
    ) -> Any | None:
        """Check if a similar query exists in cache.

        Args:
            query_embedding: L2-normalized query embedding vector.
            repo_names: List of repo names (defines cache scope).

        Returns:
            Cached result if similarity >= threshold, else None.
        """
        if not self.enabled:
            return None

        scope = self._get_scope(repo_names)
        if scope is None:
            return None

        return scope.lookup(query_embedding, self.threshold)

    def store(
        self,
        query_embedding: np.ndarray,
        repo_names: list[str],
        result: Any,
    ) -> None:
        """Store a query result in the semantic cache.

        Args:
            query_embedding: L2-normalized query embedding vector.
            repo_names: List of repo names (defines cache scope).
            result: The result to cache.
        """
        if not self.enabled:
            return

        scope_key = self._scope_key(repo_names)
        if scope_key not in self._scopes:
            dim = query_embedding.shape[0]
            self._scopes[scope_key] = _ScopedCache(dim, self.max_entries, self.ttl)

        self._scopes[scope_key].store(query_embedding, result)

    def invalidate(self, repo_names: list[str] | None = None) -> None:
        """Clear semantic cache for specific repos or all repos."""
        if repo_names is None:
            self._scopes.clear()
            self.logger.info("Cleared all semantic cache scopes")
        else:
            key = self._scope_key(repo_names)
            if key in self._scopes:
                del self._scopes[key]
                self.logger.info("Cleared semantic cache for scope: %s", key)

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total_entries = sum(s.count for s in self._scopes.values())
        return {
            "enabled": self.enabled,
            "scopes": len(self._scopes),
            "total_entries": total_entries,
            "threshold": self.threshold,
        }

    def _scope_key(self, repo_names: list[str]) -> str:
        return "|".join(sorted(repo_names))

    def _get_scope(self, repo_names: list[str]) -> "_ScopedCache | None":
        key = self._scope_key(repo_names)
        return self._scopes.get(key)


class _ScopedCache:
    """Internal: per-scope FAISS index + result storage with TTL."""

    def __init__(self, dim: int, max_entries: int, ttl: int) -> None:
        import faiss

        self._index = faiss.IndexFlatIP(dim)
        self._entries: list[tuple[float, Any]] = []  # (timestamp, result)
        self._max_entries = max_entries
        self._ttl = ttl
        self._dim = dim

    @property
    def count(self) -> int:
        return self._index.ntotal

    def lookup(self, query_vec: np.ndarray, threshold: float) -> Any | None:
        if self._index.ntotal == 0:
            return None

        query = query_vec.reshape(1, -1).astype(np.float32)
        distances, indices = self._index.search(query, 1)

        if distances[0][0] >= threshold:
            idx = int(indices[0][0])
            if idx < len(self._entries):
                timestamp, result = self._entries[idx]
                if time.time() - timestamp <= self._ttl:
                    return result
        return None

    def store(self, query_vec: np.ndarray, result: Any) -> None:
        # Evict oldest entries if at capacity
        if self._index.ntotal >= self._max_entries:
            self._evict_oldest()

        vec = query_vec.reshape(1, -1).astype(np.float32)
        self._index.add(vec)
        self._entries.append((time.time(), result))

    def _evict_oldest(self) -> None:
        """Rebuild index without the oldest 10% of entries."""
        import faiss

        keep_from = max(1, len(self._entries) // 10)
        self._entries = self._entries[keep_from:]

        # Rebuild FAISS index from remaining vectors
        new_index = faiss.IndexFlatIP(self._dim)
        # We don't store the vectors separately, so we must reconstruct them
        if self._index.ntotal > keep_from:
            vectors = np.zeros((self._index.ntotal - keep_from, self._dim), dtype=np.float32)
            for i in range(keep_from, self._index.ntotal):
                vectors[i - keep_from] = self._index.reconstruct(i)
            new_index.add(vectors)
        self._index = new_index
