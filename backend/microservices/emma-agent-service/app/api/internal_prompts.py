"""Internal endpoint for service-to-service prompt management.

Used by the Main API to push admin-curated agent personas into Langfuse
without bundling the langfuse SDK there. Authenticated with the shared
``MICROSERVICES_API_KEY`` header.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class PushPersonaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,49}$")
    instructions: str = Field(..., max_length=20000)


@router.post("/prompts/push-persona", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def push_persona(payload: PushPersonaRequest, _: None = Depends(_verify_api_key)):
    """Push an agent persona to Langfuse as ``agent_<slug>_persona``.

    Idempotent: each call creates a new Langfuse version with label ``production``.
    """
    name = f"agent_{payload.slug}_persona"
    try:
        from langfuse import Langfuse
        client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        # langfuse SDK is sync; offload to a thread.
        import asyncio
        await asyncio.to_thread(
            client.create_prompt,
            name=name,
            prompt=payload.instructions,
            labels=["production"],
            type="text",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Langfuse push failed for %s", name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Langfuse error: {exc}",
        ) from exc

    logger.info("Pushed Langfuse prompt name=%s len=%d", name, len(payload.instructions))
