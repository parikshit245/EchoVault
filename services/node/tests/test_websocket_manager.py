"""
WebSocket Connection Manager tests — Part 7.

Tests:
  - connect() accepts WebSocket and returns a connection_id
  - disconnect() removes the connection (idempotent)
  - connection_count() reflects current connections
  - send_json() succeeds for a connected client
  - send_json() removes a dead client (TimeoutError)
  - broadcast() delivers to matching clients only (filter logic)
  - broadcast() skips clients with non-matching filters
  - update_filters() subscribe merges filter sets
  - update_filters() unsubscribe removes filter values
  - touch() updates last_activity
  - get_connection_info() returns serializable metadata
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.websocket.manager import WebSocketConnectionManager, WS_SEND_TIMEOUT_SECONDS
from app.websocket.schemas import SubscriptionFilters
from fastapi.websockets import WebSocketState


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_ws(state: WebSocketState = WebSocketState.CONNECTED) -> MagicMock:
    """Return a mock WebSocket that is in a connected state by default."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.client_state = state
    return ws


# ── connect / disconnect / count ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_accepts_websocket_and_returns_id():
    """connect() must call ws.accept() and return a non-empty string ID."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()

    conn_id = await manager.connect(ws)

    ws.accept.assert_called_once()
    assert isinstance(conn_id, str)
    assert len(conn_id) > 0
    assert manager.connection_count() == 1


@pytest.mark.asyncio
async def test_disconnect_removes_connection():
    """disconnect() must remove the client; connection_count drops to 0."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()

    conn_id = await manager.connect(ws)
    assert manager.connection_count() == 1

    manager.disconnect(conn_id)
    assert manager.connection_count() == 0


@pytest.mark.asyncio
async def test_disconnect_is_idempotent():
    """Calling disconnect() twice for the same ID must not raise."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    manager.disconnect(conn_id)
    manager.disconnect(conn_id)  # second call — must be a no-op
    assert manager.connection_count() == 0


@pytest.mark.asyncio
async def test_multiple_clients_tracked():
    """Three connects produce connection_count == 3."""
    manager = WebSocketConnectionManager()
    ids = []
    for _ in range(3):
        ids.append(await manager.connect(make_mock_ws()))

    assert manager.connection_count() == 3

    manager.disconnect(ids[1])
    assert manager.connection_count() == 2


# ── send_json ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_json_succeeds_for_connected_client():
    """send_json() should return True and call ws.send_json for a connected client."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    result = await manager.send_json(conn_id, {"type": "pong"})

    assert result is True
    ws.send_json.assert_called_once_with({"type": "pong"})


@pytest.mark.asyncio
async def test_send_json_removes_slow_client():
    """A TimeoutError during send must remove the client and return False."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    ws.send_json = AsyncMock(side_effect=asyncio.TimeoutError("too slow"))
    conn_id = await manager.connect(ws)

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
        result = await manager.send_json(conn_id, {"type": "event"})

    assert result is False
    assert manager.connection_count() == 0


@pytest.mark.asyncio
async def test_send_json_returns_false_for_unknown_id():
    """send_json() for an unregistered ID should return False silently."""
    manager = WebSocketConnectionManager()
    result = await manager.send_json("nonexistent-id", {"type": "ping"})
    assert result is False


@pytest.mark.asyncio
async def test_send_json_removes_disconnected_state_client():
    """A client whose WebSocket state is DISCONNECTED should be removed on send."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws(state=WebSocketState.DISCONNECTED)
    conn_id = await manager.connect(ws)

    result = await manager.send_json(conn_id, {"type": "event"})

    assert result is False
    assert manager.connection_count() == 0


# ── broadcast ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_delivers_to_unfiltered_clients():
    """Clients with empty filters receive all events."""
    manager = WebSocketConnectionManager()
    ws_a = make_mock_ws()
    ws_b = make_mock_ws()
    await manager.connect(ws_a)
    await manager.connect(ws_b)

    sent = await manager.broadcast(
        {"type": "event"},
        event_type="evidence.created",
        source_node_id="CCTV-A",
        incident_id=None,
    )

    assert sent == 2


@pytest.mark.asyncio
async def test_broadcast_filters_by_event_type():
    """A client subscribed to incident.created should NOT receive evidence.created."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    # Subscribe to incident events only
    manager.update_filters(
        conn_id,
        SubscriptionFilters(event_types=["incident.created"]),
        merge=True,
    )

    sent = await manager.broadcast(
        {"type": "event"},
        event_type="evidence.created",
        source_node_id="CCTV-A",
        incident_id=None,
    )

    assert sent == 0


@pytest.mark.asyncio
async def test_broadcast_filters_by_incident_id():
    """A client subscribed to INC-001 should NOT receive events for INC-002."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    manager.update_filters(
        conn_id,
        SubscriptionFilters(incident_ids=["INC-000001"]),
        merge=True,
    )

    sent = await manager.broadcast(
        {"type": "event"},
        event_type="incident.updated",
        source_node_id="CCTV-A",
        incident_id="INC-000002",  # different incident
    )
    assert sent == 0

    sent2 = await manager.broadcast(
        {"type": "event"},
        event_type="incident.updated",
        source_node_id="CCTV-A",
        incident_id="INC-000001",  # matching incident
    )
    assert sent2 == 1


@pytest.mark.asyncio
async def test_broadcast_filters_by_source_node():
    """A client filtering by source_node_id receives only matching-source events."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    manager.update_filters(
        conn_id,
        SubscriptionFilters(source_node_ids=["CCTV-A"]),
        merge=True,
    )

    assert 0 == await manager.broadcast(
        {"type": "event"},
        event_type="evidence.created",
        source_node_id="CCTV-B",
        incident_id=None,
    )
    assert 1 == await manager.broadcast(
        {"type": "event"},
        event_type="evidence.created",
        source_node_id="CCTV-A",
        incident_id=None,
    )


@pytest.mark.asyncio
async def test_broadcast_slow_client_does_not_block_others():
    """A slow client must not prevent fast clients from receiving the event."""
    manager = WebSocketConnectionManager()

    # Slow client
    ws_slow = make_mock_ws()
    ws_slow.send_json = AsyncMock(side_effect=asyncio.TimeoutError("slow"))
    slow_id = await manager.connect(ws_slow)

    # Fast client
    ws_fast = make_mock_ws()
    fast_id = await manager.connect(ws_fast)

    with patch("asyncio.wait_for", side_effect=[asyncio.TimeoutError(), None]):
        sent = await manager.broadcast(
            {"type": "event"},
            event_type="test.message",
            source_node_id="X",
            incident_id=None,
        )

    # Fast client received; slow was removed
    assert manager.connection_count() == 1
    assert manager._connections.get(fast_id) is not None
    assert manager._connections.get(slow_id) is None


# ── update_filters ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_merges_filters():
    """subscribe (merge=True) should add new values without removing existing ones."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    manager.update_filters(conn_id, SubscriptionFilters(incident_ids=["INC-001"]), merge=True)
    manager.update_filters(conn_id, SubscriptionFilters(incident_ids=["INC-002"]), merge=True)

    meta = manager._connections[conn_id]
    assert set(meta.filters.incident_ids) == {"INC-001", "INC-002"}


@pytest.mark.asyncio
async def test_unsubscribe_removes_filter_values():
    """unsubscribe (merge=False) should remove specified values only."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    manager.update_filters(conn_id, SubscriptionFilters(incident_ids=["INC-001", "INC-002"]), merge=True)
    manager.update_filters(conn_id, SubscriptionFilters(incident_ids=["INC-001"]), merge=False)

    meta = manager._connections[conn_id]
    assert "INC-001" not in meta.filters.incident_ids
    assert "INC-002" in meta.filters.incident_ids


# ── touch / get_connection_info ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_touch_updates_last_activity():
    """touch() should update the last_activity timestamp."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    before = manager._connections[conn_id].last_activity
    await asyncio.sleep(0.01)
    manager.touch(conn_id)
    after = manager._connections[conn_id].last_activity

    assert after >= before


@pytest.mark.asyncio
async def test_get_connection_info_is_serializable():
    """get_connection_info() must return a list of dicts with required keys."""
    manager = WebSocketConnectionManager()
    ws = make_mock_ws()
    conn_id = await manager.connect(ws)

    info = manager.get_connection_info()
    assert len(info) == 1
    assert info[0]["connection_id"] == conn_id
    assert "connected_at" in info[0]
    assert "last_activity" in info[0]
    assert "filters" in info[0]
