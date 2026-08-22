"""
RabbitMQ message handlers — Part 6.

Each handler corresponds to one event_type routing key.
Currently, handlers log the received event and store it in the local
ReceivedMessage inbox.  They do NOT perform cross-node database writes —
that responsibility belongs to later synchronization parts (Part 7+).

Self-originated events (source_node_id == local node_id) are recorded
as IGNORED and not processed further, preventing duplicate evidence creation.

Dispatcher:
    EVENT_HANDLERS maps routing key → handler coroutine.
    Any event_type not in EVENT_HANDLERS falls through to handle_unknown().
"""

from __future__ import annotations

import logging
from typing import Any

from .schemas import MessageEnvelope

logger = logging.getLogger("echovault.messaging.handlers")


async def handle_evidence_created(envelope: MessageEnvelope, session: Any) -> None:
    """Log receipt of evidence.created from a remote node."""
    p = envelope.payload
    logger.info(
        "Evidence created on remote node: evidence_id=%s node=%s title=%s",
        p.get("evidence_id"),
        envelope.source_node_id,
        p.get("title"),
    )


async def handle_evidence_updated(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Evidence updated on remote node: evidence_id=%s node=%s",
        p.get("evidence_id"),
        envelope.source_node_id,
    )


async def handle_evidence_deleted(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Evidence deleted on remote node: evidence_id=%s node=%s deleted_at=%s",
        p.get("evidence_id"),
        envelope.source_node_id,
        p.get("deleted_at"),
    )


async def handle_incident_created(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Incident created: incident_id=%s title=%s severity=%s by node=%s",
        p.get("incident_id"),
        p.get("title"),
        p.get("severity"),
        envelope.source_node_id,
    )


async def handle_incident_updated(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Incident updated: incident_id=%s status=%s by node=%s",
        p.get("incident_id"),
        p.get("status"),
        envelope.source_node_id,
    )


async def handle_incident_closed(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Incident closed: incident_id=%s ended_at=%s by node=%s",
        p.get("incident_id"),
        p.get("ended_at"),
        envelope.source_node_id,
    )


async def handle_evidence_associated(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Evidence associated: evidence_id=%s → incident_id=%s by node=%s",
        p.get("evidence_id"),
        p.get("incident_id"),
        envelope.source_node_id,
    )


async def handle_evidence_removed(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Evidence removed from incident: evidence_id=%s incident_id=%s by node=%s",
        p.get("evidence_id"),
        p.get("incident_id"),
        envelope.source_node_id,
    )


async def handle_node_registered(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Node registered: node_id=%s type=%s host=%s:%s",
        p.get("node_id"),
        p.get("node_type"),
        p.get("host"),
        p.get("port"),
    )


async def handle_node_status_changed(envelope: MessageEnvelope, session: Any) -> None:
    p = envelope.payload
    logger.info(
        "Node status changed: node_id=%s status=%s",
        p.get("node_id"),
        p.get("status"),
    )


async def handle_test_message(envelope: MessageEnvelope, session: Any) -> None:
    """Handler for dev/testing messages only — not part of business logic."""
    logger.info(
        "TEST MESSAGE received from %s: %s",
        envelope.source_node_id,
        envelope.payload.get("message"),
    )


async def handle_unknown(envelope: MessageEnvelope, session: Any) -> None:
    logger.warning(
        "Received unknown event_type=%s from node=%s message_id=%s",
        envelope.event_type,
        envelope.source_node_id,
        envelope.message_id,
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────
EVENT_HANDLERS: dict[str, Any] = {
    "evidence.created": handle_evidence_created,
    "evidence.updated": handle_evidence_updated,
    "evidence.deleted": handle_evidence_deleted,
    "incident.created": handle_incident_created,
    "incident.updated": handle_incident_updated,
    "incident.closed": handle_incident_closed,
    "incident.evidence_associated": handle_evidence_associated,
    "incident.evidence_removed": handle_evidence_removed,
    "node.registered": handle_node_registered,
    "node.status_changed": handle_node_status_changed,
    "test.message": handle_test_message,
}
