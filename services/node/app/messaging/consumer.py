"""
RabbitMQ consumer — Part 6.

Lifecycle:
  start_consumer() is called from the FastAPI lifespan context manager.
  It sets up exchanges, queues, and bindings, then starts consuming.

Message processing pipeline (updated Part 7):
  1. Receive raw AMQP message
  2. Parse MessageEnvelope (JSON)
  3. Idempotency check — look up message_id in received_messages table
     → duplicate: record IGNORED status, ACK, return
  4. Self-origin check — source_node_id == local node_id
     → record IGNORED status, ACK, return
  5. Record RECEIVED in received_messages
  6. Dispatch to handler from EVENT_HANDLERS dict
  7. On success → update status to PROCESSED, ACK
     → (Part 7) fire-and-forget WebSocket broadcast
  8. On failure → update status to FAILED, NACK (RabbitMQ requeues)
     → After RABBITMQ_RETRY_LIMIT failures the message is dead-lettered

WebSocket bridge ordering (Part 7 §8):
  The WebSocket broadcast happens AFTER the message is persisted AND ACK'd.
  It is launched as asyncio.create_task() — completely non-blocking.
  A WebSocket failure NEVER causes a NACK or RabbitMQ retry.
  WebSocket is a best-effort real-time channel, NOT the durable event store.

Dead-letter design:
  Node queues are declared with x-dead-letter-exchange pointing to
  echovault.dead-letter.  RabbitMQ tracks per-message delivery count
  via x-death headers.  When this consumer NACKs without requeue after
  retry_limit deliveries, the message flows to the dead-letter exchange.

Message ordering note:
  RabbitMQ delivery order is NOT a substitute for global logical ordering.
  MessageEnvelope.timestamp, message_id and source_node_id are preserved
  for future use by Part 7+ (Lamport/vector clocks, causal ordering).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import aio_pika
import aio_pika.abc

from ..config import settings
from ..database import async_session_factory
from ..models.received_message import ReceivedMessage, ReceivedMessageStatus
from .config import (
    DEAD_LETTER_EXCHANGE,
    EXCHANGE_NAME,
    QUEUE_BINDING_PATTERNS,
    node_queue_name,
    get_rabbitmq_url,
)
from .handlers import EVENT_HANDLERS, handle_unknown
from .schemas import MessageEnvelope

logger = logging.getLogger("echovault.messaging.consumer")

# Module-level reference to the consuming connection (separate from publisher)
_consumer_connection: aio_pika.abc.AbstractRobustConnection | None = None


async def _save_received(
    session,
    envelope: MessageEnvelope,
    routing_key: str,
    status: ReceivedMessageStatus,
    *,
    processed_at: datetime | None = None,
    error_message: str | None = None,
) -> None:
    """Persist a ReceivedMessage record (upsert by message_id)."""
    from sqlalchemy import select

    result = await session.execute(
        select(ReceivedMessage).where(ReceivedMessage.message_id == envelope.message_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Update existing record with final status
        existing.status = status
        existing.processed_at = processed_at
        existing.error_message = error_message
    else:
        record = ReceivedMessage(
            message_id=envelope.message_id,
            source_node_id=envelope.source_node_id,
            event_type=envelope.event_type,
            routing_key=routing_key,
            incident_id=envelope.incident_id,
            received_at=datetime.now(timezone.utc),
            processed_at=processed_at,
            status=status,
            error_message=error_message,
            payload_json=envelope.payload,
        )
        session.add(record)
    await session.commit()


async def _get_delivery_count(message: aio_pika.abc.AbstractIncomingMessage) -> int:
    """Extract x-death delivery count from message headers."""
    headers = message.headers or {}
    x_death = headers.get("x-death")
    if x_death and isinstance(x_death, list):
        try:
            return int(x_death[0].get("count", 1))
        except (IndexError, KeyError, TypeError, ValueError):
            pass
    return 1


async def process_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    """
    Core message processing pipeline.

    ACK on:  successful processing, duplicates, self-originated messages,
             or invalid messages (to avoid poison-pill loops).
    NACK on: processing failures — RabbitMQ requeues up to retry_limit.
    """
    started = time.perf_counter()
    routing_key = message.routing_key or ""

    # ── 1. Parse envelope ─────────────────────────────────────────────────────
    try:
        raw = json.loads(message.body)
        envelope = MessageEnvelope(**raw)
    except Exception as exc:
        logger.error("Invalid message envelope — routing to dead-letter: %s", exc)
        await message.nack(requeue=False)  # send straight to DLX
        return

    log_ctx = {
        "message_id": envelope.message_id,
        "event_type": envelope.event_type,
        "source_node_id": envelope.source_node_id,
        "consumer_node_id": settings.node_id,
        "routing_key": routing_key,
    }

    if async_session_factory is None:
        logger.warning("No DB session factory — cannot persist message %s", envelope.message_id)
        await message.ack()
        return

    async with async_session_factory() as session:
        # ── 2. Idempotency check ──────────────────────────────────────────────
        from sqlalchemy import select

        existing = await session.execute(
            select(ReceivedMessage).where(ReceivedMessage.message_id == envelope.message_id)
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("Duplicate message_id — ignoring: %s", envelope.message_id)
            await message.ack()
            return

        # ── 3. Self-origin check ──────────────────────────────────────────────
        # Messages published by this node arrive on its own queue due to
        # wildcard bindings.  We record them as IGNORED rather than
        # re-processing, which would cause duplicate evidence creation.
        if envelope.source_node_id == settings.node_id:
            logger.debug(
                "Self-originated message — recording as IGNORED: %s",
                envelope.message_id,
            )
            await _save_received(
                session, envelope, routing_key,
                ReceivedMessageStatus.IGNORED,
            )
            await message.ack()
            return

        # ── 4. Record RECEIVED ────────────────────────────────────────────────
        await _save_received(
            session, envelope, routing_key,
            ReceivedMessageStatus.RECEIVED,
        )

        # ── 5. Dispatch to handler ────────────────────────────────────────────
        handler = EVENT_HANDLERS.get(envelope.event_type, handle_unknown)
        try:
            await handler(envelope, session)
            processed_at = datetime.now(timezone.utc)
            await _save_received(
                session, envelope, routing_key,
                ReceivedMessageStatus.PROCESSED,
                processed_at=processed_at,
            )
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                json.dumps({
                    **log_ctx,
                    "status": "PROCESSED",
                    "processing_duration_ms": duration_ms,
                })
            )
            await message.ack()

            # ── Part 7: WebSocket bridge ──────────────────────────────────
            # Fire-and-forget broadcast to connected browser clients.
            # This MUST happen after ACK — WebSocket failure cannot cause NACK.
            # asyncio.create_task ensures the consumer loop is not blocked.
            try:
                from ..websocket.event_stream import event_stream_service
                asyncio.create_task(event_stream_service.broadcast_event(envelope))
            except Exception:  # noqa: BLE001
                pass  # WebSocket layer is non-critical to message processing

        except Exception as exc:  # noqa: BLE001
            delivery_count = await _get_delivery_count(message)
            error_str = str(exc)
            await _save_received(
                session, envelope, routing_key,
                ReceivedMessageStatus.FAILED,
                error_message=error_str,
            )
            logger.error(
                json.dumps({
                    **log_ctx,
                    "status": "FAILED",
                    "delivery_count": delivery_count,
                    "error": error_str,
                })
            )
            if delivery_count >= settings.rabbitmq_retry_limit:
                # Send to dead-letter exchange — no more requeue
                logger.warning(
                    "Retry limit reached (%d) — dead-lettering message %s",
                    settings.rabbitmq_retry_limit,
                    envelope.message_id,
                )
                await message.nack(requeue=False)
            else:
                await message.nack(requeue=True)


async def start_consumer() -> None:
    """
    Set up exchanges, queues, bindings and begin consuming.
    Called from the FastAPI lifespan startup.
    Non-fatal: if RabbitMQ is unavailable, logs a warning and returns.
    """
    global _consumer_connection

    url = get_rabbitmq_url()
    try:
        _consumer_connection = await aio_pika.connect_robust(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RabbitMQ consumer could not connect: %s", exc)
        return

    channel = await _consumer_connection.channel()
    await channel.set_qos(prefetch_count=10)

    # Declare dead-letter exchange first
    dlx = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE,
        type=aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    # Declare the main events exchange
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        type=aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    # Declare this node's queue with dead-letter and TTL configuration
    queue_name = node_queue_name(settings.node_id)
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
            "x-dead-letter-routing-key": f"dead.{settings.node_id}",
            "x-message-ttl": settings.rabbitmq_message_ttl_seconds * 1000,
        },
    )

    # Bind queue to all relevant routing patterns
    for pattern in QUEUE_BINDING_PATTERNS:
        await queue.bind(exchange, routing_key=pattern)

    logger.info(
        "Consumer ready: queue=%s exchange=%s bindings=%s",
        queue_name,
        EXCHANGE_NAME,
        QUEUE_BINDING_PATTERNS,
    )

    # Start consuming — messages are processed by process_message()
    await queue.consume(process_message)


async def stop_consumer() -> None:
    """Gracefully shut down the consumer connection."""
    global _consumer_connection
    if _consumer_connection and not _consumer_connection.is_closed:
        try:
            await _consumer_connection.close()
        except Exception:  # noqa: BLE001
            pass
    logger.info("RabbitMQ consumer connection closed")
