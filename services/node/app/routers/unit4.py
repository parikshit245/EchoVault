from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..unit4 import replication_catalog

router = APIRouter(prefix="/api/v1/unit4", tags=["unit-4-emerging-paradigms"])


class ReplicationRequest(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=80)
    owner_node_id: str = Field(min_length=1, max_length=100)
    target_node_id: str = Field(min_length=1, max_length=100)
    file_name: str | None = None
    file_size: int | None = Field(default=None, ge=0)
    checksum: str | None = None


@router.get("/state")
async def get_replication_state() -> dict[str, Any]:
    return replication_catalog.report()


@router.post("/reset")
async def reset_replication_state() -> dict[str, str]:
    replication_catalog.reset()
    return {"status": "reset"}


@router.post("/replication/request")
async def request_replication(payload: ReplicationRequest) -> dict[str, Any]:
    try:
        return replication_catalog.request_replication(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/replication/{evidence_id}")
async def get_replication(evidence_id: str) -> dict[str, Any]:
    record = replication_catalog.get(evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence has no replica")
    return record
