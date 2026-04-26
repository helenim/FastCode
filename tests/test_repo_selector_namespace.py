"""Tests for the namespace-aware filter that backs ``_fuzzy_match_repo``.

The filter is extracted to ``fastcode.repo_selector.filter_pool_by_namespace``
as a pure helper so it can be tested without instantiating the full
``RepositorySelector`` (whose ``__init__`` pulls in the OpenAI / Anthropic
SDKs and python-dotenv). The test loads the function via importlib with a
small set of stub modules so it runs in any clean Python.
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


@pytest.fixture(scope="module")
def filter_fn():
    return _load_helper()


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
