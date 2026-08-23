"""
P2P Message Handlers — Idempotent dispatch & persistence (Part 8).

Handles incoming peer messages, enforces database-backed idempotency,
manages Ping/Pong RTT calculation, and audits peer announcements.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import async_session_factory
from ..models.peer_message import PeerMessage, PeerMessageStatus, PeerMessageType
from .peer import PeerConnection
from .protocol import P2PMessageEnvelope, PongPayload

logger = logging.getLogger("echovault.p2p.handlers")


async def handle_p2p_message(
    envelope: P2PMessageEnvelope,
    peer_conn: PeerConnection,
) -> None:
    """
    Main dispatch entry point for an incoming P2P message.

    Enforces idempotency:
    1. Checks peer_messages table for envelope.message_id.
    2. If duplicate, marks/logs as IGNORED and returns without re-processing.
    3. If new, creates a RECEIVED record, executes the handler, then marks PROCESSED.
    """
    peer_conn.touch()
    now = datetime.now(timezone.utc)

    # 1. Database idempotency check
    if async_session_factory is not None:
        async with async_session_factory() as session:
            try:
                # Check for existing message_id
                existing_stmt = select(PeerMessage).where(
                    PeerMessage.message_id == envelope.message_id
                )
                res = await session.execute(existing_stmt)
                existing = res.scalar_one_or_none()

                if existing is not None:
                    logger.warning(
                        "Duplicate P2P message ignored: message_id=%s from=%s type=%s",
                        envelope.message_id,
                        envelope.source_node_id,
                        envelope.message_type,
                    )
                    return

                # Record new message as RECEIVED
                msg_record = PeerMessage(
                    message_id=envelope.message_id,
                    source_node_id=envelope.source_node_id,
                    target_node_id=envelope.target_node_id,
                    message_type=envelope.message_type,
                    received_at=now,
                    status=PeerMessageStatus.RECEIVED,
                    payload=envelope.payload,
                )
                session.add(msg_record)
                await session.commit()
            except Exception as exc:
                logger.error(
                    "Error during P2P message DB initial recording: %s", exc
                )

    # 2. Dispatch to specific type handler
    error_msg: str | None = None
    final_status = PeerMessageStatus.PROCESSED

    try:
        if envelope.message_type == PeerMessageType.PING.value:
            await _handle_ping(envelope, peer_conn)
        elif envelope.message_type == PeerMessageType.PONG.value:
            await _handle_pong(envelope, peer_conn)
        elif envelope.message_type == PeerMessageType.PEER_MESSAGE.value:
            await _handle_peer_message(envelope, peer_conn)
        elif envelope.message_type == PeerMessageType.EVIDENCE_ANNOUNCEMENT.value:
            await _handle_evidence_announcement(envelope, peer_conn)
        elif envelope.message_type == PeerMessageType.INCIDENT_ANNOUNCEMENT.value:
            await _handle_incident_announcement(envelope, peer_conn)
        else:
            logger.info(
                "Received generic P2P message type: %s from %s",
                envelope.message_type,
                envelope.source_node_id,
            )
    except Exception as exc:
        logger.error(
            "Exception while processing P2P message %s (%s): %s",
            envelope.message_id,
            envelope.message_type,
            exc,
        )
        final_status = PeerMessageStatus.FAILED
        error_msg = str(exc)

    # 3. Update DB record with final status (PROCESSED or FAILED)
    if async_session_factory is not None:
        async with async_session_factory() as session:
            try:
                stmt = select(PeerMessage).where(
                    PeerMessage.message_id == envelope.message_id
                )
                res = await session.execute(stmt)
                record = res.scalar_one_or_none()
                if record is not None:
                    record.status = final_status
                    record.processed_at = datetime.now(timezone.utc)
                    record.error_message = error_msg
                    await session.commit()
            except Exception as exc:
                logger.error("Failed to update P2P message status in DB: %s", exc)


async def _handle_ping(
    envelope: P2PMessageEnvelope, peer_conn: PeerConnection
) -> None:
    """Respond to PING with a direct PONG carrying the original echo timestamp."""
    echo_ts = envelope.payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    seq = envelope.payload.get("seq", 1)

    pong_payload = PongPayload(
        seq=seq,
        echo_timestamp=echo_ts,
    )

    pong_envelope = P2PMessageEnvelope(
        message_type=PeerMessageType.PONG.value,
        source_node_id=settings.node_id,
        target_node_id=envelope.source_node_id,
        payload=pong_payload.model_dump(),
    )

    logger.debug("Replying PONG to %s (seq=%s)", envelope.source_node_id, seq)
    await peer_conn.send_json(pong_envelope.model_dump(mode="json"))


async def _handle_pong(
    envelope: P2PMessageEnvelope, peer_conn: PeerConnection
) -> None:
    """Process PONG response, calculate RTT, and resolve waiting ping future."""
    echo_ts_str = envelope.payload.get("echo_timestamp")
    seq = envelope.payload.get("seq", 1)

    rtt_ms: float | None = None
    if echo_ts_str:
        try:
            sent_time = datetime.fromisoformat(echo_ts_str)
            now = datetime.now(timezone.utc)
            delta = now - sent_time
            rtt_ms = max(0.0, round(delta.total_seconds() * 1000, 2))
            peer_conn.rtt_ms = rtt_ms
            logger.info("P2P RTT with %s: %s ms", peer_conn.peer_node_id, rtt_ms)
        except Exception:
            pass

    # Resolve any waiting future
    fut = peer_conn.ping_futures.pop(seq, None)
    if fut and not fut.done():
        fut.set_result(rtt_ms if rtt_ms is not None else 0.0)


async def _handle_peer_message(
    envelope: P2PMessageEnvelope, peer_conn: PeerConnection
) -> None:
    """Process direct text message from peer."""
    text = envelope.payload.get("text", "")
    logger.info(
        "Direct P2P message received from %s: '%s'",
        envelope.source_node_id,
        text,
    )


async def _handle_evidence_announcement(
    envelope: P2PMessageEnvelope, peer_conn: PeerConnection
) -> None:
    """Process evidence announcement metadata from peer."""
    ev_id = envelope.payload.get("evidence_id")
    title = envelope.payload.get("title")
    logger.info(
        "P2P Evidence Announcement from %s: %s ('%s')",
        envelope.source_node_id,
        ev_id,
        title,
    )


async def _handle_incident_announcement(
    envelope: P2PMessageEnvelope, peer_conn: PeerConnection
) -> None:
    """Process incident announcement metadata from peer."""
    inc_id = envelope.payload.get("incident_id")
    title = envelope.payload.get("title")
    logger.info(
        "P2P Incident Announcement from %s: %s ('%s')",
        envelope.source_node_id,
        inc_id,
        title,
    )
