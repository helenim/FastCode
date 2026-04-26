"""Tests for the workspace-aware repo registry.

Loads ``fastcode.workspace_registry`` via importlib so we don't trigger the
heavyweight ``fastcode/__init__.py`` (which eagerly imports anthropic and the
full LLM stack). The module is intentionally stdlib-only so it can be tested
without those deps; this loader enforces that contract.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_PATH = _HERE.parent / "fastcode" / "workspace_registry.py"


def _load_workspace_registry():
    spec = importlib.util.spec_from_file_location(
        "fastcode_workspace_registry_under_test", _MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_wr = _load_workspace_registry()
WORKSPACE_ENV = _wr.WORKSPACE_ENV
TENANT_ENV = _wr.TENANT_ENV
DEFAULT_TENANT_ID = _wr.DEFAULT_TENANT_ID
discover_workspace_repos = _wr.discover_workspace_repos
find_workspace_root = _wr.find_workspace_root
load_registry = _wr.load_registry
resolve_tenant_id = _wr.resolve_tenant_id
reset_cache = _wr.reset_cache


def _make_python_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    return repo


def _make_node_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "package.json").write_text("{}")
    return repo


def _make_docs_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("# docs")
    return repo


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".gitmodules").write_text("")
    _make_python_repo(tmp_path, "2d-studio-ebridge-agent-runtime")
    _make_node_repo(tmp_path, "2d-studio-ebridge-ux")
    _make_docs_repo(tmp_path, "2d-studio-ebridge-docs-manual")
    shared = tmp_path / "shared"
    _make_python_repo(shared, "ebridge_logging")
    (shared / "ebridge_no_pyproject").mkdir()  # ebridge_-prefixed → still picked up
    (shared / "ebridge_no_pyproject" / "__init__.py").write_text("")
    monkeypatch.setenv(WORKSPACE_ENV, str(tmp_path))
    reset_cache()
    yield tmp_path
    reset_cache()


def test_find_workspace_root_uses_env(workspace: Path) -> None:
    assert find_workspace_root() == workspace


def test_find_workspace_root_walks_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    (tmp_path / ".gitmodules").write_text("")
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    assert find_workspace_root(start=nested) == tmp_path.resolve()


def test_find_workspace_root_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(WORKSPACE_ENV, raising=False)
    with pytest.raises(RuntimeError):
        find_workspace_root(start=tmp_path)


def test_discover_includes_submodules_and_shared(workspace: Path) -> None:
    repos = discover_workspace_repos(workspace)
    names = {r.name for r in repos}
    assert "2d-studio-ebridge-agent-runtime" in names
    assert "2d-studio-ebridge-ux" in names
    assert "2d-studio-ebridge-docs-manual" in names
    assert "shared/ebridge_logging" in names
    assert "shared/ebridge_no_pyproject" in names


def test_classes_picked_up_from_marker_files(workspace: Path) -> None:
    repos = {r.name: r for r in discover_workspace_repos(workspace)}
    assert "python" in repos["2d-studio-ebridge-agent-runtime"].classes
    assert "nodejs" in repos["2d-studio-ebridge-ux"].classes
    assert repos["2d-studio-ebridge-docs-manual"].classes == frozenset()


def test_shared_ebridge_packages_force_python_class(workspace: Path) -> None:
    repos = {r.name: r for r in discover_workspace_repos(workspace)}
    assert "python" in repos["shared/ebridge_no_pyproject"].classes


def test_load_registry_is_cached(workspace: Path) -> None:
    a = load_registry()
    b = load_registry()
    assert a is b


def test_to_payload_marks_indexed(workspace: Path) -> None:
    registry = load_registry()
    payload = registry.to_payload(indexed_names={"2d-studio-ebridge-agent-runtime"})
    by_name = {row["name"]: row for row in payload}
    assert by_name["2d-studio-ebridge-agent-runtime"]["is_indexed"] is True
    assert by_name["2d-studio-ebridge-ux"]["is_indexed"] is False


def test_names_code_only_filter(workspace: Path) -> None:
    registry = load_registry()
    all_names = registry.names()
    code_names = registry.names(code_only=True)
    assert "2d-studio-ebridge-docs-manual" in all_names
    assert "2d-studio-ebridge-docs-manual" not in code_names
    assert "2d-studio-ebridge-agent-runtime" in code_names


def test_get_by_name(workspace: Path) -> None:
    registry = load_registry()
    repo = registry.get("2d-studio-ebridge-ux")
    assert repo is not None
    assert "nodejs" in repo.classes
    assert registry.get("nonexistent") is None


# --- per-tenant namespacing (H) ------------------------------------------

def test_resolve_tenant_id_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TENANT_ENV, raising=False)
    assert resolve_tenant_id() == DEFAULT_TENANT_ID


def test_resolve_tenant_id_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "tenant-42")
    assert resolve_tenant_id() == "tenant-42"


def test_resolve_tenant_id_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TENANT_ENV, "tenant-from-env")
    assert resolve_tenant_id("tenant-explicit") == "tenant-explicit"


def test_resolve_tenant_id_blank_env_collapses_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TENANT_ENV, "   ")
    assert resolve_tenant_id() == DEFAULT_TENANT_ID


def test_load_registry_picks_tenant_from_env(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TENANT_ENV, "tenant-acme")
    reset_cache()
    registry = load_registry()
    assert registry.tenant_id == "tenant-acme"


def test_namespaced_prefixes_repo_name(workspace: Path) -> None:
    reset_cache()
    registry = load_registry(tenant_id="tenant-x")
    assert registry.namespaced("2d-studio-ebridge-ux") == "tenant-x/2d-studio-ebridge-ux"
    # idempotent: already-prefixed names are returned unchanged.
    assert registry.namespaced("tenant-x/foo") == "tenant-x/foo"


def test_to_payload_includes_tenant_id(workspace: Path) -> None:
    reset_cache()
    registry = load_registry(tenant_id="tenant-y")
    payload = registry.to_payload()
    assert all(row["tenant_id"] == "tenant-y" for row in payload)


def test_load_registry_caches_per_tenant(workspace: Path) -> None:
    reset_cache()
    a1 = load_registry(tenant_id="A")
    a2 = load_registry(tenant_id="A")
    b = load_registry(tenant_id="B")
    assert a1 is a2  # same tenant → cached singleton
    assert a1 is not b  # different tenant → distinct registry
