from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db_session
from ..models.node import NodeType
from ..schemas.node import NodeResponse, NodeSelfResponse
from ..services.node_registry import register_self

router = APIRouter(prefix="/api/v1/node", tags=["node identity"])


@router.get("/self", response_model=NodeSelfResponse, summary="Get this service's configured identity")
async def get_self_identity() -> NodeSelfResponse:
    return NodeSelfResponse(
        node_id=settings.node_id,
        node_name=settings.node_name,
        node_type=NodeType(settings.node_type.upper()),
        host=settings.node_host,
        port=settings.port,
        grpc_host=settings.grpc_host,
        grpc_port=settings.grpc_port,
        p2p_host=settings.p2p_host,
        p2p_port=settings.p2p_port,
        supports_video=settings.supports_video,
        supports_audio=settings.supports_audio,
    )


@router.post("/self/register", response_model=NodeResponse, summary="Register this service in the node registry")
async def register_self_node(session: AsyncSession = Depends(get_db_session)) -> NodeResponse:
    return await register_self(session)
