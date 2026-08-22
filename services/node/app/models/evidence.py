import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class EvidenceType(str, enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    TEXT = "TEXT"
    SENSOR = "SENSOR"
    OTHER = "OTHER"


class EventType(str, enum.Enum):
    MOTION_DETECTED = "MOTION_DETECTED"
    PERSON_DETECTED = "PERSON_DETECTED"
    AUDIO_DETECTED = "AUDIO_DETECTED"
    DOOR_OPENED = "DOOR_OPENED"
    OBJECT_DETECTED = "OBJECT_DETECTED"
    MANUAL_OBSERVATION = "MANUAL_OBSERVATION"
    OTHER = "OTHER"


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"), index=True, nullable=False)
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.incident_id"), index=True, nullable=True
    )
    evidence_type: Mapped[EvidenceType] = mapped_column(
        Enum(EvidenceType, name="evidence_type", native_enum=True), index=True, nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type", native_enum=True), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    location: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["Node"] = relationship(back_populates="evidence", lazy="joined")
    incident: Mapped["Incident | None"] = relationship(back_populates="evidence")