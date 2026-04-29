"""
Tree-sitter Parser Wrapper.

Provides a simple interface for parsing code with tree-sitter.

Two loading strategies are tried in order:

1. ``tree_sitter_language_pack`` — when installed, this provides the full
   tree-sitter language-pack catalogue (100+ grammars bundled in a single
   wheel). This is the preferred path for full-feature container builds.
2. Individual ``tree-sitter-{lang}`` packages — used as a defensive
   fallback when the language pack is absent (common in slimmed-down
   images). The fallback covers only the languages explicitly enumerated
   in ``_INDIVIDUAL_LOADERS`` below.

Fallback languages currently supported (when their individual wheel is
installed): python, javascript, typescript, tsx, c, cpp, rust, csharp,
java, go, ruby, kotlin, swift.

Missing packages do not crash the parser: ``_load_language`` emits a
WARN log and the caller receives ``ValueError`` so indexing can skip the
file. The previous "170+ languages" marketing claim was tied to the
language-pack path and did NOT apply when only individual packages were
installed — see FINDING-EXT-C-010.
"""

import logging

import tree_sitter
from tree_sitter import Language, Parser

logger = logging.getLogger(__name__)

# Try the language pack first, fall back to individual packages
_USE_LANGUAGE_PACK = False
try:
    from tree_sitter_language_pack import get_language as _pack_get_language

    _USE_LANGUAGE_PACK = True
    logger.debug("Using tree-sitter-language-pack for language loading")
except ImportError:
    logger.debug("tree-sitter-language-pack not available; using individual packages")

# Mapping from our language names to language-pack names (where they differ)
_LANGUAGE_ALIASES: dict[str, str] = {
    "csharp": "c_sharp",
    "cpp": "cpp",
    "c": "c",
}

# Fallback: individual package loaders (only used if language-pack is unavailable)
_INDIVIDUAL_LOADERS: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "csharp": ("tree_sitter_c_sharp", "language"),
    "java": ("tree_sitter_java", "language"),
    "go": ("tree_sitter_go", "language"),
    # FINDING-EXT-C-010: new entries — Ruby / Kotlin / Swift fallback
    # wheels. Each individual package exposes a module-level ``language()``
    # factory compatible with ``tree_sitter.Language(fn())``.
    "ruby": ("tree_sitter_ruby", "language"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "swift": ("tree_sitter_swift", "language"),
}

# Languages for which an individual-package import has already failed in
# this process. Used to throttle WARN logs so we do not spam the operator
# on every file indexed in an unsupported language.
_UNAVAILABLE_LANGUAGES: set[str] = set()


class TSParser:
    """Tree-sitter parser wrapper for multiple languages.

    Primary loader: ``tree-sitter-language-pack`` (bundled grammar
    catalogue). Fallback loader: individual ``tree-sitter-{lang}``
    packages enumerated in ``_INDIVIDUAL_LOADERS``.

    If neither loader can resolve a requested language the constructor
    raises ``ValueError``; callers are expected to catch this and skip
    the file rather than aborting an entire index run.
    """

    def __init__(self, language: str = "python"):
        self.logger = logging.getLogger(__name__)
        self.current_language_name = language.lower()
        self.parser = None
        self.language = None
        self.languages_cache: dict[str, Language] = {}
        self._initialize_parser()

    def _initialize_parser(self):
        """Initialize tree-sitter parser and language."""
        try:
            self.language = self._load_language(self.current_language_name)
            self.parser = Parser(self.language)
            self.logger.debug(
                "Tree-sitter %s parser initialized successfully",
                self.current_language_name,
            )
        except Exception as e:
            self.logger.error(
                "Failed to initialize tree-sitter parser for %s: %s",
                self.current_language_name,
                e,
            )
            raise

    def _load_language(self, language_name: str) -> Language:
        """Load a tree-sitter language, using language-pack or individual packages."""
        if language_name in self.languages_cache:
            return self.languages_cache[language_name]

        lang = None

        # Try language pack first
        if _USE_LANGUAGE_PACK:
            pack_name = _LANGUAGE_ALIASES.get(language_name, language_name)
            try:
                lang = _pack_get_language(pack_name)
                self.logger.debug("Loaded '%s' from language-pack", pack_name)
            except Exception:
                # Language pack doesn't have this language; try individual
                pass

        # Fallback to individual packages
        if lang is None:
            loader_info = _INDIVIDUAL_LOADERS.get(language_name)
            if loader_info:
                module_name, func_name = loader_info
                import importlib

                try:
                    mod = importlib.import_module(module_name)
                except ImportError as exc:
                    # Package not installed in this environment (e.g.
                    # slimmed-down Docker image). Degrade gracefully:
                    # warn once per language, then let the caller raise.
                    # Hook point for future Prometheus counter
                    # ``fastcode_language_unavailable_total{language=...}``.
                    if language_name not in _UNAVAILABLE_LANGUAGES:
                        self.logger.warning(
                            "tree-sitter package '%s' for language '%s' is "
                            "not installed; files in this language will be "
                            "skipped. (%s)",
                            module_name,
                            language_name,
                            exc,
                        )
                        _UNAVAILABLE_LANGUAGES.add(language_name)
                else:
                    lang = Language(getattr(mod, func_name)())
                    self.logger.debug(
                        "Loaded '%s' from individual package %s",
                        language_name,
                        module_name,
                    )

        if lang is None:
            raise ValueError(
                f"Unsupported language: {language_name}. "
                f"Install tree-sitter-language-pack for the bundled grammar "
                f"set, or install the individual tree-sitter-{{lang}} wheel."
            )

        self.languages_cache[language_name] = lang
        return lang

    def set_language(self, language_name: str):
        """Switch the parser to a different language."""
        try:
            self.current_language_name = language_name.lower()
            self.language = self._load_language(self.current_language_name)
            # tree-sitter >=0.23 removed set_language(); must create a new Parser
            self.parser = Parser(self.language)
            self.logger.debug("Switched parser to %s", self.current_language_name)
        except Exception as e:
            self.logger.error("Failed to switch language to %s: %s", language_name, e)
            raise

    def parse(self, code: str, language: str | None = None) -> tree_sitter.Tree | None:
        """Parse code string into a tree-sitter syntax tree."""
        if language and language.lower() != self.current_language_name:
            self.set_language(language)

        if not self.is_healthy():
            self.logger.error("Parser not properly initialized")
            return None

        if code is None or not isinstance(code, str):
            self.logger.warning("Invalid code input: code must be a string")
            return None

        try:
            code_bytes = code.encode("utf-8")
            return self.parser.parse(code_bytes)
        except Exception as e:
            self.logger.error("Failed to parse code: %s", e)
            return None

    def get_language(self) -> Language | None:
        """Get the tree-sitter language object."""
        return self.language

    def is_healthy(self) -> bool:
        """Check if parser is properly initialized and ready."""
        return self.parser is not None and self.language is not None

    @staticmethod
    def supported_languages() -> list[str]:
        """List all supported language names.

        Returns the language-pack's full list if available, otherwise
        returns the individual package list.
        """
        if _USE_LANGUAGE_PACK:
            try:
                import typing

                from tree_sitter_language_pack import SupportedLanguage

                return sorted(typing.get_args(SupportedLanguage))
            except (ImportError, TypeError):
                pass
        return sorted(_INDIVIDUAL_LOADERS.keys())
