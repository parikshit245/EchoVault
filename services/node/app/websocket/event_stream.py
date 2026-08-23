"""
EventStreamService — RabbitMQ → WebSocket Bridge (Part 7).

This service is the single point of coupling between the messaging layer
(RabbitMQ consumer / publisher) and the WebSocket layer.

Design:
  EventStreamService.broadcast_event() is called:
    1. By the RabbitMQ consumer AFTER a successful ACK (remote events).
    2. By the publisher BEFORE publishing to RabbitMQ (self-originated events).

  This ensures ALL events — local and remote — flow to the live dashboard.

Critical ordering guarantee:
  RabbitMQ processing (persist ReceivedMessage + ACK) is INDEPENDENT of
  WebSocket delivery. broadcast_event() is always called as:

      asyncio.create_task(event_stream_service.broadcast_event(envelope))

  This means:
    - A WebSocket failure NEVER causes a NACK or RabbitMQ retry.
    - A disconnected browser NEVER blocks the consumer.
    - WebSocket is a best-effort, real-time delivery channel.
    - ReceivedMessage + RabbitMQ ACK remain the reliable source of truth.

  This behavior is intentional and documented per Part 7 requirements §8.

Latency measurement:
  broadcast_event() calculates latency_ms = now - envelope.timestamp.
  This is end-to-end delivery time (event creation → browser delivery)
  including RabbitMQ routing and Python processing overhead.
  It is NOT network-only latency. Reported in dev logs and WsEventMessage.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from ..messaging.schemas import MessageEnvelope
from .manager import ws_manager
from .schemas import WsEventMessage

logger = logging.getLogger("echovault.websocket.event_stream")


class EventStreamService:
    """
    Bridges the messaging layer to connected WebSocket clients.

    Responsibilities:
      - Receive a validated MessageEnvelope
      - Build a WsEventMessage (adds type discriminator + latency)
      - Server-side filter through WebSocketConnectionManager.broadcast()
      - Log delivery metrics
      - Handle failed connections (delegated to manager)
    """

    async def broadcast_event(self, envelope: MessageEnvelope) -> None:
        """
        Broadcast a validated event envelope to all eligible WebSocket clients.

        This method is fire-and-forget — callers should NOT await it directly
        in the RabbitMQ message processing pipeline.

        Use:
            asyncio.create_task(event_stream_service.broadcast_event(envelope))

        to ensure the consumer loop is not blocked by WebSocket I/O.
        """
        now = datetime.now(timezone.utc)
        latency_ms: float | None = None
        try:
            delta = now - envelope.timestamp.replace(tzinfo=timezone.utc)
            latency_ms = round(delta.total_seconds() * 1000, 2)
        except Exception:
            pass

        ws_event = WsEventMessage(
            message_id=envelope.message_id,
            event_type=envelope.event_type,
            source_node_id=envelope.source_node_id,
            timestamp=envelope.timestamp,
            incident_id=envelope.incident_id,
            payload=envelope.payload,
            latency_ms=latency_ms,
        )

        data = ws_event.model_dump(mode="json")

        if ws_manager.connection_count() == 0:
            return  # No clients — skip serialization overhead

        sent = await ws_manager.broadcast(
            data,
            event_type=envelope.event_type,
            source_node_id=envelope.source_node_id,
            incident_id=envelope.incident_id,
        )

        logger.debug(
            "WebSocket broadcast: event_type=%s source=%s sent_to=%d clients latency_ms=%s",
            envelope.event_type,
            envelope.source_node_id,
            sent,
            latency_ms,
        )


# Module-level singleton shared across the entire process
event_stream_service = EventStreamService()
