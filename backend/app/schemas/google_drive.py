"""Pydantic schemas for Google Drive integration."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl, Field


class GoogleDriveAuthURLResponse(BaseModel):
    authorization_url: HttpUrl


class GoogleDriveStatusResponse(BaseModel):
    connected: bool = Field(..., description="Whether the user has connected Google Drive")
    google_email: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class GoogleDriveDisconnectResponse(BaseModel):
    disconnected: bool


class InternalGoogleDriveTokenResponse(BaseModel):
    user_id: str
    google_email: str
    access_token: str
    expires_at: Optional[datetime]
    scopes: List[str] = Field(default_factory=list)
