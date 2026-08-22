import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "node"))

from app.database import async_session_factory  # noqa: E402
from app.models.node import NodeType  # noqa: E402
from app.schemas.node import NodeCreate  # noqa: E402
from app.services.node_registry import create_node, get_node  # noqa: E402


SEED_NODES = (
    NodeCreate(node_id="CCTV-A", node_name="CCTV Camera A", node_type=NodeType.EVIDENCE, host="localhost", port=8001, description="Development evidence node"),
    NodeCreate(node_id="CCTV-B", node_name="CCTV Camera B", node_type=NodeType.EVIDENCE, host="localhost", port=8002, description="Development evidence node"),
    NodeCreate(node_id="SECURITY-A", node_name="Security Node A", node_type=NodeType.SECURITY, host="localhost", port=8003, description="Development security node"),
)


async def seed() -> None:
    if async_session_factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with async_session_factory() as session:
        for payload in SEED_NODES:
            if await get_node(session, payload.node_id) is None:
                await create_node(session, payload)
                print(f"Registered {payload.node_id}")
            else:
                print(f"Skipped existing node {payload.node_id}")


if __name__ == "__main__":
    asyncio.run(seed())
