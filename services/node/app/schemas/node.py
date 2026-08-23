from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.node import NodeStatus, NodeType


class NodeCreate(BaseModel):
    node_id: str = Field(min_length=1, max_length=100)
    node_name: str = Field(min_length=1, max_length=200)
    node_type: NodeType
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    grpc_host: str | None = Field(default=None, max_length=255)
    grpc_port: int | None = Field(default=None, ge=1, le=65535)
    p2p_host: str | None = Field(default=None, max_length=255)
    p2p_port: int | None = Field(default=None, ge=1, le=65535)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("node_id", "node_name", "host")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class NodeUpdate(BaseModel):
    node_name: str | None = Field(default=None, min_length=1, max_length=200)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    grpc_host: str | None = Field(default=None, max_length=255)
    grpc_port: int | None = Field(default=None, ge=1, le=65535)
    p2p_host: str | None = Field(default=None, max_length=255)
    p2p_port: int | None = Field(default=None, ge=1, le=65535)
    status: NodeStatus | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("node_name", "host")
    @classmethod
    def reject_blank_optional_values(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class NodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_id: str
    node_name: str
    node_type: NodeType
    host: str
    port: int
    grpc_host: str | None
    grpc_port: int | None
    p2p_host: str | None
    p2p_port: int | None
    status: NodeStatus
    description: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None


class NodeSelfResponse(BaseModel):
    node_id: str
    node_name: str
    node_type: NodeType
    host: str
    port: int
    grpc_host: str
    grpc_port: int
    p2p_host: str
    p2p_port: int


class NodeHeartbeatResponse(BaseModel):
    node_id: str
    status: NodeStatus
    last_seen_at: datetime