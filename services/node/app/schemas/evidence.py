from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.evidence import EvidenceType, EventType


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_type: EvidenceType
    event_type: EventType = EventType.OTHER
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    incident_id: str | None = Field(default=None, max_length=100)
    location: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class EvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    incident_id: str | None = Field(default=None, max_length=100)
    incident_id: str | None = Field(default=None, max_length=100)
    location: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def update_title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_id: str
    node_id: str
    node_name: str
    incident_id: str | None
    evidence_type: EvidenceType
    event_type: EventType
    title: str
    description: str | None
    captured_at: datetime
    received_at: datetime
    location: dict[str, Any] | None
    file_name: str | None
    file_path: str | None
    mime_type: str | None
    file_size: int | None
    metadata: dict[str, Any] | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
