from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models.node import Node
from ..services.remote_rpc import RemoteNodeUnavailableError, RemoteNotFoundError, remote_evidence, remote_incident_evidence, remote_status

router = APIRouter(prefix="/api/v1/remote", tags=["remote RPC"])


async def target_node(node_id: str, session: AsyncSession) -> Node:
    result = await session.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Target node not found in registry")
    return node


def rpc_error(exc: RemoteNodeUnavailableError) -> HTTPException:
    return HTTPException(status_code=503, detail="Target node is unavailable")


@router.get("/nodes/{node_id}/status", summary="Get a remote node status through gRPC")
async def get_remote_status(node_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    node = await target_node(node_id, session)
    try:
        response = await remote_status(node)
    except RemoteNodeUnavailableError as exc:
        raise rpc_error(exc) from exc
    return {"node_id": response.node_id, "status": response.status, "timestamp": response.timestamp.ToDatetime().isoformat()}


@router.get("/nodes/{node_id}/evidence/{evidence_id}", summary="Get remote evidence metadata through gRPC")
async def get_remote_evidence(node_id: str, evidence_id: str, session: AsyncSession = Depends(get_db_session)) -> dict:
    node = await target_node(node_id, session)
    try:
        return await remote_evidence(node, evidence_id)
    except RemoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Remote evidence not found") from exc
    except RemoteNodeUnavailableError as exc:
        raise rpc_error(exc) from exc


@router.get("/nodes/{node_id}/incidents/{incident_id}/evidence", summary="Get remote incident evidence through gRPC")
async def get_remote_incident_evidence(node_id: str, incident_id: str, session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    node = await target_node(node_id, session)
    try:
        return await remote_incident_evidence(node, incident_id)
    except RemoteNodeUnavailableError as exc:
        raise rpc_error(exc) from exc
