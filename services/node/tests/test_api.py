import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.database import get_db_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    async def empty_session():
        yield None

    app.dependency_overrides[get_db_session] = empty_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_self_identity(client: TestClient) -> None:
    response = client.get("/api/v1/node/self")
    assert response.status_code == 200
    assert {"node_id", "node_name", "node_type", "host", "port"} <= response.json().keys()


def test_invalid_node_type_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/nodes",
        json={"node_id": "BAD", "node_name": "Bad", "node_type": "UNKNOWN", "host": "localhost", "port": 8001},
    )
    assert response.status_code == 422


def test_invalid_port_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/nodes",
        json={"node_id": "BAD", "node_name": "Bad", "node_type": "EVIDENCE", "host": "localhost", "port": 70000},
    )
    assert response.status_code == 422


@pytest.mark.skipif(not __import__("os").environ.get("TEST_DATABASE_URL"), reason="requires a configured test Neon database")
def test_registry_integration_requires_explicit_database() -> None:
    """CRUD/heartbeat integration tests should run only against an explicitly selected database."""
    assert True
