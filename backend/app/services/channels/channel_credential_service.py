"""
Service for managing encrypted credentials for Information Channels.

Uses Fernet symmetric encryption (same pattern as GoogleDriveTokenService)
to securely store OAuth tokens and database credentials.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.db.models import InformationChannel, ChannelCredential

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """Get Fernet instance for credential encryption/decryption.

    Uses CREDENTIALS_ENCRYPTION_KEY from settings (shared across all
    credential services: Google Drive, Gmail, Channels, etc.)
    """
    key = getattr(settings, "CREDENTIALS_ENCRYPTION_KEY", None)
    if not key:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY must be configured")
    # Key should be a URL-safe base64-encoded 32-byte key
    try:
        decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
        if len(decoded) != 32:
            raise ValueError("CREDENTIALS_ENCRYPTION_KEY must decode to 32 bytes")
    except Exception as e:
        raise ValueError(f"Invalid CREDENTIALS_ENCRYPTION_KEY format: {e}")
    return Fernet(key.encode("utf-8"))


class ChannelCredentialService:
    """
    Service for securely storing and retrieving channel credentials.

    Supports:
    - OAuth credentials (Gmail, Google Drive)
    - Database credentials (username/password)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.fernet = _get_fernet()

    def _encrypt(self, data: Dict[str, Any]) -> bytes:
        """Encrypt a dictionary as JSON bytes."""
        json_str = json.dumps(data)
        return self.fernet.encrypt(json_str.encode("utf-8"))

    def _decrypt(self, encrypted: bytes) -> Dict[str, Any]:
        """Decrypt bytes back to a dictionary."""
        decrypted = self.fernet.decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))

    async def store_oauth_credentials(
        self,
        channel_id: UUID,
        credentials: Credentials,
        userinfo: Dict[str, Any],
        scopes: list[str],
    ) -> ChannelCredential:
        """
        Store OAuth credentials for a Google channel (Gmail/Drive).

        Args:
            channel_id: The channel this credential belongs to
            credentials: Google OAuth Credentials object
            userinfo: User info from Google (contains email, sub)
            scopes: OAuth scopes granted

        Returns:
            The created/updated ChannelCredential record
        """
        creds_dict = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
        }

        # Check if credential already exists for this channel
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing credential
            # Keep old refresh token if new one is not provided
            if not credentials.refresh_token:
                old_creds = self._decrypt(existing.credentials_encrypted)
                creds_dict["refresh_token"] = old_creds.get("refresh_token")

            existing.credentials_encrypted = self._encrypt(creds_dict)
            existing.oauth_provider = "google"
            existing.oauth_user_id = userinfo.get("sub")
            existing.oauth_email = userinfo.get("email")
            existing.oauth_scopes = scopes
            existing.token_expiry = credentials.expiry
            existing.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new credential
            record = ChannelCredential(
                channel_id=channel_id,
                credentials_encrypted=self._encrypt(creds_dict),
                oauth_provider="google",
                oauth_user_id=userinfo.get("sub"),
                oauth_email=userinfo.get("email"),
                oauth_scopes=scopes,
                token_expiry=credentials.expiry,
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
            return record

    async def store_db_credentials(
        self,
        channel_id: UUID,
        username: str,
        password: str,
    ) -> ChannelCredential:
        """
        Store database credentials for an external DB channel.

        Args:
            channel_id: The channel this credential belongs to
            username: Database username
            password: Database password

        Returns:
            The created/updated ChannelCredential record
        """
        creds_dict = {
            "username": username,
            "password": password,
        }

        # Check if credential already exists
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.credentials_encrypted = self._encrypt(creds_dict)
            existing.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            record = ChannelCredential(
                channel_id=channel_id,
                credentials_encrypted=self._encrypt(creds_dict),
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
            return record

    async def get_oauth_credentials(self, channel_id: UUID) -> Optional[Credentials]:
        """
        Get Google OAuth credentials for a channel, refreshing if needed.

        Returns:
            Google Credentials object, or None if not found
        """
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record or record.oauth_provider != "google":
            return None

        creds_dict = self._decrypt(record.credentials_encrypted)
        access_token = creds_dict.get("access_token")
        refresh_token = creds_dict.get("refresh_token")

        # Convert token_expiry to timezone-naive before passing to Credentials
        # Google Auth library uses utcnow() (naive) internally for comparison,
        # but PostgreSQL stores timestamps as timezone-aware (UTC)
        token_expiry = record.token_expiry
        if token_expiry and token_expiry.tzinfo is not None:
            token_expiry = token_expiry.replace(tzinfo=None)

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=record.oauth_scopes or [],
            expiry=token_expiry,
        )

        # Refresh if expired (with 30 second buffer)
        # Handle both timezone-aware and naive datetimes
        now = datetime.utcnow()
        expiry = credentials.expiry
        if expiry:
            # Make comparison timezone-naive
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)

        if expiry and expiry <= now + timedelta(seconds=30):
            if not credentials.refresh_token:
                raise ValueError("Token expired and no refresh token available")

            logger.info(f"Refreshing expired OAuth token for channel {channel_id}")
            credentials.refresh(Request())

            # Update stored credentials
            creds_dict["access_token"] = credentials.token
            if credentials.refresh_token:
                creds_dict["refresh_token"] = credentials.refresh_token

            record.credentials_encrypted = self._encrypt(creds_dict)
            record.token_expiry = credentials.expiry
            await self.db.commit()

        return credentials

    async def get_db_credentials(self, channel_id: UUID) -> Optional[Dict[str, str]]:
        """
        Get database credentials for a channel.

        Returns:
            Dict with 'username' and 'password', or None if not found
        """
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return None

        return self._decrypt(record.credentials_encrypted)

    async def delete_credentials(self, channel_id: UUID) -> bool:
        """
        Delete credentials for a channel.

        Returns:
            True if deleted, False if not found
        """
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return False

        await self.db.delete(record)
        await self.db.commit()
        return True

    async def has_credentials(self, channel_id: UUID) -> bool:
        """Check if a channel has stored credentials."""
        stmt = select(ChannelCredential).where(ChannelCredential.channel_id == channel_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
