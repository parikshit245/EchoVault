from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..database import check_database_connection
from ..messaging.connection import messaging_connection
from ..p2p.manager import peer_manager
from ..websocket.manager import ws_manager

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}


@router.get("/health")
async def health() -> dict[str, str | dict]:
    """
    Overall health summary.

    Reports:
      - database connectivity
      - RabbitMQ messaging connectivity
      - gRPC server (always running if application is up)
      - WebSocket active connections (browser streams)
      - P2P direct communication subsystem
    """
    db_status = "unknown"
    try:
        await check_database_connection()
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"

    mq_status = "healthy" if messaging_connection.is_healthy() else "unhealthy"

    return {
        "service": settings.app_name,
        "node_id": settings.node_id,
        "status": "healthy" if db_status == "healthy" else "degraded",
        "components": {
            "database": db_status,
            "rabbitmq": mq_status,
            "grpc": "running",
            "websocket": "healthy",
            "p2p": "healthy",
        },
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
    """
    Report actual RabbitMQ connectivity.

    Returns 200 when healthy, 503 when RabbitMQ is unreachable.
    This endpoint never fakes the status — it reflects the live connection state.
    """
    if messaging_connection.is_healthy():
        return {"service": "rabbitmq", "status": "healthy"}
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"service": "rabbitmq", "status": "unhealthy"},
    )


@router.get("/health/websocket")
async def websocket_health() -> dict[str, object]:
    """
    WebSocket connectivity status.

    Always returns 200 — having zero clients is not an error.
    Reports the count of currently connected browser clients.
    """
    return {
        "service": "websocket",
        "status": "healthy",
        "active_connections": ws_manager.connection_count(),
    }


@router.get("/health/p2p")
async def p2p_health() -> dict[str, object]:
    """
    P2P subsystem health status (Part 8).

    Always returns 200 — having zero connected peers is normal.
    Reports the count of currently active direct P2P connections.
    """
    return {
        "service": "p2p",
        "status": "healthy",
        "connected_peers": peer_manager.get_connected_count(),
    }
