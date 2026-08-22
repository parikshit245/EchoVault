from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.node import Node, NodeStatus
from ..schemas.node import NodeCreate, NodeUpdate


class DuplicateNodeError(Exception):
    pass


async def create_node(session: AsyncSession, payload: NodeCreate) -> Node:
    node = Node(**payload.model_dump())
    session.add(node)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateNodeError(payload.node_id) from exc
    await session.refresh(node)
    return node


async def list_nodes(
    session: AsyncSession,
    node_type: str | None = None,
    status: NodeStatus | None = None,
) -> list[Node]:
    query = select(Node).order_by(Node.node_id)
    if node_type is not None:
        query = query.where(Node.node_type == node_type)
    if status is not None:
        query = query.where(Node.status == status)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_node(session: AsyncSession, node_id: str) -> Node | None:
    result = await session.execute(select(Node).where(Node.node_id == node_id))
    return result.scalar_one_or_none()


async def update_node(session: AsyncSession, node: Node, payload: NodeUpdate) -> Node:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    await session.commit()
    await session.refresh(node)
    return node


async def heartbeat(session: AsyncSession, node: Node) -> Node:
    now = datetime.now(timezone.utc)
    node.status = NodeStatus.ONLINE
    node.last_seen_at = now
    node.updated_at = now
    await session.commit()
    await session.refresh(node)
    return node


async def deactivate_node(session: AsyncSession, node: Node) -> Node:
    node.status = NodeStatus.OFFLINE
    node.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(node)
    return node


async def register_self(session: AsyncSession) -> Node:
    from ..config import settings
    from ..models.node import NodeType

    payload = NodeCreate(
        node_id=settings.node_id,
        node_name=settings.node_name,
        node_type=NodeType(settings.node_type.upper()),
        host=settings.node_host,
        port=settings.port,
        grpc_host=settings.grpc_host,
        grpc_port=settings.grpc_port,
    )
    existing = await get_node(session, payload.node_id)
    if existing is not None:
        return await update_node(session, existing, NodeUpdate(
            node_name=payload.node_name,
            host=payload.host,
            port=payload.port,
            grpc_host=payload.grpc_host,
            grpc_port=payload.grpc_port,
        ))
    return await create_node(session, payload)
