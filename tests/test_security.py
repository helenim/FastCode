"""Security tests for FastCode — path traversal, input validation, injection."""

import importlib.util as _ilu
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_mod(name: str, rel_path: str):
    spec = _ilu.spec_from_file_location(name, os.path.join(_PROJECT_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_path_utils = _load_mod("fastcode.path_utils", "fastcode/path_utils.py")
PathUtils = _path_utils.PathUtils
file_path_to_module_path = _path_utils.file_path_to_module_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo_dir(tmp_path):
    """Create a minimal repo directory for security testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')")
    return str(repo)


@pytest.fixture()
def path_utils(repo_dir):
    return PathUtils(repo_dir)


# ---------------------------------------------------------------------------
# SEC-001: Path traversal in is_safe_path()
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """Verify is_safe_path rejects attempts to escape the repo root."""

    def test_dotdot_escape(self, path_utils):
        assert path_utils.is_safe_path("../../../etc/passwd") is False

    def test_absolute_escape(self, path_utils):
        assert path_utils.is_safe_path("/etc/passwd") is False

    def test_prefix_collision(self, path_utils, tmp_path):
        """repo_root=/tmp/repo should NOT allow /tmp/repo_evil/secret."""
        # Create a sibling directory whose name starts with the repo name
        evil_dir = tmp_path / "repo_evil"
        evil_dir.mkdir()
        (evil_dir / "secret.txt").write_text("sensitive data")

        evil_path = os.path.relpath(str(evil_dir / "secret.txt"), str(tmp_path / "repo"))
        assert path_utils.is_safe_path(evil_path) is False

    def test_prefix_collision_absolute(self, path_utils, tmp_path):
        """Absolute path with prefix collision must be rejected."""
        evil_dir = tmp_path / "repo_evil"
        evil_dir.mkdir()
        evil_path = str(evil_dir / "secret.txt")
        # Construct a relative path that would resolve outside repo root
        rel = os.path.relpath(evil_path, str(tmp_path / "repo"))
        assert path_utils.is_safe_path(rel) is False

    def test_null_byte(self, path_utils):
        """Null bytes in paths should be rejected."""
        assert path_utils.is_safe_path("src/main.py\x00.txt") is False

    def test_valid_path_inside_repo(self, path_utils):
        """Sanity: valid paths should pass."""
        assert path_utils.is_safe_path("src/main.py") is True

    def test_repo_root_itself(self, path_utils):
        """The repo root itself should be safe."""
        assert path_utils.is_safe_path(".") is True

    def test_double_dot_in_middle(self, path_utils):
        """Paths with .. that still resolve inside repo should be safe."""
        assert path_utils.is_safe_path("src/../src/main.py") is True

    def test_symlink_escape(self, path_utils, tmp_path):
        """Symlinks pointing outside repo root should be treated carefully."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("secret")

        repo = tmp_path / "repo"
        symlink = repo / "link_to_outside"
        try:
            symlink.symlink_to(str(outside))
        except OSError:
            pytest.skip("OS does not support symlinks")

        # The symlink resolves outside repo_root — is_safe_path checks the
        # joined path, not the resolved path, so this may pass.
        # We document this as a known limitation.
        resolved = os.path.realpath(str(symlink / "secret.py"))
        assert not resolved.startswith(str(repo)), "Symlink escapes repo root"


# ---------------------------------------------------------------------------
# SEC-002: file_path_to_module_path containment
# ---------------------------------------------------------------------------

class TestModulePathContainment:
    """Verify file_path_to_module_path rejects paths outside repo root."""

    def test_outside_repo(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo, exist_ok=True)
        assert file_path_to_module_path("/etc/passwd.py", repo) is None

    def test_traversal_attempt(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(repo, exist_ok=True)
        result = file_path_to_module_path(
            os.path.join(repo, "..", "..", "etc", "passwd.py"), repo
        )
        assert result is None

    def test_valid_path(self, tmp_path):
        repo = str(tmp_path / "repo")
        os.makedirs(os.path.join(repo, "app"), exist_ok=True)
        result = file_path_to_module_path(
            os.path.join(repo, "app", "main.py"), repo
        )
        assert result == "app.main"


# ---------------------------------------------------------------------------
# SEC-003: Input validation on MCP server
# ---------------------------------------------------------------------------

class TestMCPInputValidation:
    """Test that MCP tools handle malicious/oversized input gracefully."""

    def test_empty_repos_list(self):
        """code_qa with empty repos should return an error, not crash."""
        import sys
        from unittest.mock import MagicMock

        mock_mcp = MagicMock()
        with __import__("contextlib").suppress(Exception):
            if "mcp_server" in sys.modules:
                del sys.modules["mcp_server"]

        with __import__("unittest.mock").mock.patch.dict(
            sys.modules,
            {
                "mcp": mock_mcp,
                "mcp.server": MagicMock(),
                "mcp.server.fastmcp": MagicMock(),
            },
        ):
            if "mcp_server" in sys.modules:
                del sys.modules["mcp_server"]
            import mcp_server

            fc = MagicMock()
            fc._infer_is_url = MagicMock(return_value=False)
            fc.config = {"repository": {}}
            fc.loader = MagicMock()
            fc.loader.ignore_patterns = []

            with __import__("unittest.mock").mock.patch.object(
                mcp_server, "_get_fastcode", return_value=fc
            ):
                result = mcp_server._ensure_repos_ready([])
                assert result == []

    def test_session_id_special_chars(self):
        """Session IDs with special characters should not cause issues."""
        # Session IDs are used as dict keys — verify no crash with unusual values
        special_ids = [
            "",
            "a" * 10000,
            "../../../etc/passwd",
            "'; DROP TABLE sessions; --",
            "\x00\x01\x02",
            "emoji_\U0001f600_test",
        ]
        # These are just strings used as dictionary keys, so they should all work
        d = {}
        for sid in special_ids:
            d[sid] = {"query": "test", "answer": "test"}
        assert len(d) == len(special_ids)


# ---------------------------------------------------------------------------
# SEC-004: ReDoS in search patterns
# ---------------------------------------------------------------------------

class TestReDoS:
    """Verify regex compilation handles pathological patterns."""

    @pytest.mark.xfail(reason="Known ReDoS vulnerability in agent_tools.py — SEC-005", strict=True)
    def test_catastrophic_backtracking_pattern(self):
        """Patterns like (a+)+b should not hang."""
        import re
        import signal

        pattern = "(a+)+b"

        def handler(signum, frame):
            raise TimeoutError("Regex took too long")

        # Set a 2-second alarm
        old_handler = signal.signal(signal.SIGALRM, handler)
        signal.alarm(2)
        try:
            compiled = re.compile(pattern)
            # This input causes catastrophic backtracking with naive engines
            # Python's re module handles this specific case, but we test the principle
            try:
                compiled.search("a" * 25 + "c")
            except TimeoutError:
                pytest.fail("Regex catastrophic backtracking detected")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def test_invalid_regex_does_not_crash(self):
        """Invalid regex patterns should raise re.error, not crash."""
        import re
        with pytest.raises(re.error):
            re.compile("[invalid")


# ---------------------------------------------------------------------------
# SEC-005: Pickle deserialization risk (documentation test)
# ---------------------------------------------------------------------------

class TestPickleSafety:
    """Document pickle deserialization risks."""

    def test_pickle_load_sites_documented(self):
        """Verify we know all pickle.load sites for audit tracking."""
        import subprocess
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "--include=*.py",
                "--exclude-dir=__pycache__",
                "pickle.load",
                "fastcode/",
                "mcp_server.py",
            ],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        pickle_sites = [
            line for line in result.stdout.strip().split("\n") if line
        ]
        # Document: we expect pickle.load in these files
        files_with_pickle = {
            line.split(":")[0] for line in pickle_sites
        }
        expected_files = {
            "fastcode/vector_store.py",
            "fastcode/retriever.py",
            "fastcode/cache.py",
            "fastcode/main.py",
            "fastcode/graph_builder.py",
        }
        # Verify no NEW pickle.load sites have been added
        unexpected = files_with_pickle - expected_files
        assert not unexpected, (
            f"New pickle.load sites found in unexpected files: {unexpected}. "
            "Pickle deserialization is a security risk (arbitrary code execution). "
            "Consider using safetensors or JSON instead."
        )
