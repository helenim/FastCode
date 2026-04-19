"""Pytest conftest for fastcode.

macOS ARM64 segfaults when torch and faiss share a process (duplicate
OpenMP/libomp runtime). Setting ``KMP_DUPLICATE_LIB_OK=TRUE`` before the
native libs load lets them coexist. This conftest runs at session start
so the env var is set before any test imports faiss or torch.
"""

from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
