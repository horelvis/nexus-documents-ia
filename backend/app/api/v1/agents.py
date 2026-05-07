"""REST endpoints for the admin-curated agents catalog.

Reads (list/get) are open to every authenticated user.
Writes (create/update/delete/duplicate) require ``is_superuser=True``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import get_current_user_async
from app.api.auth_helpers import get_user_or_internal
from app.core.auth.base import UserProfile
from app.core.auth.superuser import require_superuser
from app.core.config import settings
from app.db.async_database import get_async_db
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.services.agent_service import AgentService
from app.services.langfuse.persona import LangfusePersonaAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


def _service(db: AsyncSession = Depends(get_async_db)) -> AgentService:
    return AgentService(db=db, langfuse=LangfusePersonaAdapter())


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    active: Optional[bool] = None,
    slug: Optional[str] = None,
    order_by: Optional[str] = "name",
    _user: UserProfile = Depends(get_user_or_internal),
    svc: AgentService = Depends(_service),
) -> list[AgentResponse]:
    if slug is not None:
        agent = await svc.get_by_slug(slug)
        return [AgentResponse.model_validate(agent)] if agent else []
    rows = await svc.list(active_only=bool(active), order_by=order_by or "name")
    return [AgentResponse.model_validate(a) for a in rows]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    _user: UserProfile = Depends(get_user_or_internal),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    return AgentResponse.model_validate(await svc.get(agent_id))


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    agent = await svc.create(payload, owner_id=uuid.UUID(admin.sub))
    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    _admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    return AgentResponse.model_validate(await svc.update(agent_id, payload))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_agent(
    agent_id: uuid.UUID,
    _admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
):
    await svc.delete(agent_id)


@router.post(
    "/{agent_id}/duplicate",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_agent(
    agent_id: uuid.UUID,
    admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    dup = await svc.duplicate(agent_id, owner_id=uuid.UUID(admin.sub))
    return AgentResponse.model_validate(dup)


@router.post(
    "/{agent_id}/usage",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    include_in_schema=False,
)
async def increment_agent_usage(
    agent_id: uuid.UUID,
    _user: UserProfile = Depends(get_user_or_internal),
    svc: AgentService = Depends(_service),
):
    """Internal: emma-agent-service bumps usage_count after invoke_agent."""
    await svc.increment_usage(agent_id)


@router.get("/{agent_id}/metrics", response_model=dict)
async def get_metrics(
    agent_id: uuid.UUID,
    _user: UserProfile = Depends(get_user_or_internal),
    svc: AgentService = Depends(_service),
) -> dict:
    """Light metrics: usage_count from DB. Latency / last_used reserved for follow-up."""
    agent = await svc.get(agent_id)
    return {
        "usage_count": agent.usage_count,
        "last_used_at": None,
        "avg_latency_ms": None,
    }


class GeneratePromptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    semantic_types: list[str] = Field(default_factory=list)
    current_instructions: str = Field(default="", max_length=20000)


@router.post("/_helpers/generate-prompt", response_model=dict)
async def generate_prompt_helper(
    payload: GeneratePromptBody,
    _admin: UserProfile = Depends(require_superuser),
) -> dict:
    """Generate or improve an agent system prompt via the chat LLM.

    Proxies to emma-agent-service, which holds the LLM client. Admin-only
    so we don't leak generation cycles to anonymous callers.
    """
    base_url = getattr(settings, "EMMA_SERVICE_URL", "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="EMMA_SERVICE_URL not configured")
    api_key = getattr(settings, "MICROSERVICES_API_KEY", "")

    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(
                f"{base_url}/internal/agents/helpers/generate-prompt",
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                json=payload.model_dump(),
            )
    except httpx.RequestError as exc:
        logger.error("generate-prompt proxy unreachable: %s", exc)
        raise HTTPException(status_code=502, detail=f"emma unreachable: {exc}") from exc

    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
