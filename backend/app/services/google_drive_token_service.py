"""
Service for managing Google Drive OAuth tokens per user.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import requests
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import GoogleDriveToken, User

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance using shared CREDENTIALS_ENCRYPTION_KEY."""
    key = getattr(settings, "CREDENTIALS_ENCRYPTION_KEY", None)
    if not key:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY must be configured")
    decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
    if len(decoded) != 32:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY must decode to 32 bytes")
    return Fernet(key.encode("utf-8"))


class GoogleDriveTokenService:
    """Handles OAuth flow and token storage."""

    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    userinfo_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(self, db: Session):
        self.db = db
        self.fernet = _get_fernet()

    def _encrypt(self, value: Optional[str]) -> Optional[bytes]:
        if not value:
            return None
        return self.fernet.encrypt(value.encode("utf-8"))

    def _decrypt(self, value: Optional[bytes]) -> Optional[str]:
        if not value:
            return None
        return self.fernet.decrypt(value).decode("utf-8")

    def _client_config(self) -> dict:
        if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
            raise ValueError("Google OAuth client ID/secret not configured")
        return {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": self.auth_uri,
                "token_uri": self.token_uri,
            }
        }

    def create_flow(self, state: Optional[str] = None) -> Flow:
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=settings.google_oauth_scopes_list,
            state=state,
        )
        flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
        return flow

    def generate_auth_url(self, state: Optional[str] = None) -> str:
        flow = self.create_flow(state)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url

    def exchange_code(self, code: str, state: Optional[str] = None) -> Credentials:
        flow = self.create_flow(state)
        flow.fetch_token(code=code)
        return flow.credentials

    def fetch_userinfo(self, access_token: str) -> dict:
        response = requests.get(
            self.userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def upsert_tokens(
        self,
        user: User,
        credentials: Credentials,
        userinfo: dict,
    ) -> GoogleDriveToken:
        record = (
            self.db.query(GoogleDriveToken)
            .filter(GoogleDriveToken.user_id == user.id)
            .one_or_none()
        )
        scopes = credentials.scopes or settings.google_oauth_scopes_list
        access_token = credentials.token
        refresh_token = credentials.refresh_token

        if not refresh_token:
            if record:
                refresh_token = self._decrypt(record.refresh_token_encrypted)
            else:
                raise ValueError("Google did not return a refresh token. Prompt user to reconnect.")

        if record:
            record.google_user_id = userinfo.get("sub", record.google_user_id)
            record.google_email = userinfo.get("email", record.google_email)
            record.scopes = scopes
            record.access_token_encrypted = self._encrypt(access_token)
            record.refresh_token_encrypted = self._encrypt(refresh_token)
            record.token_expiry = credentials.expiry
            record.updated_at = datetime.utcnow()
        else:
            record = GoogleDriveToken(
                user_id=user.id,
                google_user_id=userinfo.get("sub", ""),
                google_email=userinfo.get("email", user.email),
                scopes=scopes,
                access_token_encrypted=self._encrypt(access_token),
                refresh_token_encrypted=self._encrypt(refresh_token),
                token_expiry=credentials.expiry,
            )
            self.db.add(record)

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_token_record(self, user_id: str) -> Optional[GoogleDriveToken]:
        user_uuid = UUID(str(user_id))
        return (
            self.db.query(GoogleDriveToken)
            .filter(GoogleDriveToken.user_id == user_uuid)
            .one_or_none()
        )

    def delete_tokens(self, user_id: str) -> bool:
        record = self.get_token_record(user_id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def _build_credentials_from_record(self, record: GoogleDriveToken) -> Credentials:
        access_token = self._decrypt(record.access_token_encrypted)
        refresh_token = self._decrypt(record.refresh_token_encrypted)
        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=self.token_uri,
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=record.scopes or settings.google_oauth_scopes_list,
            expiry=record.token_expiry,
        )

    def ensure_fresh_access_token(self, record: GoogleDriveToken) -> tuple[str, Optional[datetime]]:
        creds = self._build_credentials_from_record(record)
        if (
            creds.token
            and creds.expiry
            and creds.expiry > datetime.utcnow() + timedelta(seconds=30)
        ):
            return creds.token, creds.expiry

        if not creds.refresh_token:
            raise ValueError("Missing refresh token. Please reconnect Google Drive.")

        creds.refresh(Request())
        record.access_token_encrypted = self._encrypt(creds.token)
        record.token_expiry = creds.expiry
        self.db.commit()
        self.db.refresh(record)
        return creds.token, creds.expiry
