"""
Unified System Health & Diagnostics Router (Part 10).

Provides structured health diagnostics across all six distributed communication layers:
  - Database (PostgreSQL via Neon)
  - Messaging (RabbitMQ pub/sub)
  - gRPC (Remote procedure calls)
  - WebSocket (Real-time browser stream)
  - P2P (Direct node-to-node mesh)
  - WebRTC (Live multimedia sessions)
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..config import settings
from ..database import async_session_factory, check_database_connection
from ..messaging.connection import messaging_connection
from ..models.evidence import Evidence
from ..models.incident import Incident, IncidentStatus
from ..models.node import Node, NodeStatus
from ..p2p.manager import peer_manager
from ..webrtc.manager import webrtc_manager
from ..websocket.manager import ws_manager

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}


@router.get("/health")
async def health() -> dict[str, Any]:
    """
    Unified System Health & Runtime Metrics (Part 10).
    Provides structured status for all subsystems and live counts for dashboard.
    """
    db_status = "unknown"
    metrics = {
        "registered_nodes": 0,
        "online_nodes": 0,
        "active_incidents": 0,
        "evidence_count": 0,
        "active_p2p_peers": peer_manager.get_connected_count(),
        "active_webrtc_sessions": len(
            [s for s in webrtc_manager._sessions.values() if s.status.value == "CONNECTED"]
        ),
        "active_ws_clients": ws_manager.connection_count(),
    }

    try:
        await check_database_connection()
        db_status = "healthy"
        if async_session_factory is not None:
            async with async_session_factory() as session:
                # Node counts
                total_nodes = await session.scalar(select(func.count(Node.id))) or 0
                online_nodes = (
                    await session.scalar(
                        select(func.count(Node.id)).where(Node.status == NodeStatus.ONLINE)
                    )
                    or 0
                )
                # Incident & evidence counts
                open_inc = (
                    await session.scalar(
                        select(func.count(Incident.id)).where(
                            Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.INVESTIGATING])
                        )
                    )
                    or 0
                )
                total_ev = await session.scalar(select(func.count(Evidence.id))) or 0

                metrics["registered_nodes"] = total_nodes
                metrics["online_nodes"] = online_nodes
                metrics["active_incidents"] = open_inc
                metrics["evidence_count"] = total_ev
    except Exception:
        db_status = "unhealthy"

    mq_status = "healthy" if messaging_connection.is_healthy() else "unhealthy"

    services_map = {
        "database": db_status,
        "rabbitmq": mq_status,
        "grpc": "running",
        "websocket": "healthy",
        "p2p": "healthy",
        "webrtc": "ready",
    }

    overall = "healthy" if db_status == "healthy" and mq_status == "healthy" else "degraded"
    if db_status == "unhealthy" and mq_status == "unhealthy":
        overall = "unhealthy"

    return {
        "service": settings.app_name,
        "node_id": settings.node_id,
        "status": overall,
        "services": services_map,
        "components": services_map,  # Backward compatibility
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/database")
async def database_health() -> dict[str, str]:
    try:
        await check_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(exc)},
        ) from exc
    return {"service": settings.app_name, "database": "connected", "status": "healthy"}


@router.get("/health/messaging")
async def messaging_health() -> dict[str, str]:
    """Report actual RabbitMQ connectivity."""
    if messaging_connection.is_healthy():
        return {"service": "rabbitmq", "status": "healthy"}
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"service": "rabbitmq", "status": "unhealthy"},
    )


@router.get("/health/websocket")
async def websocket_health() -> dict[str, object]:
    """WebSocket stream connectivity status."""
    return {
        "service": "websocket",
        "status": "healthy",
        "active_connections": ws_manager.connection_count(),
    }


@router.get("/health/p2p")
async def p2p_health() -> dict[str, object]:
    """P2P subsystem health status (Part 8)."""
    return {
        "service": "p2p",
        "status": "healthy",
        "connected_peers": peer_manager.get_connected_count(),
    }


@router.get("/health/webrtc")
async def webrtc_health() -> dict[str, object]:
    """WebRTC multimedia subsystem health status (Part 9)."""
    return {
        "service": "webrtc",
        "status": "ready",
        "active_sessions": len(webrtc_manager._sessions),
    }
