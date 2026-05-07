"""Mixed-auth FastAPI dependency: authenticated user OR microservices API key.

Used by endpoints that are read-callable both from the browser (with
KeyCloak/Clerk JWT) and from internal microservices (with the shared
``MICROSERVICES_API_KEY``). Returns ``UserProfile`` (synthetic for the
internal-call case) so downstream code can stay agnostic.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.base import UserProfile
from app.core.config import settings
from app.db.async_database import get_async_db


_INTERNAL_PROFILE = UserProfile(
    sub="00000000-0000-0000-0000-000000000000",
    email="internal@nouxcube",
    name="Internal Service",
    roles=[],
    is_superuser=False,
)


async def get_user_or_internal(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-ID"),
    db: AsyncSession = Depends(get_async_db),
) -> UserProfile:
    """Accept either a user JWT or the microservices API key."""
    if x_api_key and settings.MICROSERVICES_API_KEY and x_api_key == settings.MICROSERVICES_API_KEY:
        return _INTERNAL_PROFILE

    # Fall through to standard user auth
    from app.api.async_dependencies import get_current_user_async

    try:
        return await get_current_user_async(
            request=request,
            db=db,
            authorization=authorization,
            x_user_id=x_user_id,
            x_request_id=x_request_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        ) from exc
