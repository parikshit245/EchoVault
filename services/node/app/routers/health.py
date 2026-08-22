from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..database import check_database_connection
from ..messaging.connection import messaging_connection

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
