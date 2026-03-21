"""Smoke tests for the FastCode REST API."""

import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


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


def test_health_via_test_client():
    """Exercise the /health handler (initializing branch when no FastCode instance)."""
    mock_fastcode = MagicMock()
    with patch.dict(sys.modules, {"fastcode": mock_fastcode}):
        if "api" in sys.modules:
            del sys.modules["api"]
        import api

        client = TestClient(api.app)
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "initializing"


def test_remaining_pydantic_models_validate():
    """Cover auxiliary request/response models used by the API surface."""
    mock_fastcode = MagicMock()
    with patch.dict(sys.modules, {"fastcode": mock_fastcode}):
        if "api" in sys.modules:
            del sys.modules["api"]
        import api

        lr = api.LoadRepositoriesRequest(repo_names=["a", "b"])
        assert lr.repo_names == ["a", "b"]

        im = api.IndexMultipleRequest(
            sources=[api.LoadRepositoryRequest(source="https://github.com/x/y")]
        )
        assert len(im.sources) == 1

        ns = api.NewSessionResponse(session_id="sess-1")
        assert ns.session_id == "sess-1"

        dr = api.DeleteReposRequest(repo_names=["r1"], delete_source=False)
        assert dr.delete_source is False

        st = api.StatusResponse(
            status="ready",
            repo_loaded=True,
            repo_indexed=True,
            repo_info={},
        )
        assert st.status == "ready"
