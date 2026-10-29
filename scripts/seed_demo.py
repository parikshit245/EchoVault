"""
EchoVault FA-1 Demo Seeder Script (Root Wrapper).
"""

import asyncio
import sys
from pathlib import Path

# Add services/node to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "node"))

from scripts.seed_demo import main

if __name__ == "__main__":
    asyncio.run(main())
