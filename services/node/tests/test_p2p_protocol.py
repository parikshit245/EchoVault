"""
P2P Protocol Tests — Part 8.

Tests:
  - P2PMessageEnvelope serialization and default fields
  - Handshake and HandshakeAck payload validation
  - Ping / Pong payload structure
  - Evidence and Incident announcement payloads
  - Direct message payload
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.peer_message import PeerMessageType
from app.p2p.protocol import (
    EvidenceAnnouncementPayload,
    HandshakeAckPayload,
    HandshakePayload,
    IncidentAnnouncementPayload,
    P2PMessageEnvelope,
    PeerMessagePayload,
    PingPayload,
    PongPayload,
)


def test_envelope_defaults():
    env = P2PMessageEnvelope(
        message_type="PING",
        source_node_id="CCTV-A",
        target_node_id="CCTV-B",
    )
    assert env.message_id.startswith("peer-")
    assert env.protocol_version == "1.0"
    assert env.source_node_id == "CCTV-A"
    assert env.target_node_id == "CCTV-B"
    assert isinstance(env.timestamp, datetime)
    assert env.payload == {}


def test_envelope_json_serialization():
    env = P2PMessageEnvelope(
        message_id="peer-test-123",
        message_type=PeerMessageType.PEER_MESSAGE.value,
        source_node_id="CCTV-A",
        target_node_id="CCTV-B",
        payload={"text": "hello direct peer"},
    )
    dumped = env.model_dump(mode="json")
    assert dumped["message_id"] == "peer-test-123"
    assert dumped["message_type"] == "PEER_MESSAGE"
    assert dumped["payload"]["text"] == "hello direct peer"

    # Verify round-trip parsing
    parsed = P2PMessageEnvelope.model_validate(dumped)
    assert parsed.message_id == "peer-test-123"
    assert parsed.payload["text"] == "hello direct peer"


def test_handshake_payload():
    payload = HandshakePayload(
        node_id="CCTV-A",
        node_name="CCTV Camera A",
        node_type="EVIDENCE",
        p2p_host="node-a",
        p2p_port=8001,
    )
    assert payload.node_id == "CCTV-A"
    assert payload.protocol_version == "1.0"
    assert payload.p2p_port == 8001


def test_handshake_ack_payload():
    payload = HandshakeAckPayload(
        node_id="CCTV-B",
        node_name="CCTV Camera B",
        node_type="EVIDENCE",
        status="ACCEPTED",
    )
    assert payload.status == "ACCEPTED"
    assert payload.node_id == "CCTV-B"


def test_ping_pong_payloads():
    now_str = datetime.now(timezone.utc).isoformat()
    ping = PingPayload(timestamp=now_str, seq=42)
    assert ping.seq == 42

    pong = PongPayload(seq=42, echo_timestamp=now_str)
    assert pong.seq == 42
    assert pong.echo_timestamp == now_str


def test_evidence_announcement_payload():
    payload = EvidenceAnnouncementPayload(
        evidence_id="EV-000001",
        node_id="CCTV-A",
        incident_id="INC-000001",
        event_type="PERSON_DETECTED",
        evidence_type="IMAGE",
        title="Unauthorized entry detected",
    )
    assert payload.evidence_id == "EV-000001"
    assert payload.title == "Unauthorized entry detected"


def test_incident_announcement_payload():
    payload = IncidentAnnouncementPayload(
        incident_id="INC-000001",
        title="Perimeter Breach",
        incident_type="SECURITY",
        severity="HIGH",
        status="OPEN",
        source_node_id="CCTV-A",
    )
    assert payload.incident_id == "INC-000001"
    assert payload.severity == "HIGH"
