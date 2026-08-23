"""
Peer Connection Model — Runtime P2P state tracking (Part 8).

Maintains active connection status, latency, handshake metadata, and
message futures for direct peer links.
"""

import asyncio
import enum
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("echovault.p2p.peer")


class PeerConnectionState(str, enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    HANDSHAKING = "HANDSHAKING"
    CONNECTED = "CONNECTED"
    DISCONNECTING = "DISCONNECTING"


class PeerInfo(BaseModel):
    """Serializable runtime peer metadata for REST endpoints and dashboard."""

    peer_node_id: str
    node_name: str | None = None
    node_type: str | None = None
    host: str | None = None
    port: int | None = None
    state: PeerConnectionState
    connected_at: datetime | None = None
    last_seen_at: datetime | None = None
    rtt_ms: float | None = None
    reconnect_attempts: int = 0
    is_outbound: bool = False


class PeerConnection:
    """Runtime representation of a point-to-point WebSocket connection with a peer."""

    def __init__(
        self,
        peer_node_id: str,
        *,
        node_name: str | None = None,
        node_type: str | None = None,
        host: str | None = None,
        port: int | None = None,
        state: PeerConnectionState = PeerConnectionState.DISCONNECTED,
        is_outbound: bool = False,
    ) -> None:
        self.peer_node_id = peer_node_id
        self.node_name = node_name
        self.node_type = node_type
        self.host = host
        self.port = port
        self.state = state
        self.connected_at: datetime | None = None
        self.last_seen_at: datetime | None = None
        self.rtt_ms: float | None = None
        self.reconnect_attempts: int = 0
        self.is_outbound = is_outbound
        self.websocket: Any = None
        self.listener_task: asyncio.Task | None = None
        self.reconnect_task: asyncio.Task | None = None
        self.ping_futures: dict[int, asyncio.Future[float]] = {}
        self._lock = asyncio.Lock()

    def mark_connected(
        self,
        websocket: Any,
        node_name: str | None = None,
        node_type: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.websocket = websocket
        self.state = PeerConnectionState.CONNECTED
        self.connected_at = now
        self.last_seen_at = now
        self.reconnect_attempts = 0
        if node_name:
            self.node_name = node_name
        if node_type:
            self.node_type = node_type

    def mark_disconnected(self) -> None:
        self.state = PeerConnectionState.DISCONNECTED
        self.websocket = None
        # Cancel any pending ping futures
        for seq, fut in list(self.ping_futures.items()):
            if not fut.done():
                fut.cancel()
        self.ping_futures.clear()

    def touch(self) -> None:
        self.last_seen_at = datetime.now(timezone.utc)

    async def send_json(self, data: dict[str, Any]) -> bool:
        """Send a JSON payload over the active peer WebSocket."""
        if self.state != PeerConnectionState.CONNECTED or self.websocket is None:
            logger.warning("Cannot send to %s — peer is not CONNECTED", self.peer_node_id)
            return False

        async with self._lock:
            try:
                # Handle both FastAPI/Starlette WebSocket and websockets.client
                if hasattr(self.websocket, "send_json"):
                    await self.websocket.send_json(data)
                elif hasattr(self.websocket, "send"):
                    await self.websocket.send(json.dumps(data))
                else:
                    return False
                self.touch()
                return True
            except Exception as exc:
                logger.error("Error sending P2P message to %s: %s", self.peer_node_id, exc)
                return False

    async def close(self) -> None:
        """Close the WebSocket and cancel associated background tasks."""
        self.state = PeerConnectionState.DISCONNECTING
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()

        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception:
                pass

        self.mark_disconnected()

    def to_info(self) -> PeerInfo:
        return PeerInfo(
            peer_node_id=self.peer_node_id,
            node_name=self.node_name,
            node_type=self.node_type,
            host=self.host,
            port=self.port,
            state=self.state,
            connected_at=self.connected_at,
            last_seen_at=self.last_seen_at,
            rtt_ms=self.rtt_ms,
            reconnect_attempts=self.reconnect_attempts,
            is_outbound=self.is_outbound,
        )
