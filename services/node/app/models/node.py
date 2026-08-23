import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class NodeType(str, enum.Enum):
    EVIDENCE = "EVIDENCE"
    SECURITY = "SECURITY"
    MOBILE = "MOBILE"
    COORDINATOR = "COORDINATOR"


class NodeStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(200), nullable=False)
    node_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, name="node_type", native_enum=True), nullable=False
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    grpc_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grpc_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p2p_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    p2p_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[NodeStatus] = mapped_column(
        Enum(NodeStatus, name="node_status", native_enum=True),
        nullable=False,
        default=NodeStatus.UNKNOWN,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="owner")
    incident_nodes: Mapped[list["IncidentNode"]] = relationship(back_populates="node")