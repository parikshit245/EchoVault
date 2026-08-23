"""
P2P Manager Tests — Part 8.

Tests:
  - Inbound handshake processing & rejection
  - Target identity verification & mismatch rejection
  - Connection state transitions
  - Direct message transmission
  - Direct PING/PONG and RTT calculation
  - Peer disconnect cleanup
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.p2p.manager import (
    PeerIdentityMismatchError,
    PeerManager,
    PeerNotConnectedError,
)
from app.p2p.peer import PeerConnectionState
from app.p2p.protocol import P2PMessageEnvelope


class FakeClientWebSocket:
    def __init__(self, ack_payload: dict, status: str = "ACCEPTED"):
        self.sent: list[str] = []
        self.ack_payload = ack_payload
        self.status = status
        self.closed = False
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, msg: str) -> None:
        self.sent.append(msg)

    async def recv(self) -> str:
        return json.dumps({
            "message_type": "HANDSHAKE_ACK",
            "payload": {**self.ack_payload, "status": self.status},
        })

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        return await self._queue.get()


@pytest.mark.asyncio
async def test_inbound_handshake_accepted():
    """Inbound connection sending valid HANDSHAKE must receive HANDSHAKE_ACK with ACCEPTED."""
    manager = PeerManager()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock(
        side_effect=[
            json.dumps({
                "message_type": "HANDSHAKE",
                "source_node_id": "CCTV-B",
                "target_node_id": "node-dev-001",
                "payload": {
                    "node_id": "CCTV-B",
                    "node_name": "CCTV Camera B",
                    "node_type": "EVIDENCE",
                    "p2p_host": "localhost",
                    "p2p_port": 8002,
                },
            }),
            asyncio.CancelledError(),  # Stop loop after handshake
        ]
    )
    ws.send_json = AsyncMock()

    with patch("app.p2p.manager.settings.node_id", "node-dev-001"):
        await manager.handle_inbound_connection(ws)

    ws.accept.assert_called_once()
    assert ws.send_json.call_count >= 1
    ack_call = ws.send_json.call_args_list[0][0][0]
    assert ack_call["message_type"] == "HANDSHAKE_ACK"
    assert ack_call["payload"]["status"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_inbound_self_connection_rejected():
    """Connecting to self must be rejected."""
    manager = PeerManager()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock(
        return_value=json.dumps({
            "message_type": "HANDSHAKE",
            "source_node_id": "node-dev-001",
            "target_node_id": "node-dev-001",
            "payload": {
                "node_id": "node-dev-001",
                "node_name": "Self",
                "node_type": "COORDINATOR",
            },
        })
    )
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    with patch("app.p2p.manager.settings.node_id", "node-dev-001"):
        await manager.handle_inbound_connection(ws)

    assert ws.send_json.call_count == 1
    ack_call = ws.send_json.call_args[0][0]
    assert ack_call["status"] == "REJECTED"
    ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_outbound_identity_mismatch_rejected():
    """
    If Node A attempts to connect to CCTV-B, but the remote endpoint identifies
    as CCTV-C, Node A must reject the connection and raise PeerIdentityMismatchError.
    """
    manager = PeerManager()
    fake_ws = FakeClientWebSocket({
        "node_id": "CCTV-C",  # Mismatch!
        "node_name": "CCTV Camera C",
        "node_type": "EVIDENCE",
    })

    with patch("websockets.connect", AsyncMock(return_value=fake_ws)):
        with pytest.raises(PeerIdentityMismatchError) as exc_info:
            await manager.connect_to_peer("CCTV-B", "node-b", 8002, auto_reconnect=False)

    assert "expected 'CCTV-B' but connected endpoint identified as 'CCTV-C'" in str(exc_info.value)
    assert fake_ws.closed is True

    peer = manager.get_peer("CCTV-B")
    assert peer is not None
    assert peer.state == PeerConnectionState.DISCONNECTED


@pytest.mark.asyncio
async def test_send_direct_message_when_connected():
    """Sending direct message over connected peer transmits JSON directly."""
    manager = PeerManager()
    fake_ws = FakeClientWebSocket({
        "node_id": "CCTV-B",
        "node_name": "CCTV Camera B",
        "node_type": "EVIDENCE",
    })

    with patch("websockets.connect", AsyncMock(return_value=fake_ws)):
        await manager.connect_to_peer("CCTV-B", "node-b", 8002, auto_reconnect=False)

    envelope = P2PMessageEnvelope(
        message_type="PEER_MESSAGE",
        source_node_id="node-dev-001",
        target_node_id="CCTV-B",
        payload={"text": "hello direct node"},
    )
    result = await manager.send_direct_message("CCTV-B", envelope)
    assert result is True
    assert len(fake_ws.sent) >= 2  # Handshake + Direct Message
    last_sent = json.loads(fake_ws.sent[-1])
    assert last_sent["message_type"] == "PEER_MESSAGE"
    assert last_sent["payload"]["text"] == "hello direct node"

    await manager.disconnect_peer("CCTV-B")


@pytest.mark.asyncio
async def test_send_message_when_disconnected_raises():
    """Attempting to send a message to a disconnected peer raises PeerNotConnectedError."""
    manager = PeerManager()
    envelope = P2PMessageEnvelope(
        message_type="PEER_MESSAGE",
        source_node_id="A",
        target_node_id="NON_EXISTENT",
        payload={},
    )
    with pytest.raises(PeerNotConnectedError):
        await manager.send_direct_message("NON_EXISTENT", envelope)


@pytest.mark.asyncio
async def test_ping_pong_rtt():
    """Ping peer sends PING and resolves RTT when PONG arrives."""
    from app.p2p.handlers import handle_p2p_message

    manager = PeerManager()
    fake_ws = FakeClientWebSocket({
        "node_id": "CCTV-B",
        "node_name": "CCTV Camera B",
        "node_type": "EVIDENCE",
    })

    with patch("websockets.connect", AsyncMock(return_value=fake_ws)):
        await manager.connect_to_peer("CCTV-B", "node-b", 8002, auto_reconnect=False)

    peer_conn = manager.get_peer("CCTV-B")
    assert peer_conn is not None

    async def simulate_remote_pong():
        await asyncio.sleep(0.02)
        # Find registered future seq
        seq = next(iter(peer_conn.ping_futures.keys()))
        pong_envelope = P2PMessageEnvelope(
            message_type="PONG",
            source_node_id="CCTV-B",
            target_node_id="node-dev-001",
            payload={"seq": seq, "echo_timestamp": "2026-08-23T12:00:00Z"},
        )
        await handle_p2p_message(pong_envelope, peer_conn)

    pong_task = asyncio.create_task(simulate_remote_pong())

    with patch("app.p2p.handlers.async_session_factory", None):
        rtt_ms = await manager.ping_peer("CCTV-B", timeout=2.0)

    await pong_task
    assert isinstance(rtt_ms, float)
    assert rtt_ms >= 0.0

    await manager.disconnect_peer("CCTV-B")
