"""
PeerManager — Direct Peer-to-Peer Connection Manager (Part 8).

Coordinates all point-to-point WebSocket links between EchoVault nodes:
  - Inbound connection acceptance & handshake verification (/ws/peer).
  - Outbound connection establishment, handshake, & target identity verification.
  - Bounded exponential backoff reconnection for dropped peer links.
  - Direct message routing and Ping/Pong RTT calculation.
  - Disconnect cleanup and runtime status reporting.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import websockets

from ..config import settings
from .handlers import handle_p2p_message
from .peer import PeerConnection, PeerConnectionState, PeerInfo
from .protocol import (
    HandshakeAckPayload,
    HandshakePayload,
    P2PMessageEnvelope,
    PingPayload,
)

logger = logging.getLogger("echovault.p2p.manager")


class PeerIdentityMismatchError(Exception):
    """Raised when the connected peer's handshake node_id does not match expected target."""


class PeerNotConnectedError(Exception):
    """Raised when attempting to communicate with a disconnected peer."""


class PeerManager:
    """Singleton coordinator for node-to-node direct WebSocket links."""

    def __init__(self) -> None:
        self._peers: dict[str, PeerConnection] = {}
        self._ping_seq = 0
        self._lock = asyncio.Lock()

    def get_peer(self, node_id: str) -> PeerConnection | None:
        return self._peers.get(node_id)

    def get_peer_info(self, node_id: str) -> PeerInfo | None:
        conn = self._peers.get(node_id)
        return conn.to_info() if conn else None

    def get_peers(self) -> list[PeerInfo]:
        return [conn.to_info() for conn in self._peers.values()]

    def get_connected_count(self) -> int:
        return sum(
            1
            for conn in self._peers.values()
            if conn.state == PeerConnectionState.CONNECTED
        )

    # ── Inbound Handshake & Acceptance (/ws/peer) ─────────────────────────────

    async def handle_inbound_connection(self, websocket: Any) -> None:
        """
        Accept an incoming peer WebSocket connection, perform handshake,
        and manage message reception until disconnection.
        """
        peer_node_id: str | None = None
        peer_conn: PeerConnection | None = None

        try:
            # 1. Accept WebSocket
            await websocket.accept()

            # 2. Receive Handshake
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)

            if data.get("message_type") != "HANDSHAKE":
                logger.warning("Inbound connection rejected — first message not HANDSHAKE")
                await websocket.send_json(
                    HandshakeAckPayload(
                        node_id=settings.node_id,
                        node_name=settings.node_name,
                        node_type=settings.node_type.upper(),
                        status="REJECTED",
                        reason="First message must be HANDSHAKE",
                    ).model_dump(mode="json")
                )
                await websocket.close()
                return

            handshake = HandshakePayload.model_validate(data.get("payload", {}))
            peer_node_id = handshake.node_id

            # Reject self-connection
            if peer_node_id == settings.node_id:
                logger.warning("Rejected self-connection attempt from %s", peer_node_id)
                await websocket.send_json(
                    HandshakeAckPayload(
                        node_id=settings.node_id,
                        node_name=settings.node_name,
                        node_type=settings.node_type.upper(),
                        status="REJECTED",
                        reason="Cannot connect to self",
                    ).model_dump(mode="json")
                )
                await websocket.close()
                return

            # 3. Respond with HANDSHAKE_ACK
            ack_envelope = P2PMessageEnvelope(
                message_type="HANDSHAKE_ACK",
                source_node_id=settings.node_id,
                target_node_id=peer_node_id,
                payload=HandshakeAckPayload(
                    node_id=settings.node_id,
                    node_name=settings.node_name,
                    node_type=settings.node_type.upper(),
                    status="ACCEPTED",
                ).model_dump(mode="json"),
            )
            await websocket.send_json(ack_envelope.model_dump(mode="json"))

            # 4. Register active inbound peer
            async with self._lock:
                peer_conn = self._peers.get(peer_node_id)
                if peer_conn is None:
                    peer_conn = PeerConnection(
                        peer_node_id=peer_node_id,
                        node_name=handshake.node_name,
                        node_type=handshake.node_type,
                        host=handshake.p2p_host,
                        port=handshake.p2p_port,
                        is_outbound=False,
                    )
                    self._peers[peer_node_id] = peer_conn

                peer_conn.mark_connected(
                    websocket,
                    node_name=handshake.node_name,
                    node_type=handshake.node_type,
                )

            logger.info("Inbound P2P link established with peer %s", peer_node_id)

            # 5. Receiver loop for inbound connection
            while True:
                msg_text = await websocket.receive_text()
                try:
                    msg_dict = json.loads(msg_text)
                    envelope = P2PMessageEnvelope.model_validate(msg_dict)
                    await handle_p2p_message(envelope, peer_conn)
                except Exception as exc:
                    logger.warning(
                        "Error processing inbound P2P frame from %s: %s",
                        peer_node_id,
                        exc,
                    )

        except (Exception, asyncio.CancelledError) as exc:
            logger.info("Inbound peer connection %s ended: %s", peer_node_id, exc)
        finally:
            if peer_conn is not None and peer_conn.websocket == websocket:
                peer_conn.mark_disconnected()

    # ── Outbound Connection Establishment ─────────────────────────────────────

    async def connect_to_peer(
        self,
        target_node_id: str,
        host: str,
        port: int,
        *,
        auto_reconnect: bool = True,
    ) -> PeerInfo:
        """
        Initiate a direct point-to-point connection to target node.
        Performs handshake and target identity verification.
        """
        if target_node_id == settings.node_id:
            raise ValueError("Cannot connect to self as a peer")

        async with self._lock:
            conn = self._peers.get(target_node_id)
            if conn is None:
                conn = PeerConnection(
                    peer_node_id=target_node_id,
                    host=host,
                    port=port,
                    is_outbound=True,
                )
                self._peers[target_node_id] = conn
            else:
                conn.host = host
                conn.port = port
                conn.is_outbound = True

        conn.state = PeerConnectionState.CONNECTING
        ws_url = f"ws://{host}:{port}/ws/peer"
        logger.info("Connecting outbound P2P to %s at %s...", target_node_id, ws_url)

        try:
            # 1. Open direct WebSocket link
            ws = await websockets.connect(
                ws_url,
                close_timeout=5,
                ping_interval=20,
                ping_timeout=10,
            )

            conn.state = PeerConnectionState.HANDSHAKING

            # 2. Send HANDSHAKE
            handshake_payload = HandshakePayload(
                node_id=settings.node_id,
                node_name=settings.node_name,
                node_type=settings.node_type.upper(),
                p2p_host=settings.p2p_host,
                p2p_port=settings.p2p_port,
            )
            handshake_envelope = P2PMessageEnvelope(
                message_type="HANDSHAKE",
                source_node_id=settings.node_id,
                target_node_id=target_node_id,
                payload=handshake_payload.model_dump(),
            )
            await ws.send(json.dumps(handshake_envelope.model_dump(mode="json")))

            # 3. Wait for HANDSHAKE_ACK
            ack_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            ack_data = json.loads(ack_raw)

            payload_data = ack_data.get("payload", ack_data)
            ack_node_id = payload_data.get("node_id")
            ack_status = payload_data.get("status", "ACCEPTED")

            if ack_status != "ACCEPTED":
                await ws.close()
                conn.mark_disconnected()
                raise ConnectionError(f"Peer rejected handshake: {payload_data.get('reason')}")

            # 4. Target Identity Verification (Section 14 requirement)
            if ack_node_id != target_node_id:
                logger.error(
                    "Identity mismatch! Expected node %s but received %s from %s",
                    target_node_id,
                    ack_node_id,
                    ws_url,
                )
                await ws.close()
                conn.mark_disconnected()
                raise PeerIdentityMismatchError(
                    f"Identity mismatch: expected '{target_node_id}' but connected endpoint identified as '{ack_node_id}'"
                )

            # 5. Mark Connected
            conn.mark_connected(
                ws,
                node_name=payload_data.get("node_name"),
                node_type=payload_data.get("node_type"),
            )
            logger.info("Direct outbound P2P link ACTIVE with %s", target_node_id)

            # 6. Spawn outbound message listener
            conn.listener_task = asyncio.create_task(
                self._outbound_receiver_loop(conn, ws, auto_reconnect)
            )

            return conn.to_info()

        except Exception as exc:
            conn.mark_disconnected()
            logger.warning("Failed outbound P2P connection to %s (%s): %s", target_node_id, ws_url, exc)
            if auto_reconnect and not isinstance(exc, (PeerIdentityMismatchError, ValueError)):
                self._schedule_reconnect(conn)
            raise

    async def _outbound_receiver_loop(
        self,
        conn: PeerConnection,
        ws: Any,
        auto_reconnect: bool,
    ) -> None:
        """Background receiver loop for an outbound peer connection."""
        peer_id = conn.peer_node_id
        try:
            async for raw_msg in ws:
                try:
                    data = json.loads(raw_msg)
                    envelope = P2PMessageEnvelope.model_validate(data)
                    await handle_p2p_message(envelope, conn)
                except Exception as exc:
                    logger.warning("Error processing P2P frame from %s: %s", peer_id, exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.info("Outbound P2P socket with %s closed: %s", peer_id, exc)
        finally:
            if conn.websocket == ws:
                conn.mark_disconnected()
            if auto_reconnect and conn.state == PeerConnectionState.DISCONNECTED:
                self._schedule_reconnect(conn)

    # ── Bounded Exponential Backoff Reconnection ─────────────────────────────

    def _schedule_reconnect(self, conn: PeerConnection) -> None:
        """Schedule a background reconnection task with bounded exponential backoff."""
        if conn.reconnect_task and not conn.reconnect_task.done():
            return
        if not conn.host or not conn.port:
            return

        conn.reconnect_task = asyncio.create_task(self._reconnect_worker(conn))

    async def _reconnect_worker(self, conn: PeerConnection) -> None:
        """Worker loop for bounded exponential backoff reconnection."""
        peer_id = conn.peer_node_id
        max_backoff = settings.p2p_reconnect_max_backoff

        while conn.state == PeerConnectionState.DISCONNECTED:
            conn.reconnect_attempts += 1
            # Backoff: 1s, 2s, 4s, 8s, 16s... up to max_backoff
            delay = min(2 ** (conn.reconnect_attempts - 1), max_backoff)
            logger.info(
                "Scheduling P2P reconnect to %s in %ss (attempt #%s)...",
                peer_id,
                delay,
                conn.reconnect_attempts,
            )
            await asyncio.sleep(delay)

            try:
                await self.connect_to_peer(
                    peer_id,
                    conn.host,  # type: ignore[arg-type]
                    conn.port,  # type: ignore[arg-type]
                    auto_reconnect=False,
                )
                logger.info("P2P reconnection to %s SUCCEEDED", peer_id)
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("P2P reconnect attempt to %s failed: %s", peer_id, exc)

    # ── Direct Messaging & Ping/Pong ──────────────────────────────────────────

    async def send_direct_message(
        self, target_node_id: str, envelope: P2PMessageEnvelope
    ) -> bool:
        """Send a P2P message envelope directly to target peer."""
        conn = self._peers.get(target_node_id)
        if conn is None or conn.state != PeerConnectionState.CONNECTED:
            raise PeerNotConnectedError(f"Peer '{target_node_id}' is not connected")

        payload_dict = envelope.model_dump(mode="json")
        return await conn.send_json(payload_dict)

    async def ping_peer(self, target_node_id: str, timeout: float = 5.0) -> float:
        """Send a direct P2P PING and await PONG response to measure latency in ms."""
        conn = self._peers.get(target_node_id)
        if conn is None or conn.state != PeerConnectionState.CONNECTED:
            raise PeerNotConnectedError(f"Peer '{target_node_id}' is not connected")

        self._ping_seq += 1
        seq = self._ping_seq
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[float] = loop.create_future()
        conn.ping_futures[seq] = fut

        now_iso = datetime.now(timezone.utc).isoformat()
        ping_payload = PingPayload(timestamp=now_iso, seq=seq)
        envelope = P2PMessageEnvelope(
            message_type="PING",
            source_node_id=settings.node_id,
            target_node_id=target_node_id,
            payload=ping_payload.model_dump(),
        )

        sent = await conn.send_json(envelope.model_dump(mode="json"))
        if not sent:
            conn.ping_futures.pop(seq, None)
            raise ConnectionError(f"Failed to transmit PING to {target_node_id}")

        try:
            rtt_ms = await asyncio.wait_for(fut, timeout=timeout)
            return rtt_ms
        except asyncio.TimeoutError:
            conn.ping_futures.pop(seq, None)
            raise TimeoutError(f"PING to peer '{target_node_id}' timed out after {timeout}s")

    async def disconnect_peer(self, target_node_id: str) -> None:
        """Explicitly disconnect a peer and cancel any reconnection worker."""
        conn = self._peers.get(target_node_id)
        if conn:
            await conn.close()

    async def close_all(self) -> None:
        """Gracefully terminate all active peer links during service shutdown."""
        logger.info("Closing all P2P connections...")
        for conn in list(self._peers.values()):
            await conn.close()
        self._peers.clear()


# Global Singleton
peer_manager = PeerManager()
