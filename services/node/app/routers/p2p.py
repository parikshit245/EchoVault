"""
P2P Router — Dedicated Peer WebSocket & Management API (Part 8).

Endpoints:
  - WS  /ws/peer                                          → Inbound Node-to-Node WebSocket
  - GET /api/v1/peers                                     → Discovered and active peers
  - POST /api/v1/peers/{node_id}/connect                  → Initiate direct P2P link
  - POST /api/v1/peers/{node_id}/disconnect               → Teardown direct P2P link
  - POST /api/v1/peers/{node_id}/ping                     → Measure direct RTT
  - POST /api/v1/peers/{node_id}/message                  → Send direct test message
  - POST /api/v1/peers/{node_id}/announce/evidence/{id}   → Direct evidence announcement
  - POST /api/v1/peers/{node_id}/announce/incident/{id}   → Direct incident announcement
  - GET  /api/v1/peers/messages                           → Audit log of received P2P messages
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db_session
from ..models.evidence import Evidence
from ..models.incident import Incident
from ..models.node import Node
from ..models.peer_message import PeerMessage, PeerMessageStatus, PeerMessageType
from ..p2p.manager import (
    PeerIdentityMismatchError,
    PeerNotConnectedError,
    peer_manager,
)
from ..p2p.peer import PeerConnectionState, PeerInfo
from ..p2p.protocol import (
    EvidenceAnnouncementPayload,
    IncidentAnnouncementPayload,
    P2PMessageEnvelope,
    PeerMessagePayload,
)

logger = logging.getLogger("echovault.routers.p2p")

router = APIRouter(tags=["p2p"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class DirectMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PingResponse(BaseModel):
    node_id: str
    rtt_ms: float
    status: str = "PONG"


class PeerMessageRecord(BaseModel):
    id: str
    message_id: str
    source_node_id: str
    target_node_id: str
    message_type: str
    received_at: str
    processed_at: str | None
    status: str
    error_message: str | None
    payload: dict[str, Any] | None


class PeerStatusResponse(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    host: str
    port: int
    p2p_host: str
    p2p_port: int
    connection_state: PeerConnectionState
    connected_at: str | None = None
    last_seen_at: str | None = None
    rtt_ms: float | None = None
    reconnect_attempts: int = 0
    is_outbound: bool = False


# ── Inbound WebSocket Endpoint ────────────────────────────────────────────────


@router.websocket("/ws/peer")
async def websocket_peer_endpoint(websocket: WebSocket) -> None:
    """
    Dedicated Node-to-Node WebSocket endpoint.
    Strictly separated from /ws/events (browser stream) and RabbitMQ.
    """
    await peer_manager.handle_inbound_connection(websocket)


# ── Peer Management REST API ──────────────────────────────────────────────────


@router.get("/api/v1/peers", response_model=list[PeerStatusResponse])
async def list_peers(
    session: AsyncSession = Depends(get_db_session),
) -> list[PeerStatusResponse]:
    """
    List all discovered nodes from the Node Registry with their current
    direct P2P connection status.
    """
    # 1. Fetch registered nodes from DB
    res = await session.execute(select(Node).order_by(Node.node_id))
    nodes = list(res.scalars().all())

    # 2. Combine with runtime PeerManager state
    result: list[PeerStatusResponse] = []
    for node in nodes:
        if node.node_id == settings.node_id:
            continue  # Don't list self as a peer

        peer_info = peer_manager.get_peer_info(node.node_id)
        effective_p2p_host = node.p2p_host or node.host
        effective_p2p_port = node.p2p_port or node.port

        if peer_info is not None:
            result.append(
                PeerStatusResponse(
                    node_id=node.node_id,
                    node_name=node.node_name,
                    node_type=node.node_type.value,
                    host=node.host,
                    port=node.port,
                    p2p_host=effective_p2p_host,
                    p2p_port=effective_p2p_port,
                    connection_state=peer_info.state,
                    connected_at=peer_info.connected_at.isoformat()
                    if peer_info.connected_at
                    else None,
                    last_seen_at=peer_info.last_seen_at.isoformat()
                    if peer_info.last_seen_at
                    else None,
                    rtt_ms=peer_info.rtt_ms,
                    reconnect_attempts=peer_info.reconnect_attempts,
                    is_outbound=peer_info.is_outbound,
                )
            )
        else:
            result.append(
                PeerStatusResponse(
                    node_id=node.node_id,
                    node_name=node.node_name,
                    node_type=node.node_type.value,
                    host=node.host,
                    port=node.port,
                    p2p_host=effective_p2p_host,
                    p2p_port=effective_p2p_port,
                    connection_state=PeerConnectionState.DISCONNECTED,
                )
            )

    return result


@router.post("/api/v1/peers/{node_id}/connect", response_model=PeerInfo)
async def connect_peer(
    node_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PeerInfo:
    """
    Look up target node in Node Registry and establish a direct P2P link
    with Handshake and Identity Verification.
    """
    res = await session.execute(select(Node).where(Node.node_id == node_id))
    target = res.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in registry")

    target_host = target.p2p_host or target.host
    target_port = target.p2p_port or target.port

    try:
        return await peer_manager.connect_to_peer(
            node_id,
            target_host,
            target_port,
        )
    except PeerIdentityMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to peer '{node_id}': {exc}") from exc


@router.post("/api/v1/peers/{node_id}/disconnect")
async def disconnect_peer(node_id: str) -> dict[str, str]:
    """Explicitly tear down direct P2P link to target node."""
    await peer_manager.disconnect_peer(node_id)
    return {"status": "disconnected", "node_id": node_id}


@router.post("/api/v1/peers/{node_id}/ping", response_model=PingResponse)
async def ping_peer_endpoint(node_id: str) -> PingResponse:
    """Send direct P2P PING to peer and return measured round-trip latency in ms."""
    try:
        rtt_ms = await peer_manager.ping_peer(node_id, timeout=5.0)
        return PingResponse(node_id=node_id, rtt_ms=rtt_ms, status="PONG")
    except PeerNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ping failed: {exc}") from exc


@router.post("/api/v1/peers/{node_id}/message")
async def send_direct_message(
    node_id: str,
    payload: DirectMessageRequest,
) -> dict[str, Any]:
    """Send a direct P2P message to target peer without intermediate broker."""
    msg_payload = PeerMessagePayload(
        text=payload.text,
        metadata=payload.metadata,
    )
    envelope = P2PMessageEnvelope(
        message_type=PeerMessageType.PEER_MESSAGE.value,
        source_node_id=settings.node_id,
        target_node_id=node_id,
        payload=msg_payload.model_dump(),
    )

    try:
        sent = await peer_manager.send_direct_message(node_id, envelope)
        if not sent:
            raise HTTPException(status_code=500, detail="Failed to transmit message to peer")
        return {
            "status": "sent",
            "message_id": envelope.message_id,
            "target_node_id": node_id,
            "direct": True,
        }
    except PeerNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/peers/{node_id}/announce/evidence/{evidence_id}")
async def announce_evidence(
    node_id: str,
    evidence_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Directly announce local evidence metadata to a target connected peer."""
    res = await session.execute(select(Evidence).where(Evidence.evidence_id == evidence_id))
    evidence = res.scalar_one_or_none()
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Evidence '{evidence_id}' not found")

    payload = EvidenceAnnouncementPayload(
        evidence_id=evidence.evidence_id,
        node_id=evidence.node_id,
        event_type=evidence.event_type,
        evidence_type=evidence.evidence_type.value,
        title=evidence.title,
        captured_at=evidence.captured_at.isoformat() if evidence.captured_at else None,
    )
    envelope = P2PMessageEnvelope(
        message_type=PeerMessageType.EVIDENCE_ANNOUNCEMENT.value,
        source_node_id=settings.node_id,
        target_node_id=node_id,
        payload=payload.model_dump(),
    )

    try:
        sent = await peer_manager.send_direct_message(node_id, envelope)
        if not sent:
            raise HTTPException(status_code=500, detail="Failed to transmit announcement to peer")
        return {
            "status": "announced",
            "message_id": envelope.message_id,
            "target_node_id": node_id,
            "evidence_id": evidence_id,
        }
    except PeerNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/peers/{node_id}/announce/incident/{incident_id}")
async def announce_incident(
    node_id: str,
    incident_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Directly announce local incident metadata to a target connected peer."""
    res = await session.execute(select(Incident).where(Incident.incident_id == incident_id))
    incident = res.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    payload = IncidentAnnouncementPayload(
        incident_id=incident.incident_id,
        title=incident.title,
        incident_type=incident.incident_type.value,
        severity=incident.severity.value,
        status=incident.status.value,
        source_node_id=incident.created_by_node_id,
        started_at=incident.started_at.isoformat() if incident.started_at else None,
    )
    envelope = P2PMessageEnvelope(
        message_type=PeerMessageType.INCIDENT_ANNOUNCEMENT.value,
        source_node_id=settings.node_id,
        target_node_id=node_id,
        payload=payload.model_dump(),
    )

    try:
        sent = await peer_manager.send_direct_message(node_id, envelope)
        if not sent:
            raise HTTPException(status_code=500, detail="Failed to transmit announcement to peer")
        return {
            "status": "announced",
            "message_id": envelope.message_id,
            "target_node_id": node_id,
            "incident_id": incident_id,
        }
    except PeerNotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/v1/peers/messages", response_model=list[PeerMessageRecord])
async def list_peer_messages(
    source_node_id: str | None = Query(default=None),
    message_type: str | None = Query(default=None),
    msg_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> list[PeerMessageRecord]:
    """Query the local received P2P message inbox with pagination and filters."""
    query = select(PeerMessage).order_by(desc(PeerMessage.received_at))

    if source_node_id:
        query = query.where(PeerMessage.source_node_id == source_node_id)
    if message_type:
        query = query.where(PeerMessage.message_type == message_type)
    if msg_status:
        try:
            enum_status = PeerMessageStatus(msg_status.upper())
            query = query.where(PeerMessage.status == enum_status)
        except ValueError:
            return []

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    res = await session.execute(query)
    records = res.scalars().all()

    return [
        PeerMessageRecord(
            id=str(r.id),
            message_id=r.message_id,
            source_node_id=r.source_node_id,
            target_node_id=r.target_node_id,
            message_type=r.message_type,
            received_at=r.received_at.isoformat(),
            processed_at=r.processed_at.isoformat() if r.processed_at else None,
            status=r.status.value,
            error_message=r.error_message,
            payload=r.payload,
        )
        for r in records
    ]
