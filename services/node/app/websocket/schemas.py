"""
WebSocket protocol schemas — Part 7.

Defines the JSON message protocol between the browser and the /ws/events endpoint.

Inbound messages (client → server):
  PingCommand          — { type: "ping" }
  SubscribeCommand     — { type: "subscribe", filters: {...} }
  UnsubscribeCommand   — { type: "unsubscribe", filters: {...} }

Outbound messages (server → client):
  ConnectedMessage         — sent on connection establishment
  PongMessage              — response to ping
  SubscriptionUpdated      — sent after subscribe/unsubscribe applied
  WsEventMessage           — wraps MessageEnvelope for delivery to browser
  ErrorMessage             — sent on invalid commands

Event envelope:
  The WsEventMessage reuses MessageEnvelope from messaging.schemas.
  WebSocket events use the SAME schema as RabbitMQ messages,
  ensuring the browser sees exactly what the distributed system produced.

Supported commands:
  subscribe / unsubscribe / ping
  All others → ErrorMessage(code=UNSUPPORTED_COMMAND)

Filter semantics (all filters are ANDed together per client):
  event_types       — exact match against envelope.event_type (list)
  source_node_ids   — exact match against envelope.source_node_id (list)
  incident_ids      — exact match against envelope.incident_id (list)
  Empty filters = receive all events (default on connect)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ── Subscription filters ──────────────────────────────────────────────────────


class SubscriptionFilters(BaseModel):
    """Server-side filtering config for a single WebSocket client."""

    event_types: list[str] = Field(default_factory=list)
    source_node_ids: list[str] = Field(default_factory=list)
    incident_ids: list[str] = Field(default_factory=list)

    @field_validator("event_types", mode="before")
    @classmethod
    def validate_event_types(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        # Accept only known event type prefixes — reject arbitrary strings
        allowed_prefixes = {"evidence", "incident", "node", "test", "dead"}
        result = []
        for item in v:
            if isinstance(item, str) and "." in item:
                prefix = item.split(".")[0]
                if prefix in allowed_prefixes:
                    result.append(item)
        return result

    def is_empty(self) -> bool:
        """True when no filters are set — client receives all events."""
        return (
            not self.event_types
            and not self.source_node_ids
            and not self.incident_ids
        )

    def matches(self, event_type: str, source_node_id: str, incident_id: str | None) -> bool:
        """Return True if the event passes all active filters (AND logic)."""
        if self.is_empty():
            return True
        if self.event_types and event_type not in self.event_types:
            return False
        if self.source_node_ids and source_node_id not in self.source_node_ids:
            return False
        if self.incident_ids:
            if incident_id is None or incident_id not in self.incident_ids:
                return False
        return True


# ── Inbound commands (client → server) ───────────────────────────────────────


class PingCommand(BaseModel):
    type: Literal["ping"] = "ping"


class SubscribeCommand(BaseModel):
    type: Literal["subscribe"] = "subscribe"
    filters: SubscriptionFilters = Field(default_factory=SubscriptionFilters)


class UnsubscribeCommand(BaseModel):
    type: Literal["unsubscribe"] = "unsubscribe"
    filters: SubscriptionFilters = Field(default_factory=SubscriptionFilters)


# ── Outbound messages (server → client) ──────────────────────────────────────


class ConnectedMessage(BaseModel):
    type: Literal["connected"] = "connected"
    connection_id: str
    node_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str = "Connected to EchoVault event stream"


class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SubscriptionUpdatedMessage(BaseModel):
    type: Literal["subscription.updated"] = "subscription.updated"
    filters: SubscriptionFilters
    message: str = "Subscription updated"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class WsEventMessage(BaseModel):
    """
    WebSocket event envelope — wraps MessageEnvelope for browser delivery.

    The 'type' discriminator lets the frontend know this is an event,
    not a protocol control message.
    """

    type: Literal["event"] = "event"
    message_id: str
    event_type: str
    source_node_id: str
    timestamp: datetime
    incident_id: str | None
    payload: dict[str, Any]
    # latency_ms is calculated at broadcast time (publish_ts → now)
    latency_ms: float | None = None
