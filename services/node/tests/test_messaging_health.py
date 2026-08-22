"""
Messaging health endpoint tests — Part 6.

Verifies:
  - GET /health/messaging returns 200 {"status": "healthy"} when RabbitMQ is up
  - GET /health/messaging returns 503 {"status": "unhealthy"} when RabbitMQ is down
  - GET /health includes rabbitmq component status
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.database import get_db_session
from app.main import app


@pytest.fixture
def client() -> TestClient:
    async def empty_session():
        yield None

    app.dependency_overrides[get_db_session] = empty_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_messaging_health_healthy(client: TestClient) -> None:
    """When RabbitMQ connection is healthy, endpoint returns 200 + 'healthy'."""
    from app.messaging import connection as conn_module

    with patch.object(conn_module.messaging_connection, "is_healthy", return_value=True):
        response = client.get("/health/messaging")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "rabbitmq"
    assert data["status"] == "healthy"


def test_messaging_health_unhealthy(client: TestClient) -> None:
    """When RabbitMQ is down, endpoint returns 503 + 'unhealthy'."""
    from app.messaging import connection as conn_module

    with patch.object(conn_module.messaging_connection, "is_healthy", return_value=False):
        response = client.get("/health/messaging")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["status"] == "unhealthy"


def test_health_includes_rabbitmq_component(client: TestClient) -> None:
    """GET /health must include a 'rabbitmq' field in components."""
    from app.messaging import connection as conn_module

    with patch.object(conn_module.messaging_connection, "is_healthy", return_value=True):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "components" in data
    assert "rabbitmq" in data["components"]


def test_health_rabbitmq_unhealthy_is_reported(client: TestClient) -> None:
    """When RabbitMQ is down, /health must show rabbitmq = 'unhealthy'."""
    from app.messaging import connection as conn_module

    with patch.object(conn_module.messaging_connection, "is_healthy", return_value=False):
        response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["components"]["rabbitmq"] == "unhealthy"
