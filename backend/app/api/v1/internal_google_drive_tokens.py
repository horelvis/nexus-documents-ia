"""
Internal endpoints to allow microservices to retrieve Google Drive access tokens.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_microservice_api_key
from app.schemas.google_drive import InternalGoogleDriveTokenResponse
from app.services.google_drive_token_service import GoogleDriveTokenService

router = APIRouter(
    tags=["internal-google-drive"],
    dependencies=[Depends(require_microservice_api_key)],
)


@router.get("/google-drive-tokens/{user_id}", response_model=InternalGoogleDriveTokenResponse)
def get_access_token(user_id: str, db: Session = Depends(get_db)):
    service = GoogleDriveTokenService(db)
    record = service.get_token_record(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="User has not connected Google Drive")

    try:
        access_token, expires_at = service.ensure_fresh_access_token(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InternalGoogleDriveTokenResponse(
        user_id=user_id,
        google_email=record.google_email,
        access_token=access_token,
        expires_at=expires_at,
        scopes=record.scopes or [],
    )
