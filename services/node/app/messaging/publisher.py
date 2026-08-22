"""
RabbitMQ publisher — Part 6.

Usage:
    from .messaging.publisher import publish_event
    from .messaging.schemas import EvidenceCreatedPayload

    await publish_event(
        "evidence.created",
        EvidenceCreatedPayload(evidence_id="EV-001", ...),
        incident_id="INC-001",
    )

Design:
- publish_event() is a fire-and-forget async call.
- If RabbitMQ is unavailable, a warning is logged and the call returns silently.
- The application does NOT crash or block if the broker is temporarily down.
- Messages are published as PERSISTENT (delivery_mode=2) to survive broker restarts.
- Raw file/multimedia bytes are NEVER published — only metadata references.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aio_pika

from ..config import settings
from .config import EXCHANGE_NAME
from .connection import messaging_connection
from .schemas import MessageEnvelope

logger = logging.getLogger("echovault.messaging.publisher")


async def publish_event(
    event_type: str,
    payload: Any,  # Pydantic payload model instance
    *,
    incident_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """
    Build a MessageEnvelope and publish it to the echovault.events exchange.

    Args:
        event_type:     Routing key, e.g. "evidence.created"
        payload:        A Pydantic payload model (EvidenceCreatedPayload, etc.)
        incident_id:    Optional incident this event relates to.
        correlation_id: Optional correlation ID for request tracing.
    """
    if not messaging_connection.is_healthy():
        logger.warning(
            "Skipping publish — RabbitMQ unavailable",
            extra={
                "event_type": event_type,
                "source_node_id": settings.node_id,
                "status": "skipped",
            },
        )
        return

    # Build the envelope
    if hasattr(payload, "model_dump"):
        payload_dict = payload.model_dump(mode="json")
    else:
        payload_dict = dict(payload)

    envelope = MessageEnvelope(
        event_type=event_type,
        source_node_id=settings.node_id,
        timestamp=datetime.now(timezone.utc),
        incident_id=incident_id,
        correlation_id=correlation_id,
        payload=payload_dict,
    )

    body = envelope.model_dump_json().encode()
    routing_key = event_type

    try:
        channel = messaging_connection.channel
        if channel is None:
            logger.warning("RabbitMQ channel not available, skipping publish")
            return

        exchange = await channel.get_exchange(EXCHANGE_NAME, ensure=False)
        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=envelope.message_id,
            headers={
                "source_node_id": settings.node_id,
                "event_type": event_type,
                "schema_version": envelope.schema_version,
            },
        )
        await exchange.publish(message, routing_key=routing_key)

        logger.info(
            json.dumps(
                {
                    "timestamp": envelope.timestamp.isoformat(),
                    "source_node_id": settings.node_id,
                    "event_type": event_type,
                    "message_id": envelope.message_id,
                    "routing_key": routing_key,
                    "incident_id": incident_id,
                    "status": "published",
                }
            )
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to publish event: %s — event_type=%s message_id=%s",
            exc,
            event_type,
            envelope.message_id,
        )
