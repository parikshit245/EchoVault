from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..models.node import NodeStatus, NodeType
from ..schemas.node import NodeCreate, NodeHeartbeatResponse, NodeResponse, NodeUpdate
from ..services.node_registry import (
    DuplicateNodeError,
    create_node,
    deactivate_node,
    get_node,
    heartbeat,
    list_nodes,
)

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])


def missing_node() -> HTTPException:
    return HTTPException(status_code=404, detail="Node not found")


@router.post("", response_model=NodeResponse, status_code=status.HTTP_201_CREATED, summary="Register a node")
async def register_node(payload: NodeCreate, session: AsyncSession = Depends(get_db_session)) -> NodeResponse:
    try:
        return await create_node(session, payload)
    except DuplicateNodeError as exc:
        raise HTTPException(status_code=409, detail=f"Node '{exc.args[0]}' already exists") from exc


@router.get("", response_model=list[NodeResponse], summary="Discover registered nodes")
async def get_nodes(
    node_type: NodeType | None = Query(default=None),
    node_status: NodeStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
) -> list[NodeResponse]:
    return await list_nodes(session, node_type.value if node_type else None, node_status)


@router.get("/{node_id}", response_model=NodeResponse, summary="Get a registered node")
async def get_registered_node(node_id: str, session: AsyncSession = Depends(get_db_session)) -> NodeResponse:
    node = await get_node(session, node_id)
    if node is None:
        raise missing_node()
    return node


@router.patch("/{node_id}", response_model=NodeResponse, summary="Update node metadata or status")
async def update_registered_node(
    node_id: str,
    payload: NodeUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> NodeResponse:
    node = await get_node(session, node_id)
    if node is None:
        raise missing_node()
    from ..services.node_registry import update_node
    return await update_node(session, node, payload)


@router.post("/{node_id}/heartbeat", response_model=NodeHeartbeatResponse, summary="Record node liveness")
async def node_heartbeat(node_id: str, session: AsyncSession = Depends(get_db_session)) -> NodeHeartbeatResponse:
    node = await get_node(session, node_id)
    if node is None:
        raise missing_node()
    node = await heartbeat(session, node)
    return NodeHeartbeatResponse(node_id=node.node_id, status=node.status, last_seen_at=node.last_seen_at)


@router.delete("/{node_id}", response_model=NodeResponse, summary="Deactivate a node")
async def delete_node(node_id: str, session: AsyncSession = Depends(get_db_session)) -> NodeResponse:
    node = await get_node(session, node_id)
    if node is None:
        raise missing_node()
    return await deactivate_node(session, node)
