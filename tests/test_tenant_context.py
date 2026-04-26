"""Unit tests for the per-request tenant context module.

Loaded via importlib + stub modules so the tests run in any clean Python
without needing the full FastCode dependency tree (faiss, anthropic, …).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_TENANT_PATH = Path(__file__).resolve().parent.parent / "fastcode" / "tenant_context.py"


def _load_tenant_module():
    parent_name = "fastcode_tenant_under_test"
    if parent_name not in sys.modules:
        parent = types.ModuleType(parent_name)
        parent.__path__ = [str(_TENANT_PATH.parent)]  # type: ignore[attr-defined]
        sys.modules[parent_name] = parent
    full_name = f"{parent_name}.tenant_context"
    spec = importlib.util.spec_from_file_location(full_name, _TENANT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_tc = _load_tenant_module()
DEFAULT_TENANT_ID = _tc.DEFAULT_TENANT_ID
TENANT_ENV = _tc.TENANT_ENV
bind_tenant = _tc.bind_tenant
current_tenant_id = _tc.current_tenant_id
tenant_id_from_jwt_claims = _tc.tenant_id_from_jwt_claims


# --- current_tenant_id ----------------------------------------------------

def test_current_returns_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TENANT_ENV, raising=False)
    assert current_tenant_id() == DEFAULT_TENANT_ID


def test_env_var_wins_when_no_contextvar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "tenant-from-env")
    assert current_tenant_id() == "tenant-from-env"


def test_blank_env_collapses_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "   ")
    assert current_tenant_id() == DEFAULT_TENANT_ID


def test_env_value_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "Tenant Acme!")
    # Lowercased + unsupported chars rewritten to underscores.
    assert current_tenant_id() == "tenant_acme_"


# --- bind_tenant ----------------------------------------------------------

def test_bind_tenant_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "tenant-from-env")
    with bind_tenant("tenant-bound") as resolved:
        assert resolved == "tenant-bound"
        assert current_tenant_id() == "tenant-bound"
    # On exit, env wins again.
    assert current_tenant_id() == "tenant-from-env"


def test_bind_tenant_restores_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TENANT_ENV, raising=False)
    with pytest.raises(RuntimeError):
        with bind_tenant("tenant-tx"):
            assert current_tenant_id() == "tenant-tx"
            raise RuntimeError("boom")
    assert current_tenant_id() == DEFAULT_TENANT_ID


def test_bind_tenant_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TENANT_ENV, raising=False)
    with bind_tenant("Tenant/With Spaces"):
        assert current_tenant_id() == "tenant_with_spaces"


# --- tenant_id_from_jwt_claims --------------------------------------------

def test_jwt_claim_first_match_wins() -> None:
    claims = {"tenant_id": "acme", "tenant": "fallback"}
    assert tenant_id_from_jwt_claims(claims) == "acme"


def test_jwt_claim_falls_back_to_secondary() -> None:
    claims = {"tenant": "fallback-tenant"}
    assert tenant_id_from_jwt_claims(claims) == "fallback-tenant"


def test_jwt_claim_falls_back_to_default_when_empty() -> None:
    assert tenant_id_from_jwt_claims({}) == DEFAULT_TENANT_ID
    assert tenant_id_from_jwt_claims({"tenant_id": ""}) == DEFAULT_TENANT_ID


def test_jwt_claim_handles_non_dict() -> None:
    # Real JWT decoders sometimes return None on parse failure.
    assert tenant_id_from_jwt_claims(None) == DEFAULT_TENANT_ID  # type: ignore[arg-type]


def test_jwt_claim_normalizes_value() -> None:
    claims = {"tenant_id": "  ACME-Corp/EU  "}
    assert tenant_id_from_jwt_claims(claims) == "acme-corp_eu"
