"""
EchoVault FA-1 Demo Seeder Script (Part 10).

Idempotently sets up the complete FA-1 demonstration scenario:
  - 4 Distributed Nodes: CCTV-A, CCTV-B, SECURITY-A, MOBILE-A
  - 1 Shared Logical Incident: INC-000001 ("Restricted Area Intrusion", HIGH, OPEN)
  - 4 Participating node associations
  - 4 Node-owned evidence items belonging to each node
"""

import asyncio
import sys
from pathlib import Path

# Add services/node to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from app.database import async_session_factory
from app.services.demo_seeder import DEMO_EVIDENCE, DEMO_NODES, seed_demo_data


async def main() -> None:
    if async_session_factory is None:
        print("[ERROR] DATABASE_URL not configured.")
        return

    print("==================================================")
    print(" EchoVault FA-1 Demo Seeder")
    print("==================================================")
    async with async_session_factory() as session:
        counts = await seed_demo_data(session)
        print(f"[OK] Nodes seeded:          {len(DEMO_NODES)}")
        print(f"[OK] Incident seeded:       INC-000001 (Restricted Area Intrusion)")
        print(f"[OK] Evidence items seeded: {len(DEMO_EVIDENCE)}")
        print(f"[OK] New records inserted:  {counts}")
    print("==================================================")
    print("[OK] EchoVault FA-1 demonstration environment is ready!")


if __name__ == "__main__":
    asyncio.run(main())
