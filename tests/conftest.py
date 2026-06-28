from __future__ import annotations

import asyncio
import sys
from pathlib import Path


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]

for relative in ("services/platform", "services/mcp-tools"):
    path = str(ROOT / relative)
    if path not in sys.path:
        sys.path.insert(0, path)
