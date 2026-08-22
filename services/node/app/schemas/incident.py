from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.incident import IncidentNodeStatus, IncidentRole, IncidentSeverity, IncidentStatus, IncidentType


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    incident_type: IncidentType
    description: str | None = Field(default=None, max_length=10000)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    location: dict[str, Any] | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    status: IncidentStatus | None = None
    severity: IncidentSeverity | None = None
    location: dict[str, Any] | None = None
    ended_at: datetime | None = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    incident_id: str
    title: str
    incident_type: IncidentType
    description: str | None
    status: IncidentStatus
    severity: IncidentSeverity
    location: dict[str, Any] | None
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by_node_id: str
    created_by_node_name: str


class IncidentNodeCreate(BaseModel):
    role: IncidentRole = IncidentRole.OBSERVER


class IncidentNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    incident_id: str
    node_id: str
    node_name: str
    role: IncidentRole
    joined_at: datetime
    status: IncidentNodeStatus