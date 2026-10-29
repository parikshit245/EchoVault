"""
WebRTCSession — Live multimedia session record (Part 9).

Tracks WebRTC multimedia sessions between evidence nodes and investigators:
  - Session lifecycle: REQUESTED → SIGNALING → CONNECTING → CONNECTED → ENDED / FAILED
  - Associated incident and source node
  - Configured media tracks (video, audio)
  - Timing and audit details
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class WebRTCSessionStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    SIGNALING = "SIGNALING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ENDED = "ENDED"
    FAILED = "FAILED"


class WebRTCSession(Base):
    __tablename__ = "webrtc_sessions"

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_webrtc_session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    requester_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default="investigator-ui"
    )
    source_node_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    status: Mapped[WebRTCSessionStatus] = mapped_column(
        Enum(WebRTCSessionStatus, name="webrtc_session_status", native_enum=True),
        nullable=False,
        default=WebRTCSessionStatus.REQUESTED,
        index=True,
    )
    has_video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
