"""
WebRTC Signaling Protocol Unit Tests — Part 9.

Tests:
  - SignalingMessage Pydantic envelope validation (offer, answer, ice_candidate, error)
  - SessionCreateRequest flat vs nested media option parsing
  - Unknown session signaling rejection
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.webrtc.manager import WebRTCManager
from app.webrtc.schemas import SessionCreateRequest, SignalingMessage


def test_signaling_message_offer():
    msg = SignalingMessage(
        type="offer",
        session_id="SESSION-123456",
        sdp="v=0\r\no=- 123 2 IN IP4 127.0.0.1\r\n...",
    )
    dumped = msg.model_dump()
    assert dumped["type"] == "offer"
    assert dumped["session_id"] == "SESSION-123456"
    assert "v=0" in dumped["sdp"]


def test_signaling_message_ice_candidate():
    msg = SignalingMessage(
        type="ice_candidate",
        session_id="SESSION-123456",
        candidate={
            "candidate": "candidate:842163049 1 udp 1677729535 192.168.1.1 50000 typ host",
            "sdpMid": "0",
            "sdpMLineIndex": 0,
        },
    )
    dumped = msg.model_dump()
    assert dumped["type"] == "ice_candidate"
    assert dumped["candidate"]["sdpMid"] == "0"


def test_session_create_request_parsing():
    # Nested media format
    req1 = SessionCreateRequest.model_validate({
        "node_id": "CCTV-A",
        "incident_id": "INC-000001",
        "media": {"video": True, "audio": False},
    })
    assert req1.node_id == "CCTV-A"
    assert req1.media.video is True
    assert req1.media.audio is False

    # Flat video/audio format
    req2 = SessionCreateRequest.model_validate({
        "node_id": "CCTV-B",
        "video": False,
        "audio": True,
    })
    assert req2.node_id == "CCTV-B"
    assert req2.media.video is False
    assert req2.media.audio is True


@pytest.mark.asyncio
async def test_signaling_unknown_session_rejection():
    """Connecting to an unknown session sends error message and closes socket."""
    manager = WebRTCManager()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()

    await manager.handle_signaling_connection("SESSION-NONEXISTENT", ws)

    ws.accept.assert_called_once()
    assert ws.send_json.call_count == 1
    sent_msg = ws.send_json.call_args[0][0]
    assert sent_msg["type"] == "error"
    assert "not found" in sent_msg["error"]
    ws.close.assert_called_once()
