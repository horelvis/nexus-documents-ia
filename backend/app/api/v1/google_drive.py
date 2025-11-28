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

from app.api.dependencies import get_current_user, get_db
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


def _encode_state(user: User) -> str:
    payload = {
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _decode_state(state: str) -> dict:
    try:
        return jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state token") from exc


@router.get("/oauth-url", response_model=GoogleDriveAuthURLResponse)
def get_authorization_url(
    current_user: User = Depends(get_current_user),
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
    except HTTPException as e:
        logger.error(f"❌ OAuth Callback: Invalid state token: {e}")
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    user = db.query(User).filter(User.id == payload["user_id"]).one_or_none()
    if not user:
        logger.error(f"❌ OAuth Callback: User not found for ID: {payload.get('user_id')}")
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    service = GoogleDriveTokenService(db)
    try:
        logger.info("OAuth Callback: Exchanging code for tokens...")
        credentials = service.exchange_code(code, state=state)
        logger.info("OAuth Callback: Tokens exchanged. Fetching user info...")
        userinfo = service.fetch_userinfo(credentials.token)
        logger.info("OAuth Callback: User info fetched. Upserting tokens...")
        service.upsert_tokens(user, credentials, userinfo)
        logger.info("OAuth Callback: Tokens upserted successfully.")
    except Exception as e:
        logger.error("❌ Failed to store Google Drive tokens for user %s: %s", user.id, str(e), exc_info=True)
        return RedirectResponse(settings.GOOGLE_OAUTH_ERROR_REDIRECT_URL)

    return RedirectResponse(settings.GOOGLE_OAUTH_SUCCESS_REDIRECT_URL)


@router.get("/status", response_model=GoogleDriveStatusResponse)
def get_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = GoogleDriveTokenService(db)
    record = service.get_token_record(current_user.id)
    if not record:
        return GoogleDriveStatusResponse(connected=False)

    return GoogleDriveStatusResponse(
        connected=True,
        google_email=record.google_email,
        scopes=record.scopes or [],
        expires_at=record.token_expiry,
    )


@router.post("/disconnect", response_model=GoogleDriveDisconnectResponse)
def disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = GoogleDriveTokenService(db)
    disconnected = service.delete_tokens(current_user.id)
    return GoogleDriveDisconnectResponse(disconnected=disconnected)
