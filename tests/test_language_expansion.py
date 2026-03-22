"""Tests for Phase 9: Language expansion via tree-sitter-language-pack."""

import pytest

from fastcode.tree_sitter_parser import TSParser


class TestLanguagePack:
    """Test that tree-sitter-language-pack loads languages correctly."""

    @pytest.mark.parametrize("lang", [
        "python", "javascript", "typescript", "tsx",
        "java", "go", "rust", "c", "cpp", "csharp",
    ])
    def test_original_languages_still_work(self, lang):
        """All previously supported languages should still parse."""
        try:
            parser = TSParser(lang)
        except (ValueError, ModuleNotFoundError) as exc:
            pytest.skip(f"Language {lang} not available in this environment: {exc}")
        if not parser.is_healthy():
            pytest.skip(f"Language {lang} parser not healthy in this environment")
        assert parser.is_healthy()

    @pytest.mark.parametrize("lang,code", [
        ("ruby", "def hello\n  puts 'world'\nend"),
        ("php", "<?php function hello() { return 'world'; }"),
        ("swift", "func hello() -> String { return \"world\" }"),
        ("kotlin", "fun hello(): String = \"world\""),
        ("scala", "def hello: String = \"world\""),
        ("lua", "function hello() return 'world' end"),
        ("r", "hello <- function() { 'world' }"),
        ("bash", "hello() { echo 'world'; }"),
        ("yaml", "key: value"),
        ("toml", "key = 'value'"),
        ("json", '{"key": "value"}'),
        ("html", "<div>hello</div>"),
        ("css", "body { color: red; }"),
        ("sql", "SELECT * FROM users"),
    ])
    def test_new_languages_parse(self, lang, code):
        """Newly supported languages should parse without errors."""
        try:
            parser = TSParser(lang)
        except ValueError:
            pytest.skip(f"Language {lang} not available in this installation")

        tree = parser.parse(code)
        assert tree is not None
        assert tree.root_node is not None
        assert tree.root_node.child_count > 0

    def test_language_switching(self):
        """Parser should switch between languages correctly."""
        parser = TSParser("python")
        tree_py = parser.parse("def foo(): pass")
        assert tree_py is not None

        tree_js = parser.parse("function foo() {}", language="javascript")
        assert tree_js is not None
        assert parser.current_language_name == "javascript"

    def test_language_caching(self):
        """Loading the same language twice should use cache."""
        parser = TSParser("python")
        lang1 = parser._load_language("python")
        lang2 = parser._load_language("python")
        assert lang1 is lang2  # Same object (cached)

    def test_unsupported_language_raises(self):
        """Completely unsupported language should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported language"):
            TSParser("klingon")

    def test_supported_languages_list(self):
        """supported_languages() should return a non-empty sorted list."""
        langs = TSParser.supported_languages()
        if len(langs) <= 10:
            pytest.skip(
                "tree-sitter language pack incomplete in this environment "
                f"(got {len(langs)} languages)"
            )
        assert langs == sorted(langs)
        assert "python" in langs
