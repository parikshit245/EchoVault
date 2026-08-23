"""
P2P Endpoints Integration Tests — Part 8.

Tests:
  - /ws/peer WebSocket endpoint handshake and direct communication
  - /health/p2p health endpoint
  - /api/v1/peers management REST endpoints
  - /api/v1/peers/messages message inbox querying
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.fixture(scope="module")
def p2p_test_client():
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


def test_p2p_health_endpoint(p2p_test_client):
    """GET /health/p2p should return 200 with service='p2p' and connected_peers count."""
    resp = p2p_test_client.get("/health/p2p")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "p2p"
    assert data["status"] == "healthy"
    assert isinstance(data["connected_peers"], int)


def test_overall_health_includes_p2p(p2p_test_client):
    """GET /health should report p2p component status."""
    with patch("app.routers.health.check_database_connection", new_callable=AsyncMock):
        resp = p2p_test_client.get("/health")
        assert resp.status_code == 200
        components = resp.json()["components"]
        assert "p2p" in components
        assert components["p2p"] == "healthy"


def test_ws_peer_handshake_flow(p2p_test_client):
    """Connecting to /ws/peer and sending HANDSHAKE receives HANDSHAKE_ACK."""
    with p2p_test_client.websocket_connect("/ws/peer") as ws:
        # 1. Send Handshake
        handshake_env = {
            "message_type": "HANDSHAKE",
            "source_node_id": "CCTV-B",
            "target_node_id": "node-dev-001",
            "payload": {
                "node_id": "CCTV-B",
                "node_name": "CCTV Camera B",
                "node_type": "EVIDENCE",
                "p2p_host": "localhost",
                "p2p_port": 8002,
            },
        }
        ws.send_text(json.dumps(handshake_env))

        # 2. Receive Handshake Ack
        ack_raw = ws.receive_text()
        ack = json.loads(ack_raw)

        assert ack["message_type"] == "HANDSHAKE_ACK"
        assert ack["payload"]["status"] == "ACCEPTED"
        assert ack["payload"]["node_id"] == "node-dev-001"


def test_ws_peer_invalid_first_message_rejected(p2p_test_client):
    """Sending a non-HANDSHAKE first message is rejected."""
    with p2p_test_client.websocket_connect("/ws/peer") as ws:
        ws.send_text(json.dumps({"message_type": "PING", "payload": {}}))
        ack_raw = ws.receive_text()
        ack = json.loads(ack_raw)
        assert ack["status"] == "REJECTED"


def test_disconnect_peer_endpoint(p2p_test_client):
    """POST /api/v1/peers/{node_id}/disconnect should return disconnected status."""
    resp = p2p_test_client.post("/api/v1/peers/CCTV-B/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "disconnected"
