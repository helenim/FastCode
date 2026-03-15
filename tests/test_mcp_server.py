"""Smoke tests for the FastCode MCP server."""

import sys
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
