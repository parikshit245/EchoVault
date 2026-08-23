"""
P2P Package — Peer-to-Peer Communication Subsystem (Part 8).

Dedicated direct node-to-node communication channel over /ws/peer.
Independent of browser /ws/events (stream-oriented) and RabbitMQ (pub/sub).
"""

from .protocol import (
    P2PMessageEnvelope,
    HandshakePayload,
    HandshakeAckPayload,
    PingPayload,
    PongPayload,
    PeerMessagePayload,
    EvidenceAnnouncementPayload,
    IncidentAnnouncementPayload,
)
from .peer import PeerConnection, PeerConnectionState, PeerInfo
from .manager import PeerManager, peer_manager, PeerIdentityMismatchError, PeerNotConnectedError

__all__ = [
    "P2PMessageEnvelope",
    "HandshakePayload",
    "HandshakeAckPayload",
    "PingPayload",
    "PongPayload",
    "PeerMessagePayload",
    "EvidenceAnnouncementPayload",
    "IncidentAnnouncementPayload",
    "PeerConnection",
    "PeerConnectionState",
    "PeerInfo",
    "PeerManager",
    "peer_manager",
    "PeerIdentityMismatchError",
    "PeerNotConnectedError",
]
