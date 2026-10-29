"""
ReceivedMessage — local message inbox for this node.

Each received RabbitMQ message is persisted here so that:
  1. Idempotency can be enforced (unique constraint on message_id).
  2. Duplicate deliveries (RabbitMQ at-least-once guarantee) are detected.
  3. The /messaging monitor can display real message history.
  4. Operations teams can inspect failed/dead-lettered messages.

Status lifecycle:
  RECEIVED  → handler called
  PROCESSED → handler returned without error
  FAILED    → handler raised an exception
  IGNORED   → self-originated OR duplicate delivery
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ReceivedMessageStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    IGNORED = "IGNORED"


class ReceivedMessage(Base):
    __tablename__ = "received_messages"

    __table_args__ = (
        UniqueConstraint(
            "consumer_node_id",
            "message_id",
            name="uq_received_message_consumer_message",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    # The PostgreSQL database is shared by the Docker processes, but each
    # process has its own RabbitMQ inbox. The same envelope is therefore
    # expected to appear once per consuming node.
    consumer_node_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    source_node_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    routing_key: Mapped[str] = mapped_column(String(200), nullable=False)
    incident_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[ReceivedMessageStatus] = mapped_column(
        Enum(ReceivedMessageStatus, name="received_message_status", native_enum=True),
        nullable=False,
        default=ReceivedMessageStatus.RECEIVED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        "payload", JSON, nullable=True
    )
