"""
WebSocket Connection Manager — Part 7.

Maintains a runtime-only dict of active WebSocket connections.
No database persistence — these are transient browser sessions.

Design:
  Each connected client is identified by a unique connection_id (UUID4).
  Per-client metadata:
    - connection_id
    - websocket reference
    - connected_at
    - last_activity (updated on any inbound message)
    - filters (SubscriptionFilters — empty = receive all events)

Thread/concurrency safety:
  FastAPI WebSocket connections run inside asyncio on a single event loop.
  The dict operations are synchronous and atomic within the async context.
  No asyncio.Lock needed for the dict itself (single-threaded event loop).

Backpressure:
  Each client send uses asyncio.wait_for(..., timeout=WS_SEND_TIMEOUT_SECONDS).
  If a client is too slow or disconnected:
    - WebSocketDisconnect or TimeoutError → client is removed immediately
    - Other clients continue receiving events without interruption

A slow or dead browser CANNOT block the RabbitMQ consumer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from .schemas import SubscriptionFilters

logger = logging.getLogger("echovault.websocket.manager")

# Maximum seconds to wait for a single client send before declaring it dead
WS_SEND_TIMEOUT_SECONDS: float = 3.0


@dataclass
class ConnectionMeta:
    """Runtime metadata for a single WebSocket client."""

    connection_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filters: SubscriptionFilters = field(default_factory=SubscriptionFilters)

    def touch(self) -> None:
        self.last_activity = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "filters": {
                "event_types": self.filters.event_types,
                "source_node_ids": self.filters.source_node_ids,
                "incident_ids": self.filters.incident_ids,
            },
        }


class WebSocketConnectionManager:
    """
    Manages all active WebSocket client connections.

    Usage:
        ws_manager = WebSocketConnectionManager()   # module-level singleton

        # In the endpoint handler:
        conn_id = await ws_manager.connect(websocket)
        try:
            while True:
                ...
        finally:
            ws_manager.disconnect(conn_id)
    """

    def __init__(self) -> None:
        self._connections: dict[str, ConnectionMeta] = {}

    async def connect(self, websocket: WebSocket) -> str:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        meta = ConnectionMeta(connection_id=connection_id, websocket=websocket)
        self._connections[connection_id] = meta
        logger.info(
            "WebSocket client connected: connection_id=%s total=%d",
            connection_id,
            len(self._connections),
        )
        return connection_id

    def disconnect(self, connection_id: str) -> None:
        """Remove a connection (idempotent — safe to call multiple times)."""
        removed = self._connections.pop(connection_id, None)
        if removed:
            logger.info(
                "WebSocket client disconnected: connection_id=%s total=%d",
                connection_id,
                len(self._connections),
            )

    def update_filters(
        self,
        connection_id: str,
        new_filters: SubscriptionFilters,
        *,
        merge: bool = True,
    ) -> SubscriptionFilters:
        """
        Apply new filters to a connection.

        If merge=True (subscribe): extend existing filter lists.
        If merge=False (unsubscribe): remove items from existing filter lists.
        Returns the resulting filter state.
        """
        meta = self._connections.get(connection_id)
        if meta is None:
            return SubscriptionFilters()

        if merge:
            # subscribe: add new values to existing sets
            meta.filters.event_types = list(
                set(meta.filters.event_types) | set(new_filters.event_types)
            )
            meta.filters.source_node_ids = list(
                set(meta.filters.source_node_ids) | set(new_filters.source_node_ids)
            )
            meta.filters.incident_ids = list(
                set(meta.filters.incident_ids) | set(new_filters.incident_ids)
            )
        else:
            # unsubscribe: remove specified values
            meta.filters.event_types = [
                x for x in meta.filters.event_types if x not in new_filters.event_types
            ]
            meta.filters.source_node_ids = [
                x for x in meta.filters.source_node_ids if x not in new_filters.source_node_ids
            ]
            meta.filters.incident_ids = [
                x for x in meta.filters.incident_ids if x not in new_filters.incident_ids
            ]

        meta.touch()
        return meta.filters

    def touch(self, connection_id: str) -> None:
        """Update last_activity timestamp for a connection."""
        meta = self._connections.get(connection_id)
        if meta:
            meta.touch()

    async def send_json(self, connection_id: str, data: dict[str, Any]) -> bool:
        """
        Send a JSON payload to a specific client.

        Returns True on success, False if the client was removed.
        Uses asyncio.wait_for with WS_SEND_TIMEOUT_SECONDS backpressure guard.
        """
        meta = self._connections.get(connection_id)
        if meta is None:
            return False
        if meta.websocket.client_state != WebSocketState.CONNECTED:
            self.disconnect(connection_id)
            return False
        try:
            await asyncio.wait_for(
                meta.websocket.send_json(data),
                timeout=WS_SEND_TIMEOUT_SECONDS,
            )
            return True
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning(
                "WebSocket send failed for %s: %s — removing client",
                connection_id,
                exc,
            )
            self.disconnect(connection_id)
            return False

    async def broadcast(
        self,
        data: dict[str, Any],
        *,
        event_type: str,
        source_node_id: str,
        incident_id: str | None,
    ) -> int:
        """
        Broadcast data to all eligible clients (server-side filtered).

        Returns the count of clients that received the message.
        Dead/slow clients are removed during iteration without blocking others.
        """
        if not self._connections:
            return 0

        # Snapshot connection IDs to avoid dict mutation during iteration
        candidates = list(self._connections.keys())
        sent = 0
        tasks = []

        for cid in candidates:
            meta = self._connections.get(cid)
            if meta is None:
                continue
            if not meta.filters.matches(event_type, source_node_id, incident_id):
                continue
            tasks.append(self.send_json(cid, data))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent = sum(1 for r in results if r is True)

        return sent

    def connection_count(self) -> int:
        return len(self._connections)

    def get_connection_info(self) -> list[dict[str, Any]]:
        return [meta.to_dict() for meta in self._connections.values()]


# Module-level singleton — shared across the entire process
ws_manager = WebSocketConnectionManager()
