"""
WebRTC Peer Connection & Session Manager (Part 9).

Coordinates:
  - Session lifecycle: REQUESTED → SIGNALING → CONNECTING → CONNECTED → ENDED / FAILED
  - Media track attachment (DemoVideoTrack, DemoAudioTrack)
  - SDP Offer/Answer negotiation & ICE candidate handling
  - Timeout enforcement for abandoned sessions
  - RabbitMQ session lifecycle event publication
  - Clean resource teardown (closing PeerConnection, tracks, signaling sockets)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
import aioice
# Disable mDNS ICE candidate generation.
# Inside Docker, aioice generates *.local mDNS addresses that are only resolvable
# within the Docker bridge network. The browser (running on the host) cannot resolve
# these candidates, causing ICE negotiation to fail permanently.
# Setting USE_MDNS = False forces aioice to use plain IP-based host candidates instead.
aioice.USE_MDNS = False  # type: ignore[attr-defined]
from fastapi import WebSocket
from sqlalchemy import select, update

from ..config import settings
from ..database import async_session_factory
from ..messaging.publisher import publish_event
from ..messaging.schemas import (
    WebRTCSessionEndedPayload,
    WebRTCSessionFailedPayload,
    WebRTCSessionRequestedPayload,
    WebRTCSessionStartedPayload,
)
from ..models.node import Node, NodeStatus
from ..models.webrtc_session import WebRTCSession, WebRTCSessionStatus
from .schemas import (
    SessionCreateRequest,
    SessionDetailResponse,
    SessionResponse,
    SessionStopResponse,
    SignalingMessage,
)
from .tracks import create_media_tracks

logger = logging.getLogger("echovault.webrtc")


class SessionNotFoundError(Exception):
    pass


class SessionInvalidStateError(Exception):
    pass


class NodeUnavailableError(Exception):
    pass


@dataclass
class ActiveSessionContext:
    session_id: str
    node_id: str
    incident_id: str | None
    requester_id: str
    status: WebRTCSessionStatus
    has_video: bool
    has_audio: bool
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    pc: RTCPeerConnection | None = None
    tracks: list[Any] = field(default_factory=list)
    signaling_ws: WebSocket | None = None
    timeout_task: asyncio.Task | None = None
    error_message: str | None = None


class WebRTCManager:
    """Singleton managing active WebRTC multimedia sessions and signaling."""

    def __init__(self) -> None:
        self._sessions: dict[str, ActiveSessionContext] = {}
        self._lock = asyncio.Lock()

    # ── Session Lifecycle Operations ─────────────────────────────────────────

    async def create_session(
        self, req: SessionCreateRequest, base_url: str = ""
    ) -> SessionResponse:
        """
        Initiates a new WebRTC session with the requested node.
        Validates target node, persists session to DB, and publishes RabbitMQ event.
        """
        target_node_id = req.node_id.strip()

        # 1. Validate target node
        if async_session_factory is not None:
            async with async_session_factory() as session:
                stmt = select(Node).where(Node.node_id == target_node_id)
                res = await session.execute(stmt)
                node = res.scalar_one_or_none()
                if not node:
                    raise NodeUnavailableError(f"Node '{target_node_id}' not found in registry.")
                if node.status == NodeStatus.OFFLINE:
                    raise NodeUnavailableError(f"Node '{target_node_id}' is currently OFFLINE.")

        session_id = f"SESSION-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        ctx = ActiveSessionContext(
            session_id=session_id,
            node_id=target_node_id,
            incident_id=req.incident_id,
            requester_id=req.requester_id,
            status=WebRTCSessionStatus.REQUESTED,
            has_video=req.media.video,
            has_audio=req.media.audio,
            created_at=now,
        )

        async with self._lock:
            self._sessions[session_id] = ctx

        # 2. Persist to DB
        if async_session_factory is not None:
            try:
                async with async_session_factory() as session:
                    db_session = WebRTCSession(
                        session_id=session_id,
                        incident_id=req.incident_id,
                        requester_id=req.requester_id,
                        source_node_id=target_node_id,
                        status=WebRTCSessionStatus.REQUESTED,
                        has_video=req.media.video,
                        has_audio=req.media.audio,
                        created_at=now,
                    )
                    session.add(db_session)
                    await session.commit()
            except Exception as exc:
                logger.error("Failed to persist WebRTCSession to DB: %s", exc)

        # 3. Publish webrtc.session_requested event to RabbitMQ
        await publish_event(
            event_type="webrtc.session_requested",
            payload=WebRTCSessionRequestedPayload(
                session_id=session_id,
                node_id=target_node_id,
                incident_id=req.incident_id,
                has_video=req.media.video,
                has_audio=req.media.audio,
                timestamp=now,
            ).model_dump(mode="json"),
            incident_id=req.incident_id,
        )

        # 4. Start timeout task for negotiation
        ctx.timeout_task = asyncio.create_task(
            self._session_timeout_worker(session_id, settings.webrtc_session_timeout_seconds)
        )

        signaling_url = f"/ws/webrtc/{session_id}"

        return SessionResponse(
            session_id=session_id,
            node_id=target_node_id,
            incident_id=req.incident_id,
            status=WebRTCSessionStatus.REQUESTED.value,
            signaling_url=signaling_url,
            has_video=req.media.video,
            has_audio=req.media.audio,
            created_at=now,
        )

    async def _session_timeout_worker(self, session_id: str, timeout_seconds: int) -> None:
        """Marks session as FAILED if it does not reach CONNECTED before timeout."""
        try:
            await asyncio.sleep(timeout_seconds)
            ctx = self._sessions.get(session_id)
            if ctx and ctx.status in (
                WebRTCSessionStatus.REQUESTED,
                WebRTCSessionStatus.SIGNALING,
                WebRTCSessionStatus.CONNECTING,
            ):
                logger.warning(
                    "WebRTC session %s timed out waiting for connection (state=%s)",
                    session_id,
                    ctx.status,
                )
                await self.fail_session(session_id, reason=f"Session timed out after {timeout_seconds}s")
        except asyncio.CancelledError:
            pass

    # ── Signaling WebSocket Handler ──────────────────────────────────────────

    async def handle_signaling_connection(
        self, session_id: str, websocket: WebSocket
    ) -> None:
        """
        Manages dedicated WebSocket signaling loop for session SDP/ICE negotiation.
        """
        ctx = self._sessions.get(session_id)
        if not ctx:
            # Query DB to check if valid past session
            await websocket.accept()
            await websocket.send_json(
                SignalingMessage(
                    type="error",
                    session_id=session_id,
                    error=f"Session '{session_id}' not found.",
                ).model_dump()
            )
            await websocket.close(code=1008, reason="Session not found")
            return

        if ctx.status in (WebRTCSessionStatus.ENDED, WebRTCSessionStatus.FAILED):
            await websocket.accept()
            await websocket.send_json(
                SignalingMessage(
                    type="error",
                    session_id=session_id,
                    error=f"Session '{session_id}' is already {ctx.status.value}.",
                ).model_dump()
            )
            await websocket.close(code=1008, reason="Session already closed")
            return

        await websocket.accept()
        ctx.signaling_ws = websocket
        ctx.status = WebRTCSessionStatus.SIGNALING
        await self._update_db_status(session_id, WebRTCSessionStatus.SIGNALING)

        # Create aiortc RTCPeerConnection
        # In Docker, aioice defaults to generating mDNS (*.local) ICE candidates which
        # are only valid inside the Docker network — the browser cannot reach them.
        # We inject the STUN server so public candidates are also gathered,
        # and we rely on the STUN srflx candidates for browser connectivity.
        ice_servers = []
        if settings.webrtc_stun_server:
            ice_servers.append(RTCIceServer(urls=[settings.webrtc_stun_server]))
        else:
            # Always include at least one STUN server so srflx candidates are generated
            ice_servers.append(RTCIceServer(urls=["stun:stun.l.google.com:19302"]))

        config = RTCConfiguration(iceServers=ice_servers)
        pc = RTCPeerConnection(configuration=config)
        ctx.pc = pc

        # Attach media tracks
        media_tracks = create_media_tracks(
            node_id=ctx.node_id,
            has_video=ctx.has_video,
            has_audio=ctx.has_audio,
        )
        ctx.tracks = media_tracks
        for track in media_tracks:
            pc.addTrack(track)

        @pc.on("connectionstatechange")
        async def on_connection_state_change():
            state = pc.connectionState
            logger.info("WebRTC session %s connectionState -> %s", session_id, state)
            if state == "connected":
                now = datetime.now(timezone.utc)
                ctx.status = WebRTCSessionStatus.CONNECTED
                ctx.started_at = now
                if ctx.timeout_task and not ctx.timeout_task.done():
                    ctx.timeout_task.cancel()
                await self._update_db_status(
                    session_id, WebRTCSessionStatus.CONNECTED, started_at=now
                )
                await publish_event(
                    event_type="webrtc.session_started",
                    payload=WebRTCSessionStartedPayload(
                        session_id=session_id,
                        node_id=ctx.node_id,
                        incident_id=ctx.incident_id,
                        timestamp=now,
                    ).model_dump(mode="json"),
                    incident_id=ctx.incident_id,
                )
            elif state in ("failed", "closed"):
                if ctx.status not in (WebRTCSessionStatus.ENDED, WebRTCSessionStatus.FAILED):
                    await self.fail_session(session_id, reason=f"PeerConnection entered {state} state")

        try:
            while True:
                msg_text = await websocket.receive_text()
                try:
                    msg_dict = json.loads(msg_text)
                    signaling_msg = SignalingMessage.model_validate(msg_dict)
                except Exception as exc:
                    logger.warning("Malformed signaling message for %s: %s", session_id, exc)
                    await websocket.send_json(
                        SignalingMessage(
                            type="error",
                            session_id=session_id,
                            error=f"Invalid signaling envelope: {exc}",
                        ).model_dump()
                    )
                    continue

                if signaling_msg.session_id != session_id:
                    await websocket.send_json(
                        SignalingMessage(
                            type="error",
                            session_id=session_id,
                            error="Session ID mismatch in signaling envelope.",
                        ).model_dump()
                    )
                    continue

                # Process message types
                if signaling_msg.type == "offer":
                    if not signaling_msg.sdp:
                        await websocket.send_json(
                            SignalingMessage(
                                type="error",
                                session_id=session_id,
                                error="Missing SDP payload in offer.",
                            ).model_dump()
                        )
                        continue

                    offer = RTCSessionDescription(sdp=signaling_msg.sdp, type="offer")
                    await pc.setRemoteDescription(offer)
                    ctx.status = WebRTCSessionStatus.CONNECTING
                    await self._update_db_status(session_id, WebRTCSessionStatus.CONNECTING)

                    # Create and set answer
                    answer = await pc.createAnswer()
                    await pc.setLocalDescription(answer)

                    # Wait for ICE candidate gathering to complete so all candidates are embedded in SDP answer
                    for _ in range(30):
                        if pc.iceGatheringState == "complete":
                            break
                        await asyncio.sleep(0.05)

                    # Send answer back over signaling WebSocket
                    await websocket.send_json(
                        SignalingMessage(
                            type="answer",
                            session_id=session_id,
                            sdp=pc.localDescription.sdp,
                        ).model_dump()
                    )
                    logger.info("Sent SDP answer for WebRTC session %s", session_id)

                elif signaling_msg.type == "ice_candidate":
                    if signaling_msg.candidate:
                        try:
                            cand_dict = signaling_msg.candidate
                            cand_str = cand_dict.get("candidate", "")
                            if cand_str:
                                # Strip prefix if present
                                clean_cand = (
                                    cand_str[10:].strip()
                                    if cand_str.startswith("candidate:")
                                    else cand_str.strip()
                                )
                                cand = candidate_from_sdp(clean_cand)
                                cand.sdpMid = cand_dict.get("sdpMid")
                                cand.sdpMLineIndex = cand_dict.get("sdpMLineIndex")
                                await pc.addIceCandidate(cand)
                        except Exception as exc:
                            logger.warning(
                                "Failed to add remote ICE candidate for %s: %s",
                                session_id,
                                exc,
                            )

                elif signaling_msg.type == "session_end":
                    logger.info("Client requested termination of WebRTC session %s", session_id)
                    await self.close_session(session_id)
                    break

        except (Exception, asyncio.CancelledError) as exc:
            logger.info("Signaling socket for session %s closed: %s", session_id, exc)
        finally:
            if ctx.status == WebRTCSessionStatus.CONNECTED:
                await self.close_session(session_id)
            elif ctx.status in (WebRTCSessionStatus.REQUESTED, WebRTCSessionStatus.SIGNALING, WebRTCSessionStatus.CONNECTING):
                await self.fail_session(session_id, reason="Signaling channel disconnected before stream started.")

    # ── Teardown & Fail Handlers ─────────────────────────────────────────────

    async def close_session(self, session_id: str) -> SessionStopResponse:
        """Closes an active WebRTC session cleanly and releases all resources."""
        ctx = self._sessions.get(session_id)
        if not ctx:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")

        now = datetime.now(timezone.utc)
        ctx.status = WebRTCSessionStatus.ENDED
        ctx.ended_at = now

        duration: float | None = None
        if ctx.started_at:
            duration = (now - ctx.started_at).total_seconds()

        # Cancel timeout task
        if ctx.timeout_task and not ctx.timeout_task.done():
            ctx.timeout_task.cancel()

        # Close PeerConnection & stop media tracks
        if ctx.pc:
            try:
                await ctx.pc.close()
            except Exception as exc:
                logger.warning("Error closing RTCPeerConnection for %s: %s", session_id, exc)
            ctx.pc = None

        for track in ctx.tracks:
            if hasattr(track, "stop"):
                try:
                    track.stop()
                except Exception:
                    pass
        ctx.tracks = []

        # Close signaling WebSocket if open
        if ctx.signaling_ws:
            try:
                await ctx.signaling_ws.send_json(
                    SignalingMessage(
                        type="session_ended",
                        session_id=session_id,
                    ).model_dump()
                )
                await ctx.signaling_ws.close()
            except Exception:
                pass
            ctx.signaling_ws = None

        # Update DB
        await self._update_db_status(session_id, WebRTCSessionStatus.ENDED, ended_at=now)

        # Publish webrtc.session_ended event to RabbitMQ
        await publish_event(
            event_type="webrtc.session_ended",
            payload=WebRTCSessionEndedPayload(
                session_id=session_id,
                node_id=ctx.node_id,
                incident_id=ctx.incident_id,
                duration_seconds=duration,
                timestamp=now,
            ).model_dump(mode="json"),
            incident_id=ctx.incident_id,
        )

        logger.info("WebRTC session %s closed cleanly (duration=%.1fs)", session_id, duration or 0)
        return SessionStopResponse(
            session_id=session_id,
            status=WebRTCSessionStatus.ENDED.value,
            duration_seconds=duration,
        )

    async def fail_session(self, session_id: str, reason: str = "Unknown error") -> None:
        """Marks a session as FAILED and cleans up resources."""
        ctx = self._sessions.get(session_id)
        if not ctx:
            return

        now = datetime.now(timezone.utc)
        ctx.status = WebRTCSessionStatus.FAILED
        ctx.ended_at = now
        ctx.error_message = reason

        if ctx.timeout_task and not ctx.timeout_task.done():
            ctx.timeout_task.cancel()

        if ctx.pc:
            try:
                await ctx.pc.close()
            except Exception:
                pass
            ctx.pc = None

        for track in ctx.tracks:
            if hasattr(track, "stop"):
                try:
                    track.stop()
                except Exception:
                    pass
        ctx.tracks = []

        if ctx.signaling_ws:
            try:
                await ctx.signaling_ws.send_json(
                    SignalingMessage(
                        type="error",
                        session_id=session_id,
                        error=reason,
                    ).model_dump()
                )
                await ctx.signaling_ws.close(code=1011, reason=reason[:100])
            except Exception:
                pass
            ctx.signaling_ws = None

        await self._update_db_status(
            session_id,
            WebRTCSessionStatus.FAILED,
            ended_at=now,
            error_message=reason,
        )

        await publish_event(
            event_type="webrtc.session_failed",
            payload=WebRTCSessionFailedPayload(
                session_id=session_id,
                node_id=ctx.node_id,
                incident_id=ctx.incident_id,
                reason=reason,
                timestamp=now,
            ).model_dump(mode="json"),
            incident_id=ctx.incident_id,
        )
        logger.warning("WebRTC session %s failed: %s", session_id, reason)

    async def get_session(self, session_id: str) -> SessionDetailResponse:
        """Retrieves session details from memory or database."""
        ctx = self._sessions.get(session_id)
        if ctx:
            return SessionDetailResponse(
                session_id=ctx.session_id,
                incident_id=ctx.incident_id,
                requester_id=ctx.requester_id,
                source_node_id=ctx.node_id,
                status=ctx.status.value,
                has_video=ctx.has_video,
                has_audio=ctx.has_audio,
                created_at=ctx.created_at,
                started_at=ctx.started_at,
                ended_at=ctx.ended_at,
                error_message=ctx.error_message,
            )

        # Fallback to DB
        if async_session_factory is not None:
            async with async_session_factory() as session:
                stmt = select(WebRTCSession).where(WebRTCSession.session_id == session_id)
                res = await session.execute(stmt)
                rec = res.scalar_one_or_none()
                if rec:
                    return SessionDetailResponse(
                        session_id=rec.session_id,
                        incident_id=rec.incident_id,
                        requester_id=rec.requester_id,
                        source_node_id=rec.source_node_id,
                        status=rec.status.value,
                        has_video=rec.has_video,
                        has_audio=rec.has_audio,
                        created_at=rec.created_at,
                        started_at=rec.started_at,
                        ended_at=rec.ended_at,
                        error_message=rec.error_message,
                    )

        raise SessionNotFoundError(f"Session '{session_id}' not found.")

    async def list_sessions(
        self,
        node_id: str | None = None,
        incident_id: str | None = None,
        limit: int = 50,
    ) -> list[SessionDetailResponse]:
        """Lists active and past sessions from the database."""
        if async_session_factory is None:
            return []

        async with async_session_factory() as session:
            stmt = select(WebRTCSession)
            if node_id:
                stmt = stmt.where(WebRTCSession.source_node_id == node_id)
            if incident_id:
                stmt = stmt.where(WebRTCSession.incident_id == incident_id)
            stmt = stmt.order_by(WebRTCSession.created_at.desc()).limit(limit)
            res = await session.execute(stmt)
            records = res.scalars().all()

            return [
                SessionDetailResponse(
                    session_id=r.session_id,
                    incident_id=r.incident_id,
                    requester_id=r.requester_id,
                    source_node_id=r.source_node_id,
                    status=r.status.value,
                    has_video=r.has_video,
                    has_audio=r.has_audio,
                    created_at=r.created_at,
                    started_at=r.started_at,
                    ended_at=r.ended_at,
                    error_message=r.error_message,
                )
                for r in records
            ]

    async def _update_db_status(
        self,
        session_id: str,
        status: WebRTCSessionStatus,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        """Helper updating status in database."""
        if async_session_factory is None:
            return
        try:
            async with async_session_factory() as session:
                vals: dict[str, Any] = {"status": status}
                if started_at is not None:
                    vals["started_at"] = started_at
                if ended_at is not None:
                    vals["ended_at"] = ended_at
                if error_message is not None:
                    vals["error_message"] = error_message

                stmt = (
                    update(WebRTCSession)
                    .where(WebRTCSession.session_id == session_id)
                    .values(**vals)
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.warning("Could not update WebRTCSession DB status for %s: %s", session_id, exc)

    async def close_all(self) -> None:
        """Shutdown hook closing all active peer connections."""
        active_ids = list(self._sessions.keys())
        for session_id in active_ids:
            try:
                await self.close_session(session_id)
            except Exception:
                pass


webrtc_manager = WebRTCManager()
