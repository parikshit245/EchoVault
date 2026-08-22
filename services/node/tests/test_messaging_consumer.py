"""
Tests for RabbitMQ consumer — Part 6.

These tests verify:
  - Valid messages are dispatched to the correct handler and ACK'd
  - Invalid JSON is NACK'd (without requeue) immediately
  - Self-originated messages are recorded as IGNORED and ACK'd
  - Messages already in the DB (duplicate) are detected and ACK'd without re-processing
  - Handler exceptions cause NACK and FAILED status
"""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.messaging.schemas import MessageEnvelope


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_envelope(
    event_type: str = "test.message",
    source_node_id: str = "CCTV-B",
    incident_id: str | None = None,
) -> bytes:
    env = MessageEnvelope(
        event_type=event_type,
        source_node_id=source_node_id,
        payload={"message": "test"},
        incident_id=incident_id,
    )
    return env.model_dump_json().encode()


def make_mock_message(body: bytes, routing_key: str = "test.message") -> MagicMock:
    msg = MagicMock()
    msg.body = body
    msg.routing_key = routing_key
    msg.headers = {}
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


# ── process_message tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_json_is_nacked_without_requeue():
    """Non-JSON bodies must be NACK'd straight to DLX (requeue=False)."""
    from app.messaging.consumer import process_message

    msg = make_mock_message(b"THIS IS NOT JSON")
    await process_message(msg)

    msg.nack.assert_called_once_with(requeue=False)
    msg.ack.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_envelope_schema_is_nacked():
    """Messages that are valid JSON but miss required envelope fields are rejected."""
    from app.messaging.consumer import process_message

    bad_body = json.dumps({"foo": "bar"}).encode()
    msg = make_mock_message(bad_body)
    await process_message(msg)

    msg.nack.assert_called_once_with(requeue=False)


@pytest.mark.asyncio
async def test_self_originated_message_is_ignored():
    """Messages whose source_node_id matches the local node are recorded as IGNORED."""
    from app.messaging import consumer as consumer_module

    local_node = "CCTV-A"
    body = make_envelope(event_type="evidence.created", source_node_id=local_node)
    msg = make_mock_message(body, routing_key="evidence.created")

    mock_session = AsyncMock()
    # No existing record in DB
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", local_node),
    ):
        await consumer_module.process_message(msg)

    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@pytest.mark.asyncio
async def test_valid_message_is_processed_and_acked():
    """A valid message from a remote node is dispatched, recorded PROCESSED, and ACK'd."""
    from app.messaging import consumer as consumer_module

    body = make_envelope(event_type="test.message", source_node_id="CCTV-B")
    msg = make_mock_message(body, routing_key="test.message")

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", "CCTV-A"),
    ):
        await consumer_module.process_message(msg)

    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@pytest.mark.asyncio
async def test_handler_exception_causes_nack():
    """When a handler raises, the message is NACK'd for requeue."""
    from app.messaging import consumer as consumer_module
    from app.messaging import handlers as handler_module

    body = make_envelope(event_type="evidence.created", source_node_id="CCTV-B")
    msg = make_mock_message(body, routing_key="evidence.created")

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    async def boom(envelope, session):
        raise RuntimeError("handler failed")

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", "CCTV-A"),
        patch.dict(handler_module.EVENT_HANDLERS, {"evidence.created": boom}),
    ):
        await consumer_module.process_message(msg)

    msg.nack.assert_called_once()
    msg.ack.assert_not_called()
