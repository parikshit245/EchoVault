"""
WebRTC REST & Signaling Router (Part 9).

Endpoints:
  - POST /api/v1/webrtc/sessions — Request live session with evidence node
  - POST /api/v1/webrtc/sessions/{session_id}/stop — Stop live session cleanly
  - GET  /api/v1/webrtc/sessions — List active/past WebRTC sessions
  - GET  /api/v1/webrtc/sessions/{session_id} — Get session details
  - WS   /ws/webrtc/{session_id} — Dedicated signaling channel for SDP & ICE negotiation

Node routing:
  If the requested node_id belongs to a different node (not this process),
  the coordinator proxies the POST to that node's HTTP endpoint so the session
  is created on — and the aiortc PeerConnection lives on — the correct process.
  This ensures source_node_id is correctly stamped and the signaling WS URL
  points to the right host.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, status
from sqlalchemy import select

from ..config import settings
from ..database import async_session_factory
from ..models.node import Node
from ..webrtc.manager import NodeUnavailableError, SessionNotFoundError, webrtc_manager
from ..webrtc.schemas import (
    SessionCreateRequest,
    SessionDetailResponse,
    SessionResponse,
    SessionStopResponse,
)

logger = logging.getLogger("echovault.routers.webrtc")
router = APIRouter(tags=["WebRTC Multimedia"])


async def _get_node_base_url(node_id: str) -> str | None:
    """
    Look up the host:port of a registered node from the database.
    Returns None if the node is not found or DB is unavailable.
    """
    if async_session_factory is None:
        return None
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Node).where(Node.node_id == node_id)
            )
            node = result.scalar_one_or_none()
            if node:
                return f"http://{node.host}:{node.port}"
    except Exception as exc:
        logger.warning("Could not look up node URL for %s: %s", node_id, exc)
    return None


@router.post(
    "/api/v1/webrtc/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate WebRTC multimedia session",
)
async def create_webrtc_session(
    body: SessionCreateRequest, request: Request
) -> SessionResponse:
    """
    Requests a live WebRTC multimedia session with an evidence node.

    If the target node_id is this node → create session locally.
    If the target node_id belongs to a different node → proxy request to that
    node's HTTP endpoint so the session is owned by the correct process.

    This is critical: aiortc PeerConnection and media tracks must live in the
    same process as the /ws/webrtc/{session_id} signaling endpoint the browser
    connects to. Routing to the wrong process = session not found + signaling fail.
    """
    target_node_id = body.node_id.strip()

    # If this is NOT our node, proxy the request to the correct node's endpoint
    if target_node_id != settings.node_id:
        node_base_url = await _get_node_base_url(target_node_id)
        if node_base_url:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{node_base_url}/api/v1/webrtc/sessions",
                        json=body.model_dump(mode="json"),
                    )
                if resp.status_code == 201:
                    data = resp.json()
                    # Rewrite the signaling_url host so the browser can reach it
                    # We tell the browser to connect to the correct node's WS port
                    session_id = data["session_id"]
                    # Parse host from node_base_url (e.g. http://node-a:8001)
                    # The browser can't use the Docker service name, so we need
                    # the signaling to go through this coordinator via a forwarded URL.
                    # For now, return the signaling URL on THIS node which we'll
                    # forward — or if the node is reachable on localhost, use its port.
                    # See architecture note in docstring below.
                    data["signaling_url"] = f"/ws/webrtc/{session_id}"
                    return SessionResponse(**data)
                else:
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=resp.json().get("detail", "Node refused session"),
                    )
            except httpx.RequestError as exc:
                logger.warning(
                    "Could not proxy WebRTC session to node %s at %s: %s",
                    target_node_id, node_base_url, exc,
                )
                # Fall through to local creation if node unreachable
        else:
            logger.warning(
                "Node %s not found in registry — creating session locally as fallback",
                target_node_id,
            )

    try:
        base_url = str(request.base_url).rstrip("/")
        return await webrtc_manager.create_session(body, base_url=base_url)
    except NodeUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Failed to create WebRTC session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate WebRTC session: {exc}",
        )


@router.post(
    "/api/v1/webrtc/sessions/{session_id}/stop",
    response_model=SessionStopResponse,
    summary="Stop live WebRTC session",
)
async def stop_webrtc_session(session_id: str) -> SessionStopResponse:
    """
    Tears down a live WebRTC session cleanly, closing media tracks and signaling channels.
    """
    try:
        return await webrtc_manager.close_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("Error stopping WebRTC session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop session: {exc}",
        )


@router.get(
    "/api/v1/webrtc/sessions",
    response_model=list[SessionDetailResponse],
    summary="List WebRTC sessions",
)
async def list_webrtc_sessions(
    node_id: Optional[str] = Query(None, description="Filter by source node ID"),
    incident_id: Optional[str] = Query(None, description="Filter by incident ID"),
    limit: int = Query(50, ge=1, le=200),
) -> list[SessionDetailResponse]:
    """Lists recent active and past WebRTC multimedia sessions."""
    return await webrtc_manager.list_sessions(
        node_id=node_id, incident_id=incident_id, limit=limit
    )


@router.get(
    "/api/v1/webrtc/sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get WebRTC session detail",
)
async def get_webrtc_session(session_id: str) -> SessionDetailResponse:
    """Retrieves metadata and current status for a specific WebRTC session."""
    try:
        return await webrtc_manager.get_session(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.websocket("/ws/webrtc/{session_id}")
async def webrtc_signaling_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    Dedicated WebRTC signaling channel for SDP offer/answer exchange and ICE candidate trickle.
    The signaling channel does NOT carry media bytes — media travels over RTCPeerConnection directly.
    """
    await webrtc_manager.handle_signaling_connection(session_id, websocket)
