"""Tests for ``fastcode.tree_sitter_parser`` — MT-02 (FINDING-EXT-C-010).

Covers the Ruby / Kotlin / Swift fallback-loader additions plus the
defensive-import behaviour used when an individual tree-sitter package
is absent from the environment.

These tests skip (rather than fail) when the underlying tree-sitter
packages are not installed, matching the pattern established by
``test_language_expansion.py`` — CI installs the wheels; sparse dev
environments still let the rest of the suite pass.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Lightweight import shim.
#
# ``fastcode/__init__.py`` eagerly imports heavy LLM dependencies
# (``anthropic``, ``openai``, ``sentence_transformers`` …) which are not
# installed in slim test environments. The whole point of MT-02 is to
# support slim environments, so this test module loads
# ``tree_sitter_parser`` and ``utils`` directly from their source files
# via ``importlib.util.spec_from_file_location``, bypassing the package
# ``__init__``.
#
# ``fastcode.utils`` pulls ``tiktoken`` at module-import time for token
# counting — we do not exercise that path here, so we stub the module
# when it is unavailable.
# ---------------------------------------------------------------------------

_FASTCODE_DIR = Path(__file__).resolve().parent.parent / "fastcode"


def _ensure_stub(mod_name: str, attrs: dict | None = None) -> None:
    """Install a minimal stub module in ``sys.modules`` if the real one
    is missing. Only used to satisfy unrelated top-level imports in
    ``fastcode.utils`` — the test suite never calls into the stub."""
    if mod_name in sys.modules:
        return
    try:
        importlib.import_module(mod_name)
        return
    except ImportError:
        pass
    stub = types.ModuleType(mod_name)
    for k, v in (attrs or {}).items():
        setattr(stub, k, v)
    sys.modules[mod_name] = stub


def _load_module_from_file(mod_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(
        mod_name, _FASTCODE_DIR / rel_path,
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Stub heavy transitive deps of fastcode.utils that are not exercised in
# this test module. If the real package is installed we leave it alone.
_ensure_stub(
    "tiktoken",
    {
        "encoding_for_model": lambda *_a, **_kw: None,
        "get_encoding": lambda *_a, **_kw: None,
    },
)
_ensure_stub("yaml", {"safe_load": lambda *_a, **_kw: {}})

tsp = _load_module_from_file("fastcode_mt02_tsp", "tree_sitter_parser.py")
_utils = _load_module_from_file("fastcode_mt02_utils", "utils.py")

TSParser = tsp.TSParser
get_language_from_extension = _utils.get_language_from_extension


# ---------------------------------------------------------------------------
# Happy path — new languages parse and produce AST nodes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang,code,expected_child_type",
    [
        ("ruby", "def hello\n  puts 'world'\nend\n", "method"),
        ("kotlin", 'fun hello(): String = "world"\n', "function_declaration"),
        (
            "swift",
            'func hello() -> String { return "world" }\n',
            "function_declaration",
        ),
    ],
)
def test_new_language_parses_to_expected_node(lang, code, expected_child_type):
    """Happy path: each new language produces a non-empty AST whose first
    top-level node is the expected declaration type.

    Skip gracefully when neither the language pack nor the individual
    wheel is installed (the fallback loader will warn and raise
    ``ValueError`` in that case)."""
    try:
        parser = TSParser(lang)
    except ValueError as exc:
        pytest.skip(f"Language '{lang}' not available in this environment: {exc}")
    if not parser.is_healthy():  # defensive — environment inconsistency
        pytest.skip(f"Parser for '{lang}' is not healthy in this environment")

    tree = parser.parse(code)
    assert tree is not None, f"{lang}: parse returned None"
    assert tree.root_node is not None
    assert tree.root_node.child_count >= 1, (
        f"{lang}: expected >=1 top-level child, got {tree.root_node.child_count}"
    )
    # Most individual-package grammars emit the expected node type for a
    # plain function/method; when language-pack is used the exact child
    # type can diverge slightly, so only assert on the fallback path.
    if not tsp._USE_LANGUAGE_PACK:
        assert tree.root_node.child(0).type == expected_child_type


# ---------------------------------------------------------------------------
# Defensive import path — missing package degrades gracefully.
# ---------------------------------------------------------------------------


def test_missing_package_raises_value_error_with_warning(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
):
    """When the individual wheel for a language is absent, ``TSParser``
    must raise ``ValueError`` (so the caller can skip the file) and emit
    exactly one WARN log entry per language per process.

    The test forces the fallback path by disabling the language pack and
    monkey-patching ``importlib.import_module`` to raise ``ImportError``
    for the Ruby loader."""
    # Force the fallback branch — independent of whether the language
    # pack happens to be installed on this machine.
    monkeypatch.setattr(tsp, "_USE_LANGUAGE_PACK", False)

    # Reset the "already warned" set so the WARN is emitted for this test.
    monkeypatch.setattr(tsp, "_UNAVAILABLE_LANGUAGES", set())

    real_import = importlib.import_module

    def fake_import(name: str, *a, **kw):
        if name == "tree_sitter_ruby":
            raise ImportError("simulated missing wheel: tree_sitter_ruby")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    caplog.set_level(logging.WARNING, logger=tsp.__name__)

    with pytest.raises(ValueError, match="Unsupported language: ruby"):
        TSParser("ruby")

    warn_msgs = [
        rec.message for rec in caplog.records
        if rec.levelno == logging.WARNING
        and "tree_sitter_ruby" in rec.message
    ]
    assert len(warn_msgs) == 1, (
        f"expected exactly one WARN about tree_sitter_ruby, got: {warn_msgs}"
    )
    assert "ruby" in tsp._UNAVAILABLE_LANGUAGES


def test_missing_package_warning_is_throttled(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch,
):
    """Two consecutive construction attempts for an unavailable language
    should produce only one WARN log entry total — the second call must
    hit the ``_UNAVAILABLE_LANGUAGES`` dedupe."""
    monkeypatch.setattr(tsp, "_USE_LANGUAGE_PACK", False)
    monkeypatch.setattr(tsp, "_UNAVAILABLE_LANGUAGES", set())

    real_import = importlib.import_module

    def fake_import(name: str, *a, **kw):
        if name == "tree_sitter_kotlin":
            raise ImportError("simulated missing wheel")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(importlib, "import_module", fake_import)

    caplog.set_level(logging.WARNING, logger=tsp.__name__)

    for _ in range(2):
        with pytest.raises(ValueError):
            TSParser("kotlin")

    warn_msgs = [
        rec.message for rec in caplog.records
        if rec.levelno == logging.WARNING and "tree_sitter_kotlin" in rec.message
    ]
    assert len(warn_msgs) == 1, (
        f"WARN should be emitted once per language per process; got {warn_msgs}"
    )


# ---------------------------------------------------------------------------
# Extension detection — new routes added by MT-02.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ext,expected",
    [
        (".rb", "ruby"),
        (".rake", "ruby"),
        (".gemspec", "ruby"),
        (".kt", "kotlin"),
        (".kts", "kotlin"),
        (".swift", "swift"),
    ],
)
def test_extension_routes_to_expected_language(ext, expected):
    """File-extension → language routing for the new MT-02 entries."""
    assert get_language_from_extension(ext) == expected


# ---------------------------------------------------------------------------
# Regression — existing languages remain in the fallback loader.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lang",
    ["python", "javascript", "typescript", "tsx", "c", "cpp",
     "rust", "csharp", "java", "go"],
)
def test_existing_loader_entries_retained(lang):
    """The 10 languages that predate MT-02 must still appear in the
    fallback loader map so the pre-existing contract is preserved."""
    assert lang in tsp._INDIVIDUAL_LOADERS


def test_new_loader_entries_present():
    """MT-02 adds ruby / kotlin / swift to the fallback loader map."""
    for lang in ("ruby", "kotlin", "swift"):
        assert lang in tsp._INDIVIDUAL_LOADERS, (
            f"MT-02: '{lang}' missing from _INDIVIDUAL_LOADERS"
        )
        module_name, func_name = tsp._INDIVIDUAL_LOADERS[lang]
        assert module_name == f"tree_sitter_{lang}"
        assert func_name == "language"
