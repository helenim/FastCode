"""Tests for the cross-tenant collision-guard on repo lookups.

Two complementary layers:

1. **Helper-level** — exercise the pure ``filter_pool_by_namespace`` function
   without instantiating ``RepositorySelector``. Loaded via importlib with
   stub modules so it runs in any clean Python (no SDK install required).

2. **Method-level** — exercise the full ``RepositorySelector._fuzzy_match_repo``
   path end-to-end on a real instance. Requires ``anthropic``, ``openai`` and
   ``python-dotenv`` to be importable; auto-skips otherwise.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_REPO_SELECTOR_PATH = (
    Path(__file__).resolve().parent.parent / "fastcode" / "repo_selector.py"
)


def _stub(name: str, attrs: dict[str, object] | None = None) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    for k, v in (attrs or {}).items():
        setattr(mod, k, v)
    sys.modules[name] = mod


def _load_helper():
    _stub("openai", {"OpenAI": object})
    _stub("anthropic", {"Anthropic": object})
    _stub("dotenv", {"load_dotenv": lambda: None})
    # Belongs to the fastcode package; stub both the parent and the relative
    # import target so the relative `from .llm_utils import …` resolves.
    _stub("fastcode_under_test")
    sys.modules["fastcode_under_test"].__path__ = [str(_REPO_SELECTOR_PATH.parent)]  # type: ignore[attr-defined]
    _stub(
        "fastcode_under_test.llm_utils",
        {"openai_chat_completion": lambda *a, **k: ""},
    )
    spec = importlib.util.spec_from_file_location(
        "fastcode_under_test.repo_selector", _REPO_SELECTOR_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.filter_pool_by_namespace


# ---------------------------------------------------------------------------
# Real-instance loader.
#
# Resolved eagerly at module import time so the SDK-availability probe runs
# BEFORE any helper-fixture stub is injected into sys.modules. Once cached
# into ``_REAL_SELECTOR_CLASS``, the class object stays bound to the real
# anthropic/openai/dotenv modules even if a later fixture stubs them out.
# ---------------------------------------------------------------------------


def _load_real_selector_class():
    for name in ("anthropic", "openai", "dotenv"):
        if importlib.util.find_spec(name) is None:
            return None

    parent_name = "fastcode_real_under_test"
    if parent_name not in sys.modules:
        parent = types.ModuleType(parent_name)
        parent.__path__ = [str(_REPO_SELECTOR_PATH.parent)]  # type: ignore[attr-defined]
        sys.modules[parent_name] = parent

    full_name = f"{parent_name}.repo_selector"
    spec = importlib.util.spec_from_file_location(full_name, _REPO_SELECTOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module.RepositorySelector


_REAL_SELECTOR_CLASS = _load_real_selector_class()


@pytest.fixture(scope="module")
def filter_fn():
    return _load_helper()


@pytest.fixture(scope="module")
def real_selector():
    if _REAL_SELECTOR_CLASS is None:
        pytest.skip("anthropic, openai and python-dotenv must be installed")
    return _REAL_SELECTOR_CLASS(config={})


# ---------------------------------------------------------------------------
# Helper-level tests (run under any Python — no SDK install required).
# ---------------------------------------------------------------------------


def test_passthrough_when_namespace_is_none(filter_fn) -> None:
    pool = ["tenant-a/foo", "tenant-b/foo", "shared-utils"]
    assert filter_fn(pool, None) == pool


def test_passthrough_when_namespace_is_empty_string(filter_fn) -> None:
    pool = ["tenant-a/foo", "shared-utils"]
    assert filter_fn(pool, "") == pool


def test_filters_to_one_tenant(filter_fn) -> None:
    pool = ["tenant-a/api", "tenant-b/api", "shared-utils"]
    assert filter_fn(pool, "tenant-b") == ["tenant-b/api", "shared-utils"]


def test_keeps_unprefixed_shared_entries(filter_fn) -> None:
    pool = ["tenant-a/foo", "shared-utils", "another-tool"]
    assert filter_fn(pool, "tenant-a") == ["tenant-a/foo", "shared-utils", "another-tool"]


def test_excludes_other_tenants(filter_fn) -> None:
    pool = ["tenant-a/private-api", "tenant-b/foo"]
    assert filter_fn(pool, "tenant-b") == ["tenant-b/foo"]


def test_empty_pool_stays_empty(filter_fn) -> None:
    assert filter_fn([], "tenant-x") == []


# ---------------------------------------------------------------------------
# Method-level tests on RepositorySelector._fuzzy_match_repo (skip without SDKs).
# ---------------------------------------------------------------------------


def test_fuzzy_match_namespace_none_passthrough(real_selector) -> None:
    pool = ["tenant-a/api", "tenant-b/api", "shared-utils"]
    assert (
        real_selector._fuzzy_match_repo("shared-utils", pool, namespace=None)
        == "shared-utils"
    )


def test_fuzzy_match_namespace_filters_to_tenant_a(real_selector) -> None:
    pool = ["tenant-a/api", "tenant-b/api", "shared-utils"]
    assert (
        real_selector._fuzzy_match_repo("api", pool, namespace="tenant-a")
        == "tenant-a/api"
    )


def test_fuzzy_match_namespace_excludes_other_tenants(real_selector) -> None:
    pool = ["tenant-a/api", "tenant-b/api"]
    assert (
        real_selector._fuzzy_match_repo("api", pool, namespace="tenant-b")
        == "tenant-b/api"
    )
