from fastapi import APIRouter, HTTPException, status

from ..config import settings
from ..database import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"service": settings.app_name, "status": "healthy"}


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
