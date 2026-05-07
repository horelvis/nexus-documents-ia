"""CRUD service for the agents catalog.

The service owns the DB session and the Langfuse persona adapter. CRUD
writes that change ``persona.instructions`` push the new content to
Langfuse on commit; if the push fails, the DB transaction is rolled
back so the two stores remain consistent.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import Agent
from app.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)


class LangfusePersonaPusher(Protocol):
    """Minimal interface the service depends on (allows test injection)."""

    async def push_persona(self, *, slug: str, instructions: str) -> None: ...


class AgentService:
    """CRUD for the agents catalog."""

    def __init__(self, db: AsyncSession, langfuse: LangfusePersonaPusher) -> None:
        self.db = db
        self.langfuse = langfuse

    async def list(
        self,
        *,
        active_only: bool = False,
        order_by: str = "name",
    ) -> list[Agent]:
        stmt = select(Agent)
        if active_only:
            stmt = stmt.where(Agent.is_active.is_(True))
        if order_by == "usage_count":
            stmt = stmt.order_by(Agent.usage_count.desc())
        else:
            stmt = stmt.order_by(Agent.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, agent_id: uuid.UUID) -> Agent:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    async def get_by_slug(self, slug: str) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, payload: AgentCreate, *, owner_id: uuid.UUID) -> Agent:
        agent = Agent(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            icon=payload.icon,
            color=payload.color,
            persona=payload.persona.model_dump(),
            scope=payload.scope.model_dump(mode="json"),
            is_active=payload.is_active,
            is_seed=False,
            model_role=payload.model_role,
            temperature=payload.temperature,
            owner_id=owner_id,
        )
        self.db.add(agent)
        await self.db.flush()

        try:
            await self.langfuse.push_persona(
                slug=agent.slug,
                instructions=payload.persona.instructions,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Langfuse push failed slug=%s: %s", agent.slug, exc)
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Langfuse unreachable; agent not created.",
            ) from exc

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update(self, agent_id: uuid.UUID, payload: AgentUpdate) -> Agent:
        agent = await self.get(agent_id)

        data = payload.model_dump(exclude_unset=True)
        if agent.is_seed and data.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seed agents cannot be deactivated.",
            )

        new_instructions: Optional[str] = None
        for key, value in data.items():
            if key == "persona" and value is not None:
                agent.persona = value
                new_instructions = value.get("instructions", "")
            elif key == "scope" and value is not None:
                agent.scope = value
            else:
                setattr(agent, key, value)
        await self.db.flush()

        if new_instructions is not None:
            try:
                await self.langfuse.push_persona(
                    slug=agent.slug,
                    instructions=new_instructions,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Langfuse update push failed slug=%s: %s", agent.slug, exc)
                await self.db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Langfuse unreachable; agent not updated.",
                ) from exc

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent_id: uuid.UUID) -> None:
        agent = await self.get(agent_id)
        if agent.is_seed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Seed agents cannot be deleted.",
            )
        await self.db.delete(agent)
        await self.db.commit()

    async def duplicate(self, agent_id: uuid.UUID, *, owner_id: uuid.UUID) -> Agent:
        src = await self.get(agent_id)
        suffix_n = 0
        candidate = f"{src.slug}_copy"
        while await self.get_by_slug(candidate) is not None:
            suffix_n += 1
            candidate = f"{src.slug}_copy{suffix_n}"
        dup = Agent(
            name=f"{src.name} (copia)",
            slug=candidate,
            description=src.description,
            icon=src.icon,
            color=src.color,
            persona=dict(src.persona),
            scope=dict(src.scope),
            is_active=False,
            is_seed=False,
            model_role=src.model_role,
            temperature=src.temperature,
            owner_id=owner_id,
        )
        self.db.add(dup)
        await self.db.flush()

        try:
            await self.langfuse.push_persona(
                slug=dup.slug,
                instructions=dup.persona.get("instructions", ""),
            )
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Langfuse unreachable.",
            ) from exc

        await self.db.commit()
        await self.db.refresh(dup)
        return dup

    async def increment_usage(self, agent_id: uuid.UUID) -> None:
        from sqlalchemy import update

        await self.db.execute(
            update(Agent).where(Agent.id == agent_id).values(usage_count=Agent.usage_count + 1)
        )
        await self.db.commit()
