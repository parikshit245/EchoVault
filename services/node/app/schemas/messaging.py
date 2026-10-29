"""Pydantic response schemas for the messaging API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..models.received_message import ReceivedMessageStatus


class ReceivedMessageResponse(BaseModel):
    """Response schema for a single received message record."""

    id: Any  # UUID — serialised as string in JSON
    message_id: str
    consumer_node_id: str
    source_node_id: str
    event_type: str
    routing_key: str
    incident_id: str | None
    received_at: datetime
    processed_at: datetime | None
    status: ReceivedMessageStatus
    error_message: str | None

    model_config = {"from_attributes": True}
