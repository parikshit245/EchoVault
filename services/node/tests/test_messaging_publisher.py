"""
Tests for RabbitMQ publisher — Part 6.

These tests verify:
  - MessageEnvelope is constructed correctly
  - event_type maps directly to the routing key
  - publish_event() is a no-op (no crash) when RabbitMQ is unavailable
  - Payload is correctly serialized to the envelope
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.messaging.schemas import (
    EvidenceCreatedPayload,
    IncidentCreatedPayload,
    MessageEnvelope,
    DevTestPayload,
)


# ── Envelope construction ─────────────────────────────────────────────────────

def test_envelope_defaults():
    """MessageEnvelope generates a UUID message_id and UTC timestamp."""
    env = MessageEnvelope(
        event_type="evidence.created",
        source_node_id="CCTV-A",
        payload={"evidence_id": "EV-001"},
    )
    assert env.message_id  # non-empty
    try:
        uuid.UUID(env.message_id)  # must be a valid UUID
    except ValueError:
        pytest.fail("message_id is not a valid UUID")
    assert env.timestamp.tzinfo is not None
    assert env.schema_version == "1.0"


def test_envelope_event_type_preserved():
    env = MessageEnvelope(
        event_type="incident.closed",
        source_node_id="SECURITY-A",
        payload={"incident_id": "INC-001"},
    )
    assert env.event_type == "incident.closed"


def test_envelope_incident_id_optional():
    env = MessageEnvelope(
        event_type="node.registered",
        source_node_id="NODE-01",
        payload={"node_id": "NODE-01"},
    )
    assert env.incident_id is None


def test_envelope_incident_id_set():
    env = MessageEnvelope(
        event_type="evidence.created",
        source_node_id="CCTV-A",
        payload={},
        incident_id="INC-001",
    )
    assert env.incident_id == "INC-001"


# ── Payload serialization ─────────────────────────────────────────────────────

def test_evidence_created_payload_serializes():
    payload = EvidenceCreatedPayload(
        evidence_id="EV-001",
        node_id="CCTV-A",
        event_type="PERSON_DETECTED",
        evidence_type="IMAGE",
        title="Person at entrance",
    )
    d = payload.model_dump()
    assert d["evidence_id"] == "EV-001"
    assert d["node_id"] == "CCTV-A"


def test_incident_payload_has_required_fields():
    payload = IncidentCreatedPayload(
        incident_id="INC-001",
        title="Intrusion detected",
        incident_type="INTRUSION",
        severity="HIGH",
        status="OPEN",
        created_by_node_id="SECURITY-A",
    )
    d = payload.model_dump()
    assert d["severity"] == "HIGH"
    assert d["created_by_node_id"] == "SECURITY-A"


# ── publish_event when RabbitMQ is unavailable ────────────────────────────────

@pytest.mark.asyncio
async def test_publish_event_no_crash_when_mq_unavailable():
    """publish_event() must not raise when the connection is unavailable."""
    from app.messaging import publisher as pub_module

    with patch.object(pub_module.messaging_connection, "is_healthy", return_value=False):
        # Should return silently, no exception
        await pub_module.publish_event(
            "test.message",
            DevTestPayload(message="hello"),
        )


@pytest.mark.asyncio
async def test_publish_event_routing_key_equals_event_type():
    """The routing key used for publishing must equal event_type."""
    from app.messaging import publisher as pub_module

    mock_exchange = AsyncMock()
    mock_channel = MagicMock()
    mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

    with (
        patch.object(pub_module.messaging_connection, "is_healthy", return_value=True),
        patch.object(pub_module.messaging_connection, "_channel", mock_channel),
    ):
        await pub_module.publish_event(
            "evidence.created",
            EvidenceCreatedPayload(
                evidence_id="EV-001",
                node_id="CCTV-A",
                event_type="PERSON_DETECTED",
                evidence_type="IMAGE",
                title="Test",
            ),
        )

        mock_exchange.publish.assert_called_once()
        call_kwargs = mock_exchange.publish.call_args
        assert call_kwargs.kwargs["routing_key"] == "evidence.created"


@pytest.mark.asyncio
async def test_publish_event_message_is_persistent():
    """Published messages must use PERSISTENT delivery mode."""
    import aio_pika
    from app.messaging import publisher as pub_module

    mock_exchange = AsyncMock()
    mock_channel = MagicMock()
    mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)

    with (
        patch.object(pub_module.messaging_connection, "is_healthy", return_value=True),
        patch.object(pub_module.messaging_connection, "_channel", mock_channel),
    ):
        await pub_module.publish_event(
            "node.registered",
            DevTestPayload(message="test"),
        )

        published_message = mock_exchange.publish.call_args.args[0]
        assert published_message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
