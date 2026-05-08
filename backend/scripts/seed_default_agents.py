"""Seed the agents catalog with the default agent (emma_general) + 3 starters.

Idempotent: re-running on existing slugs only flips is_seed / is_active
flags; persona content authored by the admin is preserved. After
inserting/updating each row, the persona is pushed to Langfuse via the
emma-agent-service internal endpoint so admin-facing CRUD and seed
remain consistent.

Usage:
    cd backend && python scripts/seed_default_agents.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from sqlalchemy import select

from app.db.async_database import AsyncSessionLocal
from app.db.agent_models import Agent
from app.db.enums import ModelRole
from app.db.models import User
from app.services.langfuse.persona import LangfusePersonaAdapter


SEEDS: list[dict[str, Any]] = [
    {
        "name": "Emma General",
        "slug": "emma_general",
        "description": "Asistente general por defecto. Sin scope, persona neutra.",
        "icon": "IconRobot",
        "color": "blue",
        "persona": {
            "style": "concise",
            "language": "es",
            "instructions": "Eres Emma, asistente general de NouxCubeIA.",
        },
        "scope": {},
        "is_active": True,
        "is_seed": True,
        "model_role": ModelRole.CHAT,
        "temperature": 0.5,
    },
    {
        "name": "Contabilidad",
        "slug": "contabilidad",
        "description": "Análisis de facturas, pagos y conciliaciones.",
        "icon": "IconReceipt",
        "color": "green",
        "persona": {
            "style": "concise",
            "language": "es",
            "instructions": (
                "Eres el asistente de Contabilidad. Especialízate en facturas, "
                "pagos y conciliaciones. Cita siempre la factura origen."
            ),
        },
        "scope": {"semantic_types": ["factura", "pago"]},
        "is_active": False,
        "model_role": ModelRole.CHAT,
        "temperature": 0.5,
    },
    {
        "name": "Ventas",
        "slug": "ventas",
        "description": "Análisis de pipeline, leads y oportunidades.",
        "icon": "IconChartBar",
        "color": "orange",
        "persona": {
            "style": "concise",
            "language": "es",
            "instructions": "Eres el asistente de Ventas. Analiza pipeline, leads y oportunidades.",
        },
        "scope": {"semantic_types": ["contrato", "propuesta"]},
        "is_active": False,
        "model_role": ModelRole.CHAT,
        "temperature": 0.5,
    },
    {
        "name": "Legal",
        "slug": "legal",
        "description": "Contratos, cumplimiento normativo, jurisprudencia.",
        "icon": "IconScale",
        "color": "purple",
        "persona": {
            "style": "detailed",
            "language": "es",
            "instructions": (
                "Eres el asistente Legal. Cita siempre artículos y referencias normativas."
            ),
        },
        "scope": {"semantic_types": ["contrato", "sentencia"]},
        "is_active": False,
        "model_role": ModelRole.CHAT,
        "temperature": 0.5,
    },
]


async def main() -> None:
    adapter = LangfusePersonaAdapter()
    async with AsyncSessionLocal() as db:
        owner_q = await db.execute(select(User).where(User.is_superuser.is_(True)).limit(1))
        owner = owner_q.scalar_one_or_none()
        if owner is None:
            owner_q = await db.execute(select(User).limit(1))
            owner = owner_q.scalar_one_or_none()
        if owner is None:
            print("ERROR: no users in DB; create one first.", file=sys.stderr)
            sys.exit(1)
        print(f"Seeding agents owned by {owner.email}")

        for seed in SEEDS:
            existing_q = await db.execute(select(Agent).where(Agent.slug == seed["slug"]))
            existing = existing_q.scalar_one_or_none()
            if existing is None:
                agent = Agent(
                    id=uuid.uuid4(),
                    name=seed["name"],
                    slug=seed["slug"],
                    description=seed["description"],
                    icon=seed["icon"],
                    color=seed["color"],
                    persona=seed["persona"],
                    scope=seed["scope"],
                    is_active=seed["is_active"],
                    is_seed=seed.get("is_seed", False),
                    model_role=seed["model_role"],
                    temperature=seed["temperature"],
                    owner_id=owner.id,
                )
                db.add(agent)
                print(f"  + INSERT {seed['slug']}")
            else:
                existing.is_seed = seed.get("is_seed", existing.is_seed)
                if seed.get("is_seed"):
                    existing.is_active = True  # invariant
                print(f"  ~ UPDATE flags {seed['slug']}")

            try:
                await adapter.push_persona(
                    slug=seed["slug"],
                    instructions=seed["persona"]["instructions"],
                )
                print(f"    ↳ Langfuse push ok")
            except Exception as exc:  # noqa: BLE001
                print(f"    ↳ Langfuse push FAILED: {exc}")

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
