"""
P2P Protocol — Envelopes and Payload Schemas (Part 8).

All direct node-to-node communication uses structured P2PMessageEnvelope instances.
Pydantic ensures validation and serialization consistency across nodes.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..models.peer_message import PeerMessageType


class P2PMessageEnvelope(BaseModel):
    """Standard message envelope for all direct peer-to-peer transmissions."""

    message_id: str = Field(
        default_factory=lambda: f"peer-{uuid.uuid4().hex[:12]}",
        description="Unique identifier for idempotency tracking",
    )
    message_type: str = Field(
        ...,
        description="Message type identifier (e.g. HANDSHAKE, PING, PEER_MESSAGE, etc.)",
    )
    source_node_id: str = Field(
        ...,
        description="Originating node ID (e.g. CCTV-A)",
    )
    target_node_id: str = Field(
        ...,
        description="Destination node ID (e.g. CCTV-B)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp",
    )
    protocol_version: str = Field(
        default="1.0",
        description="P2P Protocol specification version",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured message payload",
    )


class HandshakePayload(BaseModel):
    """Initial handshake sent by initiating peer upon WebSocket connection."""

    node_id: str
    node_name: str
    node_type: str
    protocol_version: str = "1.0"
    p2p_host: str | None = None
    p2p_port: int | None = None


class HandshakeAckPayload(BaseModel):
    """Response to handshake confirming or rejecting the peer connection."""

    node_id: str
    node_name: str
    node_type: str
    protocol_version: str = "1.0"
    status: str = "ACCEPTED"  # ACCEPTED or REJECTED
    reason: str | None = None


class PingPayload(BaseModel):
    """Liveness probe sent to measure direct network latency."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    seq: int = 1


class PongPayload(BaseModel):
    """Response to Ping returning original timestamp for round-trip calculation."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    seq: int = 1
    echo_timestamp: str


class PeerMessagePayload(BaseModel):
    """Direct arbitrary peer text message for testing and dev communication."""

    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceAnnouncementPayload(BaseModel):
    """Metadata-only announcement of locally captured evidence to a peer."""

    evidence_id: str
    node_id: str
    incident_id: str | None = None
    event_type: str
    evidence_type: str
    title: str
    captured_at: str | None = None


class IncidentAnnouncementPayload(BaseModel):
    """Metadata-only announcement of incident state/context to a peer."""

    incident_id: str
    title: str
    incident_type: str
    severity: str
    status: str
    source_node_id: str
    started_at: str | None = None
