"""
WebRTC Endpoints Integration Tests — Part 9.

Tests:
  - POST /api/v1/webrtc/sessions
  - POST /api/v1/webrtc/sessions/{session_id}/stop
  - GET  /api/v1/webrtc/sessions
  - GET  /api/v1/webrtc/sessions/{session_id}
  - WS   /ws/webrtc/{session_id} signaling offer/answer flow
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.node import NodeStatus
from app.webrtc.manager import webrtc_manager
from app.webrtc.schemas import SessionCreateRequest


@pytest.fixture(scope="module")
def webrtc_test_client():
    grpc_mock = MagicMock()
    grpc_mock.stop = AsyncMock()

    with (
        patch("app.database.async_session_factory", None),
        patch("app.messaging.connection.messaging_connection.connect", new_callable=AsyncMock),
        patch("app.messaging.connection.messaging_connection.close", new_callable=AsyncMock),
        patch("app.messaging.consumer.start_consumer", new_callable=AsyncMock),
        patch("app.messaging.consumer.stop_consumer", new_callable=AsyncMock),
        patch("app.grpc.server.start_grpc_server", return_value=AsyncMock(return_value=grpc_mock)),
    ):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        yield client


def test_create_webrtc_session_endpoint(webrtc_test_client):
    """POST /api/v1/webrtc/sessions should return 201 with session_id and signaling_url."""
    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock),
    ):
        resp = webrtc_test_client.post(
            "/api/v1/webrtc/sessions",
            json={
                "node_id": "CCTV-A",
                "incident_id": "INC-000001",
                "media": {"video": True, "audio": True},
            },
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["session_id"].startswith("SESSION-")
    assert data["node_id"] == "CCTV-A"
    assert data["status"] == "REQUESTED"
    assert data["signaling_url"] == f"/ws/webrtc/{data['session_id']}"


def test_stop_webrtc_session_endpoint(webrtc_test_client):
    """POST /api/v1/webrtc/sessions/{session_id}/stop should return status='ENDED'."""
    # Pre-create session in manager
    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock),
    ):
        create_resp = webrtc_test_client.post(
            "/api/v1/webrtc/sessions",
            json={"node_id": "CCTV-A"},
        )
        session_id = create_resp.json()["session_id"]

        stop_resp = webrtc_test_client.post(
            f"/api/v1/webrtc/sessions/{session_id}/stop"
        )

    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "ENDED"


def test_get_webrtc_session_detail_endpoint(webrtc_test_client):
    """GET /api/v1/webrtc/sessions/{session_id} should return session metadata."""
    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock),
    ):
        create_resp = webrtc_test_client.post(
            "/api/v1/webrtc/sessions",
            json={"node_id": "CCTV-A"},
        )
        session_id = create_resp.json()["session_id"]

        get_resp = webrtc_test_client.get(f"/api/v1/webrtc/sessions/{session_id}")

    assert get_resp.status_code == 200
    assert get_resp.json()["session_id"] == session_id
    assert get_resp.json()["source_node_id"] == "CCTV-A"
