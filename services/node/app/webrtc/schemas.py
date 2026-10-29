"""
WebRTC Pydantic Schemas (Part 9).

Defines:
  - Session request and response contracts
  - WebRTC signaling envelopes for SDP offer/answer and ICE candidate exchange
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SessionMediaOptions(BaseModel):
    video: bool = True
    audio: bool = True


class SessionCreateRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=100)
    incident_id: str | None = None
    media: SessionMediaOptions = Field(default_factory=SessionMediaOptions)
    requester_id: str = "investigator-ui"

    @model_validator(mode="before")
    @classmethod
    def handle_flat_media_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Allow flat video/audio fields or nested media: {"video": true, "audio": true}
            if "media" not in values:
                v = values.get("video", True)
                a = values.get("audio", True)
                values["media"] = {"video": bool(v), "audio": bool(a)}
        return values


class SessionResponse(BaseModel):
    session_id: str
    node_id: str
    incident_id: str | None = None
    status: str
    signaling_url: str
    has_video: bool
    has_audio: bool
    created_at: datetime


class SessionStopResponse(BaseModel):
    session_id: str
    status: str
    duration_seconds: float | None = None


class SessionDetailResponse(BaseModel):
    session_id: str
    incident_id: str | None
    requester_id: str
    source_node_id: str
    status: str
    has_video: bool
    has_audio: bool
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    error_message: str | None


class SignalingMessage(BaseModel):
    """Envelope for all WebRTC signaling messages on /ws/webrtc/{session_id}."""

    type: str  # "offer", "answer", "ice_candidate", "session_started", "session_ended", "error"
    session_id: str
    sdp: str | None = None
    candidate: dict[str, Any] | None = None
    error: str | None = None
