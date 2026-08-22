"""
RabbitMQ configuration constants and helpers.

Exchange design:
  echovault.events  — topic exchange, durable
    Routing keys:
      evidence.created, evidence.updated, evidence.deleted
      incident.created, incident.updated, incident.closed
      incident.evidence_associated, incident.evidence_removed
      node.registered, node.status_changed
      test.message (dev only)

  echovault.dead-letter — topic exchange, durable
    Dead-letter destination for repeatedly failed messages.

Queue design:
  Each node has its own durable queue: echovault.node.{NODE_ID}
  Bound to patterns: evidence.*, incident.*, node.*
"""

from ..config import settings

# ── Exchange names ────────────────────────────────────────────────────────────
EXCHANGE_NAME: str = "echovault.events"
DEAD_LETTER_EXCHANGE: str = "echovault.dead-letter"

# ── Routing key constants ─────────────────────────────────────────────────────
EVIDENCE_CREATED = "evidence.created"
EVIDENCE_UPDATED = "evidence.updated"
EVIDENCE_DELETED = "evidence.deleted"

INCIDENT_CREATED = "incident.created"
INCIDENT_UPDATED = "incident.updated"
INCIDENT_CLOSED = "incident.closed"

INCIDENT_EVIDENCE_ASSOCIATED = "incident.evidence_associated"
INCIDENT_EVIDENCE_REMOVED = "incident.evidence_removed"

NODE_REGISTERED = "node.registered"
NODE_STATUS_CHANGED = "node.status_changed"

TEST_MESSAGE = "test.message"

# ── Queue configuration ───────────────────────────────────────────────────────
# Wildcard patterns each node subscribes to
QUEUE_BINDING_PATTERNS: list[str] = [
    "evidence.*",
    "incident.*",
    "node.*",
    "test.*",
]


def node_queue_name(node_id: str) -> str:
    """Return the canonical queue name for a given node."""
    return f"echovault.node.{node_id}"


def get_rabbitmq_url() -> str:
    """Build the AMQP connection URL from settings."""
    s = settings
    # URL-encode the vhost: "/" must become "%2F" in the path
    vhost = s.rabbitmq_vhost
    if vhost.startswith("/"):
        vhost = "%2F" + vhost[1:]
    return (
        f"amqp://{s.rabbitmq_username}:{s.rabbitmq_password}"
        f"@{s.rabbitmq_host}:{s.rabbitmq_port}/{vhost}"
    )
