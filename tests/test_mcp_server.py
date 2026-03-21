"""Smoke tests for the FastCode MCP server."""

import sys
import types
from unittest.mock import MagicMock, patch


def test_mcp_server_module_imports():
    """Verify the MCP server module can be imported without errors."""
    # Mock heavy dependencies
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    mock_fastcode = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": mock_fastcode,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        # The module should import without raising
        import mcp_server

        assert hasattr(mcp_server, "mcp") or hasattr(mcp_server, "app")


def _fake_fastcode_package_for_mcp():
    """Minimal `fastcode` + `fastcode.utils` so mcp helpers can import safely."""
    utils_mod = types.ModuleType("fastcode.utils")

    def _get_repo_name_from_url(url: str) -> str:
        return "repo-from-url"

    utils_mod.get_repo_name_from_url = _get_repo_name_from_url  # type: ignore[attr-defined]
    fc_pkg = types.ModuleType("fastcode")
    fc_pkg.utils = utils_mod  # type: ignore[attr-defined]
    return fc_pkg, utils_mod


def test_repo_name_from_local_path():
    """`_repo_name_from_source` local-path branch does not touch FastCode."""
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        assert mcp_server._repo_name_from_source("/tmp/myproject", False) == "myproject"


def test_repo_name_from_url_uses_utils():
    """URL branch delegates naming to `fastcode.utils.get_repo_name_from_url`."""
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        assert (
            mcp_server._repo_name_from_source("https://github.com/org/repo", True)
            == "repo-from-url"
        )


def test_apply_forced_env_excludes_adds_site_packages_when_env_enabled():
    """Optional FASTCODE_EXCLUDE_SITE_PACKAGES extends forced ignore patterns."""
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        fc = MagicMock()
        fc.config = {"repository": {}}
        fc.loader = MagicMock()
        fc.loader.ignore_patterns = []

        with patch.dict("os.environ", {"FASTCODE_EXCLUDE_SITE_PACKAGES": "1"}):
            mcp_server._apply_forced_env_excludes(fc)

        patterns = fc.config["repository"]["ignore_patterns"]
        assert "site-packages" in patterns


def test_is_repo_indexed_false_when_index_files_missing():
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        fc = MagicMock()
        fc.vector_store.persist_dir = "/data/indexes"

        with patch.object(mcp_server, "_get_fastcode", return_value=fc):
            with patch.object(mcp_server.os.path, "exists", return_value=False):
                assert mcp_server._is_repo_indexed("missing") is False


def test_is_repo_indexed_true_when_faiss_and_metadata_exist():
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        fc = MagicMock()
        fc.vector_store.persist_dir = "/data/indexes"

        def _exists(path: str) -> bool:
            return path.endswith("myrepo.faiss") or path.endswith("myrepo_metadata.pkl")

        with patch.object(mcp_server, "_get_fastcode", return_value=fc):
            with patch.object(mcp_server.os.path, "exists", side_effect=_exists):
                assert mcp_server._is_repo_indexed("myrepo") is True


def test_ensure_repos_ready_skips_clone_when_already_indexed():
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        fc = MagicMock()
        fc._infer_is_url = MagicMock(return_value=True)
        fc.config = {"repository": {}}
        fc.loader = MagicMock()
        fc.loader.ignore_patterns = []

        with patch.object(mcp_server, "_get_fastcode", return_value=fc):
            with patch.object(mcp_server, "_is_repo_indexed", return_value=True):
                ready = mcp_server._ensure_repos_ready(
                    ["https://github.com/example/demo"],
                )

        assert ready == ["repo-from-url"]
        fc.load_repository.assert_not_called()


def test_apply_forced_env_excludes_merges_patterns():
    """Forced ignore patterns are merged into repo config and loader."""
    mock_mcp = MagicMock()
    mock_fastmcp = MagicMock()
    fc_pkg, utils_mod = _fake_fastcode_package_for_mcp()

    with patch.dict(
        sys.modules,
        {
            "mcp": mock_mcp,
            "mcp.server": MagicMock(),
            "mcp.server.fastmcp": mock_fastmcp,
            "fastcode": fc_pkg,
            "fastcode.utils": utils_mod,
        },
    ):
        if "mcp_server" in sys.modules:
            del sys.modules["mcp_server"]
        import mcp_server

        fc = MagicMock()
        fc.config = {"repository": {"ignore_patterns": ["custom"]}}
        fc.loader = MagicMock()
        fc.loader.ignore_patterns = []

        mcp_server._apply_forced_env_excludes(fc)

        patterns = fc.config["repository"]["ignore_patterns"]
        assert "custom" in patterns
        assert ".venv" in patterns
        assert fc.loader.ignore_patterns == patterns
