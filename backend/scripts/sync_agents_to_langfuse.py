"""Re-push every active agent's persona to Langfuse (disaster recovery).

Idempotent: each call creates a new Langfuse version with label
``production`` for ``agent_<slug>_persona``. Safe to run after a
Langfuse restore or to seed a fresh environment.

Usage:
    cd backend && python scripts/sync_agents_to_langfuse.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.async_database import AsyncSessionLocal
from app.db.agent_models import Agent
from app.services.langfuse.persona import LangfusePersonaAdapter


async def main() -> None:
    adapter = LangfusePersonaAdapter()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Agent).where(Agent.is_active.is_(True)))).scalars().all()
        if not rows:
            print("No active agents found.")
            return
        for row in rows:
            instructions = (row.persona or {}).get("instructions", "")
            try:
                await adapter.push_persona(slug=row.slug, instructions=instructions)
                print(f"  + agent_{row.slug}_persona ({len(instructions)} chars)")
            except Exception as exc:  # noqa: BLE001
                print(f"  ! agent_{row.slug}_persona FAILED: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
