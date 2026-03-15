"""Smoke tests for the FastCode REST API."""

import importlib
import sys
from unittest.mock import MagicMock, patch


def test_app_creates_successfully():
    """Verify the FastAPI app object is importable and has expected metadata."""
    # Mock the FastCode dependency so we don't need FAISS/torch
    mock_fastcode = MagicMock()
    with patch.dict(sys.modules, {"fastcode": mock_fastcode}):
        # Force reimport
        if "api" in sys.modules:
            del sys.modules["api"]
        import api

        assert api.app is not None
        assert api.app.title == "FastCode API"
        assert api.app.version == "2.0.0"


def test_pydantic_models_validate():
    """Verify Pydantic request/response models accept valid data."""
    mock_fastcode = MagicMock()
    with patch.dict(sys.modules, {"fastcode": mock_fastcode}):
        if "api" in sys.modules:
            del sys.modules["api"]
        import api

        req = api.LoadRepositoryRequest(source="https://github.com/example/repo")
        assert req.source == "https://github.com/example/repo"

        query = api.QueryRequest(question="How does auth work?")
        assert query.question == "How does auth work?"
        assert query.multi_turn is False


def test_health_endpoint_exists():
    """Verify /health route is registered on the app."""
    mock_fastcode = MagicMock()
    with patch.dict(sys.modules, {"fastcode": mock_fastcode}):
        if "api" in sys.modules:
            del sys.modules["api"]
        import api

        routes = [r.path for r in api.app.routes]
        assert "/health" in routes
