"""
Pydantic schemas for RabbitMQ message envelopes and payloads.

All messages published to echovault.events MUST use MessageEnvelope.
Payload models keep message contracts strongly typed.
Raw evidence file bytes and WebRTC media streams are NEVER included in messages — only metadata/references.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── Envelope ─────────────────────────────────────────────────────────────────


class MessageEnvelope(BaseModel):
    """Standard wrapper for every RabbitMQ message in EchoVault."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    source_node_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"
    correlation_id: str | None = None
    incident_id: str | None = None
    payload: dict[str, Any]


# ── Evidence payloads ─────────────────────────────────────────────────────────


class EvidenceCreatedPayload(BaseModel):
    evidence_id: str
    node_id: str
    event_type: str  # EventType value
    evidence_type: str  # EvidenceType value
    title: str
    incident_id: str | None = None
    captured_at: datetime | None = None


class EvidenceUpdatedPayload(BaseModel):
    evidence_id: str
    node_id: str
    incident_id: str | None = None
    title: str | None = None
    description: str | None = None
    updated_at: datetime | None = None


class EvidenceDeletedPayload(BaseModel):
    evidence_id: str
    node_id: str
    incident_id: str | None = None
    deleted_at: datetime


# ── Incident payloads ─────────────────────────────────────────────────────────


class IncidentCreatedPayload(BaseModel):
    incident_id: str
    title: str
    incident_type: str
    severity: str
    status: str
    created_by_node_id: str


class IncidentUpdatedPayload(BaseModel):
    incident_id: str
    title: str | None = None
    status: str | None = None
    severity: str | None = None
    updated_at: datetime | None = None


class IncidentClosedPayload(BaseModel):
    incident_id: str
    title: str
    status: str
    ended_at: datetime | None = None


class EvidenceAssociatedPayload(BaseModel):
    incident_id: str
    evidence_id: str
    node_id: str


class EvidenceRemovedPayload(BaseModel):
    incident_id: str
    evidence_id: str
    node_id: str


# ── Node payloads ─────────────────────────────────────────────────────────────


class NodeRegisteredPayload(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    host: str
    port: int


class NodeStatusChangedPayload(BaseModel):
    node_id: str
    status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── WebRTC Session Lifecycle payloads (Part 9) ───────────────────────────────


class WebRTCSessionRequestedPayload(BaseModel):
    session_id: str
    node_id: str
    incident_id: str | None = None
    has_video: bool = True
    has_audio: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebRTCSessionStartedPayload(BaseModel):
    session_id: str
    node_id: str
    incident_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebRTCSessionEndedPayload(BaseModel):
    session_id: str
    node_id: str
    incident_id: str | None = None
    duration_seconds: float | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebRTCSessionFailedPayload(BaseModel):
    session_id: str
    node_id: str
    incident_id: str | None = None
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Dev test payload (dev/testing endpoint only) ─────────────────────────────


class DevTestPayload(BaseModel):
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)
