"""
EchoVault Database Purge & Fresh Re-Seed Script.

Wipes all legacy/old test nodes and records, then freshly seeds:
  - 4 Clean Demo Nodes: CCTV-A, CCTV-B, SECURITY-A, MOBILE-A
  - 1 Incident: INC-000001
  - 4 Node-owned evidence items
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "node"))

from app.database import async_session_factory
from app.services.demo_seeder import DEMO_EVIDENCE, DEMO_NODES, clean_reset_demo_data


async def main() -> None:
    if async_session_factory is None:
        print("[ERROR] DATABASE_URL not configured.")
        return

    print("==================================================")
    print(" EchoVault Database Clean Reset")
    print("==================================================")
    async with async_session_factory() as session:
        counts = await clean_reset_demo_data(session)
        print(f"[OK] Legacy nodes & tables purged.")
        print(f"[OK] Fresh nodes seeded:     {len(DEMO_NODES)} (CCTV-A, CCTV-B, SECURITY-A, MOBILE-A)")
        print(f"[OK] Fresh incident seeded:  INC-000001 (Restricted Area Intrusion)")
        print(f"[OK] Fresh evidence seeded:  {len(DEMO_EVIDENCE)}")
        print(f"[OK] New record counts:      {counts}")
    print("==================================================")
    print("[OK] Database is clean and ready for evaluation!")


if __name__ == "__main__":
    asyncio.run(main())
