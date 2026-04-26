"""Workspace-aware repo registry for the ebridge multi-repo MCP facade.

The existing FastCode tools (``code_qa``, ``search_symbol``, …) already accept
``repos: list[str]`` for cross-repo work, but the caller has to know the names
up front. The ebridge workspace is structured (21 git submodules under
``2d-studio-*`` plus in-tree ``shared/ebridge_*`` packages), so we can hand
agents a single registry that enumerates every repo, marks which are
FastCode-indexed today, and feeds the rest of the cross-repo tools.

Source of truth:

* Workspace root is auto-detected by walking up from the cwd looking for a
  ``.gitmodules`` file, or supplied via the ``EBRIDGE_WORKSPACE_ROOT``
  environment variable.
* Repos are discovered on disk: every directory matching ``2d-studio-*`` plus
  every ``shared/ebridge_*`` directory. No additional manifest file is
  required — the workspace layout is the manifest.
* "Indexed" status is derived from the FastCode vector store's existing
  ``scan_available_indexes`` API; we never duplicate that bookkeeping.

This module is intentionally dependency-free (stdlib only) so it can be
imported by ``mcp_server.py`` without dragging the heavy FastCode engine
graph in until a tool is actually called.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

# Marker files that flag a repo as code-bearing. Order is irrelevant — any
# match flips the corresponding language tag.
_CODE_MARKERS: tuple[tuple[str, str], ...] = (
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("package.json", "nodejs"),
    ("composer.json", "php"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
)

WORKSPACE_ENV = "EBRIDGE_WORKSPACE_ROOT"
TENANT_ENV = "EBRIDGE_TENANT_ID"
DEFAULT_TENANT_ID = "_default"


@dataclass(frozen=True)
class WorkspaceRepo:
    """A single repo the registry knows about."""

    name: str
    path: Path
    is_submodule: bool
    classes: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_code(self) -> bool:
        return bool(self.classes & {"python", "nodejs", "php", "rust", "go"})

    def to_dict(self, *, indexed: bool | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "path": str(self.path),
            "is_submodule": self.is_submodule,
            "classes": sorted(self.classes),
            "is_code": self.is_code,
        }
        if indexed is not None:
            out["is_indexed"] = indexed
        return out


def find_workspace_root(start: Path | None = None) -> Path:
    """Locate the workspace root.

    Resolution order:

    1. ``EBRIDGE_WORKSPACE_ROOT`` env var, if set and pointing at a real dir.
    2. Walk up from ``start`` (defaults to cwd) until a ``.gitmodules`` file
       is found.

    Raises ``RuntimeError`` if neither succeeds — callers should surface the
    error to the user rather than silently falling back, since the wrong root
    would point the registry at the wrong tree.
    """
    env = os.environ.get(WORKSPACE_ENV)
    if env:
        root = Path(env).expanduser().resolve()
        if root.is_dir():
            return root
    candidate = (start or Path.cwd()).resolve()
    for parent in (candidate, *candidate.parents):
        if (parent / ".gitmodules").exists():
            return parent
    raise RuntimeError(
        f"could not locate ebridge workspace root from {candidate}; set "
        f"{WORKSPACE_ENV} or run from inside the workspace tree"
    )


def _detect_classes(repo: Path) -> frozenset[str]:
    found: set[str] = set()
    for marker, tag in _CODE_MARKERS:
        if (repo / marker).exists():
            found.add(tag)
    if (repo / "next.config.ts").exists() or (repo / "next.config.js").exists():
        found.add("nextjs")
    return frozenset(found)


def discover_workspace_repos(workspace_root: Path) -> list[WorkspaceRepo]:
    """Enumerate every workspace repo (submodules + shared/ packages)."""
    repos: list[WorkspaceRepo] = []
    for entry in sorted(workspace_root.glob("2d-studio-*")):
        if not entry.is_dir():
            continue
        repos.append(
            WorkspaceRepo(
                name=entry.name,
                path=entry,
                is_submodule=True,
                classes=_detect_classes(entry),
            )
        )
    shared = workspace_root / "shared"
    if shared.is_dir():
        for entry in sorted(shared.iterdir()):
            if not entry.is_dir() or entry.name.startswith((".", "_")):
                continue
            looks_like_pkg = (
                entry.name.startswith("ebridge_")
                or (entry / "pyproject.toml").exists()
                or (entry / "__init__.py").exists()
            )
            if not looks_like_pkg:
                continue
            classes = _detect_classes(entry)
            if entry.name.startswith("ebridge_"):
                classes = classes | {"python"}
            repos.append(
                WorkspaceRepo(
                    name=f"shared/{entry.name}",
                    path=entry,
                    is_submodule=False,
                    classes=classes,
                )
            )
    return repos


@dataclass(frozen=True)
class WorkspaceRegistry:
    """Read-only view of the workspace + cached indexed-status.

    The ``tenant_id`` field is the namespace under which this registry's repos
    are persisted in the FastCode vector store. Single-tenant deployments
    keep the default ``"_default"``; SaaS multi-tenant deployments derive the
    value from the request's tenant scope (Keycloak claim, header, etc.) and
    pass it explicitly to :func:`load_registry`.
    """

    root: Path
    repos: tuple[WorkspaceRepo, ...]
    tenant_id: str = DEFAULT_TENANT_ID

    def names(self, *, code_only: bool = False) -> list[str]:
        return [r.name for r in self.repos if (not code_only) or r.is_code]

    def get(self, name: str) -> WorkspaceRepo | None:
        for r in self.repos:
            if r.name == name:
                return r
        return None

    def namespaced(self, name: str) -> str:
        """Apply the tenant prefix to a bare repo name.

        Returns ``<tenant_id>/<name>`` so callers can store / look up
        artifacts in tenant-scoped vector-store namespaces. Already-prefixed
        names are returned unchanged so the function is idempotent.
        """
        if not name:
            return name
        prefix = f"{self.tenant_id}/"
        if name.startswith(prefix):
            return name
        return f"{prefix}{name}"

    def to_payload(self, indexed_names: Iterable[str] = ()) -> list[dict[str, Any]]:
        indexed = set(indexed_names)
        return [
            {**r.to_dict(indexed=r.name in indexed), "tenant_id": self.tenant_id}
            for r in self.repos
        ]


@lru_cache(maxsize=8)
def _cached_registry(root_str: str, tenant_id: str) -> WorkspaceRegistry:
    root = Path(root_str)
    return WorkspaceRegistry(
        root=root,
        repos=tuple(discover_workspace_repos(root)),
        tenant_id=tenant_id,
    )


def resolve_tenant_id(explicit: str | None = None) -> str:
    """Resolve the active tenant id.

    Precedence: explicit argument > ``EBRIDGE_TENANT_ID`` env var > the
    workspace default ``"_default"``. Empty strings collapse to the default
    so a misconfigured env never silently namespaces under ``""``.
    """
    if explicit:
        return explicit
    env = os.environ.get(TENANT_ENV)
    if env and env.strip():
        return env.strip()
    return DEFAULT_TENANT_ID


def load_registry(
    workspace_root: Path | None = None, *, tenant_id: str | None = None
) -> WorkspaceRegistry:
    """Return the workspace registry, cached per ``(root, tenant_id)`` pair."""
    root = (workspace_root or find_workspace_root()).resolve()
    return _cached_registry(str(root), resolve_tenant_id(tenant_id))


def reset_cache() -> None:
    """Clear the per-process registry cache. Tests + reload workflows only."""
    _cached_registry.cache_clear()
