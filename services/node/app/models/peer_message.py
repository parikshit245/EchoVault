"""
PeerMessage — local P2P message record for this node.

Each received direct P2P message is persisted here so that:
  1. Idempotency can be enforced (unique constraint on message_id).
  2. Duplicate deliveries (reconnect retries) are detected.
  3. The /peers monitor can display real P2P activity history.
  4. Node-to-node announcements (evidence, incident) are audited locally.

Status lifecycle:
  RECEIVED  → message parsed and handler invoked
  PROCESSED → handler completed successfully
  FAILED    → handler raised an exception
  IGNORED   → duplicate delivery or target mismatch
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PeerMessageStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class PeerMessageType(str, enum.Enum):
    HANDSHAKE = "HANDSHAKE"
    HANDSHAKE_ACK = "HANDSHAKE_ACK"
    PING = "PING"
    PONG = "PONG"
    PEER_MESSAGE = "PEER_MESSAGE"
    EVIDENCE_ANNOUNCEMENT = "EVIDENCE_ANNOUNCEMENT"
    INCIDENT_ANNOUNCEMENT = "INCIDENT_ANNOUNCEMENT"


class PeerMessage(Base):
    __tablename__ = "peer_messages"

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_peer_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    source_node_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    target_node_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    message_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[PeerMessageStatus] = mapped_column(
        Enum(PeerMessageStatus, name="peer_message_status", native_enum=True),
        nullable=False,
        default=PeerMessageStatus.RECEIVED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
