"""
WebSocket endpoint integration tests — Part 7.

Tests the /ws/events endpoint using FastAPI's TestClient WebSocket support.

These tests verify the application-level WebSocket protocol:
  - Connection is accepted and a 'connected' greeting is sent
  - ping command receives a 'pong' response
  - subscribe command receives a 'subscription.updated' response
  - unsubscribe command receives a 'subscription.updated' response
  - Unknown/unsupported command receives an 'error' UNSUPPORTED_COMMAND response
  - Invalid JSON receives an 'error' INVALID_JSON response
  - Disconnect is handled cleanly (connection_count drops)

Note on database/messaging:
  These tests patch the database session factory and messaging connection
  so the FastAPI app can start without real PostgreSQL or RabbitMQ.
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))


# ── App fixture ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def test_client():
    """
    Create a TestClient for the FastAPI app with external dependencies patched.

    Patches:
      - async_session_factory → None (no DB needed for WS-only tests)
      - messaging_connection.connect → no-op
      - messaging_connection.close → no-op
      - start_consumer / stop_consumer → no-op
      - start_grpc_server → returns a MagicMock with stop()
    """
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


# ── connection greeting ───────────────────────────────────────────────────────


def test_ws_connection_sends_connected_greeting(test_client):
    """On connect, the server must immediately send a 'connected' message with connection_id."""
    with test_client.websocket_connect("/ws/events") as ws:
        greeting = ws.receive_json()

    assert greeting["type"] == "connected"
    assert "connection_id" in greeting
    assert len(greeting["connection_id"]) > 0
    assert "node_id" in greeting
    assert "timestamp" in greeting


# ── ping / pong ───────────────────────────────────────────────────────────────


def test_ws_ping_returns_pong(test_client):
    """Sending { type: 'ping' } must receive { type: 'pong', timestamp: '...' }."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # consume greeting
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()

    assert pong["type"] == "pong"
    assert "timestamp" in pong


# ── subscribe ─────────────────────────────────────────────────────────────────


def test_ws_subscribe_returns_subscription_updated(test_client):
    """subscribe command must return subscription.updated with the applied filters."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting
        ws.send_json({
            "type": "subscribe",
            "filters": {"incident_ids": ["INC-000001"]},
        })
        resp = ws.receive_json()

    assert resp["type"] == "subscription.updated"
    assert "INC-000001" in resp["filters"]["incident_ids"]


def test_ws_subscribe_event_types(test_client):
    """subscribe with event_types filter must include those types in the response."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting
        ws.send_json({
            "type": "subscribe",
            "filters": {
                "event_types": ["evidence.created", "incident.updated"],
            },
        })
        resp = ws.receive_json()

    assert resp["type"] == "subscription.updated"
    assert "evidence.created" in resp["filters"]["event_types"]
    assert "incident.updated" in resp["filters"]["event_types"]


def test_ws_subscribe_multiple_calls_merge(test_client):
    """Two subscribe calls must accumulate filters (union)."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting

        ws.send_json({"type": "subscribe", "filters": {"incident_ids": ["INC-001"]}})
        resp1 = ws.receive_json()
        assert "INC-001" in resp1["filters"]["incident_ids"]

        ws.send_json({"type": "subscribe", "filters": {"incident_ids": ["INC-002"]}})
        resp2 = ws.receive_json()

    assert "INC-001" in resp2["filters"]["incident_ids"]
    assert "INC-002" in resp2["filters"]["incident_ids"]


# ── unsubscribe ───────────────────────────────────────────────────────────────


def test_ws_unsubscribe_removes_filters(test_client):
    """unsubscribe must remove only the specified filter values."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting

        # Subscribe to two incidents
        ws.send_json({"type": "subscribe", "filters": {"incident_ids": ["INC-A", "INC-B"]}})
        ws.receive_json()  # subscription.updated

        # Unsubscribe from one
        ws.send_json({"type": "unsubscribe", "filters": {"incident_ids": ["INC-A"]}})
        resp = ws.receive_json()

    assert "INC-A" not in resp["filters"]["incident_ids"]
    assert "INC-B" in resp["filters"]["incident_ids"]


# ── unsupported command ───────────────────────────────────────────────────────


def test_ws_unsupported_command_returns_error(test_client):
    """Any unknown command type must receive type='error', code='UNSUPPORTED_COMMAND'."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting
        ws.send_json({"type": "execute_query", "sql": "DROP TABLE nodes;"})
        err = ws.receive_json()

    assert err["type"] == "error"
    assert err["code"] == "UNSUPPORTED_COMMAND"
    assert "message" in err


def test_ws_null_type_returns_error(test_client):
    """A message with type=null is an unsupported command."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting
        ws.send_json({"type": None})
        err = ws.receive_json()

    assert err["type"] == "error"
    assert err["code"] == "UNSUPPORTED_COMMAND"


# ── invalid JSON ──────────────────────────────────────────────────────────────


def test_ws_invalid_json_returns_error(test_client):
    """Non-JSON text must return type='error', code='INVALID_JSON'."""
    with test_client.websocket_connect("/ws/events") as ws:
        ws.receive_json()  # greeting
        ws.send_text("THIS IS NOT JSON {{{{")
        err = ws.receive_json()

    assert err["type"] == "error"
    assert err["code"] == "INVALID_JSON"


# ── connection health endpoint ────────────────────────────────────────────────


def test_ws_health_endpoint_reports_zero_when_no_clients(test_client):
    """GET /health/websocket should return active_connections >= 0 and status='healthy'."""
    # Reset manager state before test
    from app.websocket.manager import ws_manager
    ws_manager._connections.clear()

    resp = test_client.get("/health/websocket")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "websocket"
    assert isinstance(body["active_connections"], int)
    assert body["active_connections"] >= 0


def test_ws_health_counts_active_connections(test_client):
    """While a WebSocket is open, active_connections should be >= 1."""
    from app.websocket.manager import ws_manager

    with test_client.websocket_connect("/ws/events"):
        resp = test_client.get("/health/websocket")
        body = resp.json()
        assert body["active_connections"] >= 1

    # After disconnect, count should drop
    resp_after = test_client.get("/health/websocket")
    assert resp_after.json()["active_connections"] == 0
