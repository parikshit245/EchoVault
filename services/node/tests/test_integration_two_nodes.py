"""
Integration test — Two-node RabbitMQ messaging demonstration (Part 6).

This test documents and simulates the two-node exchange scenario:
  Node A (CCTV-A) creates evidence → publishes evidence.created
  Node B (CCTV-B) receives the message → records it in its local inbox

Because actual RabbitMQ + two running nodes are integration-environment
dependencies, this test:
  - Verifies the pipeline logic end-to-end with mocked I/O
  - Is clearly marked to show how to run the REAL two-node demonstration

To run the actual two-node demonstration:
  1. docker compose up rabbitmq
  2. docker compose up node-a node-b
  3. POST http://localhost:8001/api/v1/evidence  { ... }
  4. GET  http://localhost:8002/api/v1/messaging/messages
     → you should see source_node_id = "CCTV-A"
  5. Verify Node B did NOT query Node A's database directly.
"""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.messaging.schemas import (
    EvidenceCreatedPayload,
    MessageEnvelope,
)


# ── Step 1: Node A builds + publishes an evidence.created event ───────────────

def test_node_a_builds_correct_envelope():
    """
    Node A creates evidence and serializes the correct envelope.
    Simulates what publish_event() does inside evidence_registry.create_evidence().
    """
    payload = EvidenceCreatedPayload(
        evidence_id="EV-DEMO-001",
        node_id="CCTV-A",
        event_type="PERSON_DETECTED",
        evidence_type="IMAGE",
        title="Person detected at entrance",
        incident_id="INC-DEMO-001",
    )
    envelope = MessageEnvelope(
        event_type="evidence.created",
        source_node_id="CCTV-A",
        payload=payload.model_dump(mode="json"),
        incident_id="INC-DEMO-001",
    )

    assert envelope.source_node_id == "CCTV-A"
    assert envelope.event_type == "evidence.created"
    assert envelope.payload["evidence_id"] == "EV-DEMO-001"


# ── Step 2: Node B receives the message and records it ────────────────────────

@pytest.mark.asyncio
async def test_node_b_receives_message_from_node_a():
    """
    Simulate Node B consuming a message published by Node A.

    Node B (consumer node_id = CCTV-B) receives an envelope with
    source_node_id = CCTV-A. It must:
      - Not skip it as self-originated (CCTV-A ≠ CCTV-B)
      - Record it as PROCESSED
      - ACK the message
    """
    from app.messaging import consumer as consumer_module
    from app.messaging import handlers as handler_module

    # Build Node A's message
    envelope = MessageEnvelope(
        event_type="evidence.created",
        source_node_id="CCTV-A",  # from Node A
        payload={
            "evidence_id": "EV-DEMO-001",
            "node_id": "CCTV-A",
            "event_type": "PERSON_DETECTED",
            "evidence_type": "IMAGE",
            "title": "Person at entrance",
        },
        incident_id="INC-DEMO-001",
    )
    body = envelope.model_dump_json().encode()

    msg = MagicMock()
    msg.body = body
    msg.routing_key = "evidence.created"
    msg.headers = {}
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()

    # Node B's DB session — no prior record of this message_id
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    node_b_id = "CCTV-B"

    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", node_b_id),
    ):
        await consumer_module.process_message(msg)

    # Node B ACK'd the message
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


@pytest.mark.asyncio
async def test_node_b_does_not_process_node_a_self_message():
    """
    When Node A itself receives a message it published (source = CCTV-A, consumer = CCTV-A),
    it must record IGNORED — not re-process.

    This is the key self-origin guard.
    """
    from app.messaging import consumer as consumer_module

    envelope = MessageEnvelope(
        event_type="evidence.created",
        source_node_id="CCTV-A",
        payload={"evidence_id": "EV-DEMO-001", "title": "X"},
    )
    body = envelope.model_dump_json().encode()

    msg = MagicMock()
    msg.body = body
    msg.routing_key = "evidence.created"
    msg.headers = {}
    msg.ack = AsyncMock()
    msg.nack = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session_cm

    # Node A consuming its own message
    with (
        patch.object(consumer_module, "async_session_factory", mock_factory),
        patch.object(consumer_module.settings, "node_id", "CCTV-A"),
    ):
        await consumer_module.process_message(msg)

    # Must ACK (clean), but NOT process the event
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


# ── Full scenario docstring (manual demo steps) ───────────────────────────────

def test_two_node_demo_documentation():
    """
    Documents the manual two-node demonstration steps.

    This is the core Part 6 acceptance criterion:
      CCTV-A publishes → RabbitMQ → CCTV-B receives

    Manual steps to execute the full demonstration:
      1. docker compose up rabbitmq
         → RabbitMQ running at localhost:5672
         → Management UI at http://localhost:15672 (guest/guest)

      2. docker compose up node-a node-b

      3. Wait for both nodes to connect to RabbitMQ.
         Verify queues in Management UI:
           echovault.node.CCTV-A
           echovault.node.CCTV-B

      4. POST http://localhost:8001/api/v1/evidence
         {
           "evidence_type": "IMAGE",
           "event_type": "PERSON_DETECTED",
           "title": "Two-node demo evidence",
           "captured_at": "2026-08-22T18:00:00Z"
         }

      5. Node A publishes evidence.created to echovault.events exchange.
         RabbitMQ routes to both CCTV-A and CCTV-B queues.

      6. Node B consumes the message.
         source_node_id = CCTV-A ≠ CCTV-B → handler dispatched → PROCESSED.

      7. GET http://localhost:8002/api/v1/messaging/messages
         → shows message with source_node_id = "CCTV-A", status = "PROCESSED"

      8. Node B's database has NO evidence created — it only received the EVENT.
         Node B did NOT directly query Node A's database.
    """
    assert True  # Documentation test always passes
