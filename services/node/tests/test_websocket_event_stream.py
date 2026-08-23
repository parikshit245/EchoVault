"""
EventStreamService tests — Part 7.

Tests:
  - broadcast_event() builds correct WsEventMessage from a MessageEnvelope
  - latency_ms is computed and included in the broadcast payload
  - broadcast_event() is a no-op when zero clients are connected
  - broadcast_event() calls ws_manager.broadcast with correct filter args
  - broadcast_event() handles a malformed timestamp gracefully (latency_ms=None)
  - Envelope with incident_id passes incident_id to broadcast
"""
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.messaging.schemas import MessageEnvelope
from app.websocket.event_stream import EventStreamService
from app.websocket.manager import WebSocketConnectionManager


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_envelope(
    event_type: str = "evidence.created",
    source_node_id: str = "CCTV-A",
    incident_id: str | None = "INC-000001",
    timestamp: datetime | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        event_type=event_type,
        source_node_id=source_node_id,
        incident_id=incident_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        payload={"evidence_id": "EV-000001", "title": "Person detected"},
    )


# ── broadcast_event: no clients ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_event_no_op_when_no_clients():
    """broadcast_event() should skip broadcast entirely when connection_count == 0."""
    manager = WebSocketConnectionManager()
    service = EventStreamService()

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "broadcast", new_callable=AsyncMock) as mock_broadcast:
            await service.broadcast_event(make_envelope())

    mock_broadcast.assert_not_called()


# ── broadcast_event: message structure ───────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_event_passes_correct_args():
    """broadcast_event() must call ws_manager.broadcast with the right filter kwargs."""
    manager = WebSocketConnectionManager()
    service = EventStreamService()
    envelope = make_envelope(
        event_type="incident.updated",
        source_node_id="SECURITY-B",
        incident_id="INC-000002",
    )

    captured_kwargs: dict = {}

    async def mock_broadcast(data, *, event_type, source_node_id, incident_id):
        captured_kwargs["event_type"] = event_type
        captured_kwargs["source_node_id"] = source_node_id
        captured_kwargs["incident_id"] = incident_id
        return 1

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "connection_count", return_value=1):
            with patch.object(manager, "broadcast", side_effect=mock_broadcast):
                await service.broadcast_event(envelope)

    assert captured_kwargs["event_type"] == "incident.updated"
    assert captured_kwargs["source_node_id"] == "SECURITY-B"
    assert captured_kwargs["incident_id"] == "INC-000002"


@pytest.mark.asyncio
async def test_broadcast_event_payload_contains_type_discriminator():
    """The data dict passed to broadcast must have type='event'."""
    manager = WebSocketConnectionManager()
    service = EventStreamService()
    envelope = make_envelope()

    captured_data: dict = {}

    async def mock_broadcast(data, **kwargs):
        captured_data.update(data)
        return 1

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "connection_count", return_value=1):
            with patch.object(manager, "broadcast", side_effect=mock_broadcast):
                await service.broadcast_event(envelope)

    assert captured_data.get("type") == "event"
    assert captured_data.get("event_type") == "evidence.created"
    assert captured_data.get("source_node_id") == "CCTV-A"
    assert captured_data.get("incident_id") == "INC-000001"
    assert "payload" in captured_data
    assert "message_id" in captured_data


# ── broadcast_event: latency ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_event_computes_latency_ms():
    """latency_ms should be a positive float for a recent event."""
    manager = WebSocketConnectionManager()
    service = EventStreamService()

    past = datetime.now(timezone.utc) - timedelta(milliseconds=200)
    envelope = make_envelope(timestamp=past)

    captured_data: dict = {}

    async def mock_broadcast(data, **kwargs):
        captured_data.update(data)
        return 1

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "connection_count", return_value=1):
            with patch.object(manager, "broadcast", side_effect=mock_broadcast):
                await service.broadcast_event(envelope)

    latency = captured_data.get("latency_ms")
    assert latency is not None
    assert latency >= 0


@pytest.mark.asyncio
async def test_broadcast_event_handles_latency_error_gracefully():
    """If latency_ms computation raises (e.g. datetime subtraction fails), the
    broadcast should still succeed with latency_ms=None — not raise."""
    from datetime import timezone
    import app.websocket.event_stream as es_module

    manager = WebSocketConnectionManager()
    service = EventStreamService()
    envelope = make_envelope()

    captured_data: dict = {}

    async def mock_broadcast(data, **kwargs):
        captured_data.update(data)
        return 1

    # Make datetime.now() return a non-datetime to trigger subtraction error
    class BadNow:
        def __sub__(self, other):
            raise TypeError("intentional subtraction error")

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "connection_count", return_value=1):
            with patch.object(manager, "broadcast", side_effect=mock_broadcast):
                with patch(f"{es_module.__name__}.datetime") as mock_dt:
                    mock_dt.now.return_value = BadNow()
                    await service.broadcast_event(envelope)

    # broadcast must have been called — the latency error was swallowed
    assert captured_data.get("type") == "event"
    assert captured_data.get("latency_ms") is None



# ── broadcast_event: None incident_id ────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_event_with_no_incident_id():
    """Events without incident_id should still broadcast successfully."""
    manager = WebSocketConnectionManager()
    service = EventStreamService()
    envelope = make_envelope(incident_id=None)

    captured_kwargs: dict = {}

    async def mock_broadcast(data, *, event_type, source_node_id, incident_id):
        captured_kwargs["incident_id"] = incident_id
        return 1

    with patch("app.websocket.event_stream.ws_manager", manager):
        with patch.object(manager, "connection_count", return_value=1):
            with patch.object(manager, "broadcast", side_effect=mock_broadcast):
                await service.broadcast_event(envelope)

    assert captured_kwargs["incident_id"] is None


# ── EventStreamService singleton ─────────────────────────────────────────────


def test_event_stream_service_is_importable():
    """The module-level singleton should be importable."""
    from app.websocket.event_stream import event_stream_service, EventStreamService
    assert isinstance(event_stream_service, EventStreamService)
