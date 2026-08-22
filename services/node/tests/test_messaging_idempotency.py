"""
Idempotency tests — Part 6.

Verifies that delivering the same message_id twice does NOT
cause the handler to execute a second time.

Expected behavior:
  First delivery:  msg-123 → PROCESS → PROCESSED
  Second delivery: msg-123 → already in received_messages → IGNORED (ACK, no handler)
"""
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.messaging.schemas import MessageEnvelope


def make_envelope_bytes(message_id: str, source_node_id: str = "CCTV-B") -> bytes:
    env = MessageEnvelope(
        message_id=message_id,
        event_type="test.message",
        source_node_id=source_node_id,
        payload={"message": "duplicate test"},
    )
    return env.model_dump_json().encode()


def make_mock_message(body: bytes) -> MagicMock:
    msg = MagicMock()
    msg.body = body
    msg.routing_key = "test.message"
    msg.headers = {}
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_duplicate_message_id_is_acked_without_handler():
    """
    When a message_id already exists in received_messages,
    the consumer must ACK it without calling any handler.
    """
    from app.messaging import consumer as consumer_module
    from app.messaging import handlers as handler_module

    shared_message_id = str(uuid.uuid4())
    body = make_envelope_bytes(shared_message_id)
    msg = make_mock_message(body)

    # Simulate existing record in DB (duplicate)
    existing_record = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_record

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    handler_called = False

    async def spy_handler(envelope, session):
        nonlocal handler_called
        handler_called = True

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", "CCTV-A"),
        patch.dict(handler_module.EVENT_HANDLERS, {"test.message": spy_handler}),
    ):
        await consumer_module.process_message(msg)

    assert not handler_called, "Handler must NOT be called for duplicate message_id"
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@pytest.mark.asyncio
async def test_unique_message_id_processes_handler():
    """
    A new (non-duplicate) message_id must trigger the handler.
    Confirms the idempotency check only fires on actual duplicates.
    """
    from app.messaging import consumer as consumer_module
    from app.messaging import handlers as handler_module

    unique_id = str(uuid.uuid4())
    body = make_envelope_bytes(unique_id, source_node_id="CCTV-B")
    msg = make_mock_message(body)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # no existing record

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    handler_called = False

    async def spy_handler(envelope, session):
        nonlocal handler_called
        handler_called = True

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", "CCTV-A"),
        patch.dict(handler_module.EVENT_HANDLERS, {"test.message": spy_handler}),
    ):
        await consumer_module.process_message(msg)

    assert handler_called, "Handler MUST be called for a new unique message_id"
    msg.ack.assert_called_once()
