"""
Google Drive OAuth endpoints for end users.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.config import settings
from app.db.models import User
from app.schemas.google_drive import (
    GoogleDriveAuthURLResponse,
    GoogleDriveStatusResponse,
    GoogleDriveDisconnectResponse,
)
from app.services.google_drive_token_service import GoogleDriveTokenService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google-drive", tags=["google-drive"])


def _encode_state(user: UserProfile) -> str:
    payload = {
        "user_id": str(user.sub),
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _decode_state(state: str) -> dict:
    try:
        return jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token") from exc


@router.get("/oauth-url", response_model=GoogleDriveAuthURLResponse)
async def get_authorization_url(
    current_user: UserProfile = Depends(get_current_user_async),
    db: Session = Depends(get_db),
):
    service = GoogleDriveTokenService(db)
    state_token = _encode_state(current_user)
    auth_url = service.generate_auth_url(state=state_token)
    return GoogleDriveAuthURLResponse(authorization_url=auth_url)


@router.get("/oauth/callback")
def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        payload = _decode_state(state)
    except HTTPException:
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    user = db.query(User).filter(User.id == payload["user_id"]).one_or_none()
    if not user:
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    service = GoogleDriveTokenService(db)
    try:
        credentials = service.exchange_code(code, state=state)
        userinfo = service.fetch_userinfo(credentials.token)
        service.upsert_tokens(user, credentials, userinfo)
    except Exception:
        logger.exception("Failed to store Google Drive tokens for user %s", user.id)
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    return RedirectResponse(settings.GOOGLE_OAUTH_SUCCESS_REDIRECT_URL)


@router.get("/status", response_model=GoogleDriveStatusResponse)
async def get_status(
    current_user: UserProfile = Depends(get_current_user_async),
    db: Session = Depends(get_db),
):
    service = GoogleDriveTokenService(db)
    record = service.get_token_record(current_user.sub)
    if not record:
        return GoogleDriveStatusResponse(connected=False)

    return GoogleDriveStatusResponse(
        connected=True,
        google_email=record.google_email,
        scopes=record.scopes or [],
        expires_at=record.token_expiry,
    )


@router.post("/disconnect", response_model=GoogleDriveDisconnectResponse)
async def disconnect(
    current_user: UserProfile = Depends(get_current_user_async),
    db: Session = Depends(get_db),
):
    service = GoogleDriveTokenService(db)
    disconnected = service.delete_tokens(current_user.sub)
    return GoogleDriveDisconnectResponse(disconnected=disconnected)
