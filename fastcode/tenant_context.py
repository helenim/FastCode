"""Per-request tenant context for FastCode.

The vector store, retriever and graph builder were all single-tenant by
construction (everything lived flat under ``persist_dir``). For SaaS multi-
tenant deployment we need to scope every on-disk artifact to a tenant
namespace — typically derived from a Keycloak claim on the inbound MCP /
HTTP request.

This module provides:

* A `tenant_id_var` ContextVar (asyncio + thread-safe) that callers stamp
  at the request boundary.
* `current_tenant_id()` — the function the vector store + friends call
  whenever they need to compute a path. Falls back to the
  `EBRIDGE_TENANT_ID` env var, then to the workspace-default
  ``"_default"`` so single-tenant local dev keeps working unchanged.
* `bind_tenant()` — context manager / decorator helper that sets the var
  for the duration of a tool / request handler.
* `tenant_id_from_jwt_claims()` — pure utility that maps a Keycloak token's
  claim dictionary to a stable, filesystem-safe tenant id. Kept pure so
  whatever middleware the project bolts on (FastAPI dep, FastMCP tool
  wrapper, raw Starlette middleware) can wire it without bringing this
  module into the network path.

The default tenant id is intentionally a leading underscore so it sorts
ahead of any real tenant directory and is easy to grep for during
incident review.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from contextvars import ContextVar
from typing import Any, Iterator

DEFAULT_TENANT_ID = "_default"
TENANT_ENV = "EBRIDGE_TENANT_ID"
JWT_CLAIM_CANDIDATES: tuple[str, ...] = (
    # Order matters — first match wins. Aligns with the workspace's
    # Keycloak realm conventions (`tenant_id` custom mapper) plus the
    # multi-tenant audience-style fallbacks ebridge has standardised on.
    "tenant_id",
    "tenant",
    "ebridge_tenant",
    "https://ebridge.dev/tenant_id",
    "azp",  # last resort: client id
)
_TENANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")

tenant_id_var: ContextVar[str | None] = ContextVar("ebridge_tenant_id", default=None)


def current_tenant_id() -> str:
    """Resolve the active tenant id.

    Precedence:

    1. The contextvar value (set by `bind_tenant` / middleware) — wins,
       even if an env override is present, so per-request scopes never
       leak into a process-wide setting.
    2. The ``EBRIDGE_TENANT_ID`` env var — useful for single-tenant
       containers and the legacy CLI workflow.
    3. ``"_default"`` — the workspace-wide fallback.
    """
    value = tenant_id_var.get()
    if value:
        return value
    env = os.environ.get(TENANT_ENV)
    if env and env.strip():
        return _normalize(env)
    return DEFAULT_TENANT_ID


@contextlib.contextmanager
def bind_tenant(tenant_id: str | None) -> Iterator[str]:
    """Set the tenant id for the duration of the with-block.

    Yields the resolved tenant id (the one actually written to the var)
    so callers can log / propagate it. Always restores the previous token
    on exit, even on exception.
    """
    resolved = _normalize(tenant_id) if tenant_id else current_tenant_id()
    token = tenant_id_var.set(resolved)
    try:
        yield resolved
    finally:
        tenant_id_var.reset(token)


def tenant_id_from_jwt_claims(claims: dict[str, Any]) -> str:
    """Extract a stable tenant id from a decoded Keycloak JWT.

    Walks ``JWT_CLAIM_CANDIDATES`` in order; the first non-empty string
    wins. Returns the workspace default when no candidate is present so
    callers can still bind unconditionally without raising.
    """
    if not isinstance(claims, dict):
        return DEFAULT_TENANT_ID
    for key in JWT_CLAIM_CANDIDATES:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize(value)
    return DEFAULT_TENANT_ID


def _normalize(value: str) -> str:
    """Filesystem-safe rewrite of an arbitrary tenant id.

    Strips whitespace, lowercases, replaces unsupported characters with
    underscores, and caps the length. Empty input maps to the default.
    """
    cleaned = value.strip().lower()
    if not cleaned:
        return DEFAULT_TENANT_ID
    safe = "".join(ch if _TENANT_ID_PATTERN.fullmatch(ch) else "_" for ch in cleaned)
    return safe[:64] or DEFAULT_TENANT_ID


# ---------------------------------------------------------------------------
# Thread-local sanity guards
# ---------------------------------------------------------------------------
# Some FastCode codepaths spawn worker threads. ContextVars copy across
# asyncio contexts but NOT across threads created with raw `threading.Thread`.
# We expose a tiny helper that captures the current tenant and re-binds it
# inside the worker — callers can opt in via `Thread(target=run_with_tenant)`.

def run_with_tenant(target, /, *args, **kwargs):
    """Run ``target(*args, **kwargs)`` in a worker thread with the same
    tenant id the caller currently has bound."""
    captured = current_tenant_id()

    def _run() -> None:
        with bind_tenant(captured):
            target(*args, **kwargs)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
