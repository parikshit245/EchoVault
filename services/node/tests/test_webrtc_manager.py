"""
WebRTC Manager Unit Tests — Part 9.

Tests:
  - Session creation lifecycle and RabbitMQ event publication
  - Offline node rejection (NodeUnavailableError)
  - Session teardown and resource release
  - Session timeout handling (auto-fail abandoned sessions)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.node import NodeStatus
from app.models.webrtc_session import WebRTCSessionStatus
from app.webrtc.manager import NodeUnavailableError, WebRTCManager
from app.webrtc.schemas import SessionCreateRequest


@pytest.mark.asyncio
async def test_create_session_success():
    manager = WebRTCManager()

    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    req = SessionCreateRequest(
        node_id="CCTV-A",
        incident_id="INC-000001",
        video=True,
        audio=True,
    )

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock) as mock_pub,
    ):
        res = await manager.create_session(req)

    assert res.session_id.startswith("SESSION-")
    assert res.node_id == "CCTV-A"
    assert res.status == WebRTCSessionStatus.REQUESTED.value
    assert res.signaling_url == f"/ws/webrtc/{res.session_id}"

    # Verify RabbitMQ event published
    mock_pub.assert_called_once()
    assert mock_pub.call_args[1]["event_type"] == "webrtc.session_requested"


@pytest.mark.asyncio
async def test_create_session_offline_node_fails():
    manager = WebRTCManager()

    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.OFFLINE  # Node is offline!

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    req = SessionCreateRequest(node_id="CCTV-A")

    with patch("app.webrtc.manager.async_session_factory", mock_factory):
        with pytest.raises(NodeUnavailableError) as exc_info:
            await manager.create_session(req)

    assert "currently OFFLINE" in str(exc_info.value)


@pytest.mark.asyncio
async def test_close_session_releases_resources():
    manager = WebRTCManager()

    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    req = SessionCreateRequest(node_id="CCTV-A")

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock),
    ):
        created = await manager.create_session(req)

    # Attach mock PeerConnection
    mock_pc = AsyncMock()
    mock_pc.close = AsyncMock()
    manager._sessions[created.session_id].pc = mock_pc

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock) as mock_pub,
    ):
        stop_res = await manager.close_session(created.session_id)

    assert stop_res.status == WebRTCSessionStatus.ENDED.value
    mock_pc.close.assert_called_once()
    assert manager._sessions[created.session_id].status == WebRTCSessionStatus.ENDED

    # Verify webrtc.session_ended was published
    mock_pub.assert_called_once()
    assert mock_pub.call_args[1]["event_type"] == "webrtc.session_ended"


@pytest.mark.asyncio
async def test_session_timeout_transitions_to_failed():
    """If connection negotiation exceeds timeout, session becomes FAILED."""
    manager = WebRTCManager()

    mock_node = MagicMock()
    mock_node.node_id = "CCTV-A"
    mock_node.status = NodeStatus.ONLINE

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_node
    mock_session.execute = AsyncMock(return_value=mock_res)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)

    req = SessionCreateRequest(node_id="CCTV-A")

    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock),
    ):
        created = await manager.create_session(req)

    # Simulate timeout worker triggering
    with (
        patch("app.webrtc.manager.async_session_factory", mock_factory),
        patch("app.webrtc.manager.publish_event", new_callable=AsyncMock) as mock_pub,
    ):
        await manager.fail_session(created.session_id, reason="Timed out")

    assert manager._sessions[created.session_id].status == WebRTCSessionStatus.FAILED
    mock_pub.assert_called_once()
    assert mock_pub.call_args[1]["event_type"] == "webrtc.session_failed"
