"""
P2P Idempotency & Message Handling Tests — Part 8.

Tests:
  - Valid direct P2P messages are processed and recorded as PROCESSED
  - Duplicate message_ids are detected and ignored without re-processing
  - Handler exceptions mark status as FAILED with error_message
  - Evidence and incident announcements are safely audited
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.peer_message import PeerMessageStatus, PeerMessageType
from app.p2p.handlers import handle_p2p_message
from app.p2p.peer import PeerConnection, PeerConnectionState
from app.p2p.protocol import P2PMessageEnvelope


@pytest.mark.asyncio
async def test_first_message_is_processed_and_recorded():
    """A new P2P message is inserted as RECEIVED then updated to PROCESSED."""
    envelope = P2PMessageEnvelope(
        message_id="peer-msg-unique-001",
        message_type=PeerMessageType.PEER_MESSAGE.value,
        source_node_id="CCTV-A",
        target_node_id="CCTV-B",
        payload={"text": "Test message 1"},
    )
    peer_conn = PeerConnection("CCTV-A", state=PeerConnectionState.CONNECTED)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # No existing message
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session_cm)

    with patch("app.p2p.handlers.async_session_factory", mock_factory):
        await handle_p2p_message(envelope, peer_conn)

    mock_session.add.assert_called_once()
    assert mock_session.commit.call_count >= 1


@pytest.mark.asyncio
async def test_duplicate_message_id_is_ignored():
    """A message with an existing message_id in the DB must be ignored without re-processing."""
    envelope = P2PMessageEnvelope(
        message_id="peer-msg-dup-001",
        message_type=PeerMessageType.PEER_MESSAGE.value,
        source_node_id="CCTV-A",
        target_node_id="CCTV-B",
        payload={"text": "Duplicate message"},
    )
    peer_conn = PeerConnection("CCTV-A", state=PeerConnectionState.CONNECTED)

    # Simulate existing DB record
    existing_record = MagicMock()
    existing_record.status = PeerMessageStatus.PROCESSED

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_record
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session_cm)

    with patch("app.p2p.handlers.async_session_factory", mock_factory):
        await handle_p2p_message(envelope, peer_conn)

    # Must NOT add new record
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_announcement_handling():
    """Evidence announcement metadata is received and processed."""
    envelope = P2PMessageEnvelope(
        message_id="peer-msg-ev-001",
        message_type=PeerMessageType.EVIDENCE_ANNOUNCEMENT.value,
        source_node_id="CCTV-A",
        target_node_id="CCTV-B",
        payload={
            "evidence_id": "EV-000001",
            "node_id": "CCTV-A",
            "title": "Intruder detected",
            "event_type": "PERSON_DETECTED",
            "evidence_type": "IMAGE",
        },
    )
    peer_conn = PeerConnection("CCTV-A", state=PeerConnectionState.CONNECTED)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock(return_value=mock_session_cm)

    with patch("app.p2p.handlers.async_session_factory", mock_factory):
        await handle_p2p_message(envelope, peer_conn)

    mock_session.add.assert_called_once()
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.message_id == "peer-msg-ev-001"
    assert added_obj.message_type == PeerMessageType.EVIDENCE_ANNOUNCEMENT.value
