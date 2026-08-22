import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class IncidentType(str, enum.Enum):
    SECURITY = "SECURITY"
    ACCIDENT = "ACCIDENT"
    INTRUSION = "INTRUSION"
    THEFT = "THEFT"
    VANDALISM = "VANDALISM"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    OTHER = "OTHER"


class IncidentStatus(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentRole(str, enum.Enum):
    OBSERVER = "OBSERVER"
    INVESTIGATOR = "INVESTIGATOR"
    COORDINATOR = "COORDINATOR"


class IncidentNodeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, name="incident_type", native_enum=True), index=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", native_enum=True), index=True, nullable=False,
        default=IncidentStatus.OPEN,
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incident_severity", native_enum=True), index=True, nullable=False,
        default=IncidentSeverity.MEDIUM,
    )
    location: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"), index=True, nullable=False)

    creator: Mapped["Node"] = relationship(lazy="joined")
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="incident")
    participating_nodes: Mapped[list["IncidentNode"]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentNode(Base):
    __tablename__ = "incident_nodes"

    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.incident_id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[IncidentRole] = mapped_column(
        Enum(IncidentRole, name="incident_role", native_enum=True), nullable=False, default=IncidentRole.OBSERVER
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[IncidentNodeStatus] = mapped_column(
        Enum(IncidentNodeStatus, name="incident_node_status", native_enum=True), nullable=False,
        default=IncidentNodeStatus.ACTIVE,
    )

    incident: Mapped[Incident] = relationship(back_populates="participating_nodes")
    node: Mapped["Node"] = relationship(back_populates="incident_nodes", lazy="joined")