from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..unit3 import unit3_state

router = APIRouter(prefix="/api/v1/unit3", tags=["unit-3-synchronization"])


class TickRequest(BaseModel):
    node_id: str | None = None
    received_clock: int | None = Field(default=None, ge=0)


class BeaconRequest(BaseModel):
    node_id: str


class SyncRequest(BaseModel):
    node_id: str
    reference_time_ms: float
    round_trip_ms: float = Field(ge=0)


class ElectionRequest(BaseModel):
    failed_node_id: str | None = None


class LockRequest(BaseModel):
    node_id: str
    resource_id: str = Field(min_length=1, max_length=200)


class ReleaseRequest(BaseModel):
    node_id: str


@router.get("/state")
async def get_state() -> dict[str, Any]:
    return unit3_state.report()


@router.post("/reset")
async def reset_state() -> dict[str, str]:
    unit3_state.reset()
    return {"status": "reset"}


@router.post("/clock/tick")
async def tick_clock(payload: TickRequest) -> dict[str, int]:
    return {"lamport_clock": unit3_state.tick(payload.node_id, payload.received_clock)}


@router.post("/beacon")
async def send_beacon(payload: BeaconRequest) -> dict[str, Any]:
    try:
        return unit3_state.beacon(payload.node_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown node '{exc.args[0]}'") from exc


@router.post("/clock/synchronize")
async def synchronize_clock(payload: SyncRequest) -> dict[str, Any]:
    try:
        return unit3_state.synchronize(
            payload.node_id, payload.reference_time_ms, payload.round_trip_ms
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown node '{exc.args[0]}'") from exc


@router.post("/election")
async def run_election(payload: ElectionRequest) -> dict[str, Any]:
    return unit3_state.elect(payload.failed_node_id)


@router.post("/lock/request")
async def request_lock(payload: LockRequest) -> dict[str, Any]:
    try:
        return unit3_state.request_lock(payload.node_id, payload.resource_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/lock/release")
async def release_lock(payload: ReleaseRequest) -> dict[str, Any]:
    try:
        return unit3_state.release_lock(payload.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/snapshot")
async def capture_snapshot() -> dict[str, Any]:
    return unit3_state.snapshot()
