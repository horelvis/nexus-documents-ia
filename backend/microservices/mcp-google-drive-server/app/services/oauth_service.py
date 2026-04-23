"""
OAuth2 Service for Google Drive authentication.

Handles the complete OAuth2 flow:
1. Generate authorization URL (admin clicks to authorize)
2. Handle callback (exchange code for tokens)
3. Encrypt and store tokens in connectors.config JSONB
4. Auto-refresh expired access tokens
5. Revoke tokens

Token storage format in connectors.config:
{
    "folder_id": "1abc...",
    "include_subfolders": true,
    "access_token_encrypted": "gAAAAA...",
    "refresh_token_encrypted": "gAAAAA...",
    "token_expiry": "2025-01-31T12:00:00+00:00",
    "google_email": "admin@company.com",
    "scopes": ["https://www.googleapis.com/auth/drive.readonly"]
}
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from ..core.config import settings, encrypt_token, decrypt_token, invalidate_connector_cache

logger = logging.getLogger(__name__)


class OAuthService:
    """Manages OAuth2 flow and token lifecycle for Google Drive connectors."""

    AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
    TOKEN_URI = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
    REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

    def _client_config(self) -> dict:
        """Build Google OAuth client config dict."""
        if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
            raise ValueError("Google OAuth client ID/secret not configured")
        return {
            "web": {
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "auth_uri": self.AUTH_URI,
                "token_uri": self.TOKEN_URI,
            }
        }

    def _create_flow(self, state: Optional[str] = None) -> Flow:
        """Create Google OAuth flow."""
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=settings.google_oauth_scopes_list,
            state=state,
        )
        flow.redirect_uri = settings.google_oauth_redirect_uri
        return flow

    async def generate_auth_url(self, connector_id: str, login_hint: str = None) -> str:
        """
        Generate Google OAuth authorization URL.

        The state parameter encodes the connector_id so the callback knows
        where to store the tokens.

        google-auth-oauthlib auto-enables PKCE on Flow.authorization_url(),
        so we persist the generated code_verifier into connectors.config and
        retrieve it at callback time (see exchange_code).
        """
        state = str(connector_id)
        flow = self._create_flow(state=state)
        kwargs = {
            "access_type": "offline",
            "prompt": "consent",
        }
        if login_hint:
            kwargs["login_hint"] = login_hint
        authorization_url, _ = flow.authorization_url(**kwargs)

        # Persist PKCE code_verifier for the callback handshake.
        verifier = getattr(flow, "code_verifier", None)
        if verifier:
            await self._save_pkce_verifier(UUID(connector_id), verifier)

        return authorization_url

    async def exchange_code(self, code: str, state: str) -> Credentials:
        """Exchange authorization code for credentials (with PKCE verifier)."""
        flow = self._create_flow(state=state)

        # Retrieve the code_verifier persisted at authorize time. Restoring
        # it on the Flow before fetch_token is the only way to pass it to
        # the token endpoint via google-auth-oauthlib.
        connector_id_str = state.split(":", 1)[0].strip()
        verifier = await self._consume_pkce_verifier(UUID(connector_id_str))
        if verifier:
            flow.code_verifier = verifier

        flow.fetch_token(code=code)
        return flow.credentials

    async def fetch_userinfo(self, access_token: str) -> dict:
        """Fetch Google user info (email, name, etc.)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def handle_callback(
        self,
        code: str,
        state: str,
    ) -> Dict[str, Any]:
        """
        Handle OAuth callback: exchange code, encrypt tokens, save to DB.

        Args:
            code: Authorization code from Google
            state: connector_id encoded as state

        Returns:
            Dict with connector_id, google_email, success status
        """
        # Parse state — legacy callers may still send "connector_id:tenant_id";
        # accept either form and use only the connector_id.
        connector_id_str = state.split(":", 1)[0].strip()
        if not connector_id_str:
            raise ValueError(f"Invalid state parameter: {state}")
        connector_id = UUID(connector_id_str)

        # Exchange code for tokens
        credentials = await self.exchange_code(code, state)

        # Get user info
        userinfo = await self.fetch_userinfo(credentials.token)
        google_email = userinfo.get("email", "")

        # Encrypt tokens
        access_token_encrypted = encrypt_token(credentials.token)
        refresh_token_encrypted = encrypt_token(credentials.refresh_token)

        # Save to database
        await self._save_tokens_to_db(
            connector_id=connector_id,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            token_expiry=credentials.expiry,
            google_email=google_email,
            scopes=list(credentials.scopes) if credentials.scopes else settings.google_oauth_scopes_list,
        )

        # Invalidate cache
        await invalidate_connector_cache(connector_id)

        logger.info(f"OAuth tokens saved for connector {connector_id}, email: {google_email}")

        return {
            "success": True,
            "connector_id": str(connector_id),
            "google_email": google_email,
        }

    async def refresh_access_token(
        self,
        connector_id: UUID,
    ) -> Optional[str]:
        """
        Refresh an expired access token using the refresh token.

        Returns new access token or None if refresh failed.
        """
        from ..core.config import load_connector_from_db

        config = await load_connector_from_db(connector_id)
        if not config or not config.refresh_token:
            logger.error(f"No refresh token for connector {connector_id}")
            return None

        try:
            creds = Credentials(
                token=config.access_token,
                refresh_token=config.refresh_token,
                token_uri=self.TOKEN_URI,
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                scopes=config.scopes or settings.google_oauth_scopes_list,
                expiry=config.token_expiry,
            )

            creds.refresh(Request())

            # Save refreshed tokens
            await self._save_tokens_to_db(
                connector_id=connector_id,
                access_token_encrypted=encrypt_token(creds.token),
                refresh_token_encrypted=encrypt_token(creds.refresh_token or config.refresh_token),
                token_expiry=creds.expiry,
                google_email=config.google_email,
                scopes=config.scopes,
            )

            await invalidate_connector_cache(connector_id)

            logger.info(f"Refreshed access token for connector {connector_id}")
            return creds.token

        except Exception as e:
            logger.error(f"Failed to refresh token for connector {connector_id}: {e}")
            return None

    async def revoke_token(
        self,
        connector_id: UUID,
    ) -> bool:
        """Revoke OAuth tokens and clear from DB."""
        from ..core.config import load_connector_from_db

        config = await load_connector_from_db(connector_id)
        if not config or not config.access_token:
            return False

        # Revoke at Google
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    self.REVOKE_ENDPOINT,
                    params={"token": config.access_token},
                )
        except Exception as e:
            logger.warning(f"Failed to revoke token at Google (may already be revoked): {e}")

        # Clear tokens in DB
        await self._clear_tokens_in_db(connector_id)
        await invalidate_connector_cache(connector_id)

        logger.info(f"Revoked OAuth tokens for connector {connector_id}")
        return True

    async def get_oauth_status(
        self,
        connector_id: UUID,
    ) -> Dict[str, Any]:
        """Check OAuth status for a connector."""
        from ..core.config import load_connector_from_db

        config = await load_connector_from_db(connector_id)
        if not config:
            return {"connected": False, "error": "Connector not found"}

        if not config.is_authenticated:
            return {"connected": False, "error": "Not authorized"}

        # Check token expiry
        token_expired = False
        if config.token_expiry:
            expiry = config.token_expiry
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            token_expired = expiry <= datetime.now(timezone.utc)

        return {
            "connected": True,
            "google_email": config.google_email,
            "token_expired": token_expired,
            "token_expiry": config.token_expiry.isoformat() if config.token_expiry else None,
            "scopes": config.scopes,
            "folder_id": config.folder_id,
        }

    async def ensure_fresh_token(
        self,
        config: "GoogleDriveInstanceConfig",
    ) -> str:
        """
        Ensure we have a valid (non-expired) access token.

        Auto-refreshes if expired.

        Returns:
            Valid access token string

        Raises:
            ValueError if no token available or refresh fails
        """
        from datetime import timedelta

        if not config.is_authenticated:
            raise ValueError(f"Connector {config.connector_id} not authenticated")

        # Check if token is still valid (with 30s buffer)
        expiry = config.token_expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if (
            config.access_token
            and expiry
            and expiry > datetime.now(timezone.utc) + timedelta(seconds=30)
        ):
            return config.access_token

        # Need to refresh
        new_token = await self.refresh_access_token(config.connector_id)
        if not new_token:
            raise ValueError(
                f"Failed to refresh token for connector {config.connector_id}. "
                "Please re-authorize Google Drive."
            )

        return new_token

    # =========================================================================
    # Database helpers
    # =========================================================================

    async def _save_tokens_to_db(
        self,
        connector_id: UUID,
        access_token_encrypted: Optional[str],
        refresh_token_encrypted: Optional[str],
        token_expiry: Optional[datetime],
        google_email: Optional[str],
        scopes: Optional[list],
    ) -> None:
        """Update connector config with encrypted OAuth tokens."""
        import asyncpg

        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(db_url)
        try:
            # Read current config
            row = await conn.fetchrow(
                "SELECT config FROM connectors WHERE id = $1",
                connector_id,
            )
            if not row:
                raise ValueError(f"Connector {connector_id} not found")

            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}

            # Update OAuth fields
            config_data['access_token_encrypted'] = access_token_encrypted
            config_data['refresh_token_encrypted'] = refresh_token_encrypted
            config_data['token_expiry'] = token_expiry.isoformat() if token_expiry else None
            config_data['google_email'] = google_email
            config_data['scopes'] = scopes

            # Save back
            await conn.execute(
                "UPDATE connectors SET config = $1::jsonb WHERE id = $2",
                json.dumps(config_data),
                connector_id,
            )

        finally:
            await conn.close()

    async def _save_pkce_verifier(self, connector_id: UUID, verifier: str) -> None:
        """Persist PKCE code_verifier into connectors.config for this authorize attempt."""
        import asyncpg

        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow(
                "SELECT config FROM connectors WHERE id = $1", connector_id,
            )
            if not row:
                return
            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}
            config_data['oauth_pkce_verifier'] = verifier
            await conn.execute(
                "UPDATE connectors SET config = $1::jsonb WHERE id = $2",
                json.dumps(config_data),
                connector_id,
            )
        finally:
            await conn.close()

    async def _consume_pkce_verifier(self, connector_id: UUID) -> Optional[str]:
        """Read + delete the persisted PKCE code_verifier. Returns None if absent."""
        import asyncpg

        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow(
                "SELECT config FROM connectors WHERE id = $1", connector_id,
            )
            if not row:
                return None
            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}
            verifier = config_data.pop('oauth_pkce_verifier', None)
            if verifier is not None:
                await conn.execute(
                    "UPDATE connectors SET config = $1::jsonb WHERE id = $2",
                    json.dumps(config_data),
                    connector_id,
                )
            return verifier
        finally:
            await conn.close()

    async def _clear_tokens_in_db(self, connector_id: UUID) -> None:
        """Clear OAuth tokens from connector config."""
        import asyncpg

        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(db_url)
        try:
            row = await conn.fetchrow(
                "SELECT config FROM connectors WHERE id = $1",
                connector_id,
            )
            if not row:
                return

            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}

            # Remove OAuth fields
            for key in ['access_token_encrypted', 'refresh_token_encrypted',
                        'token_expiry', 'google_email', 'scopes']:
                config_data.pop(key, None)

            await conn.execute(
                "UPDATE connectors SET config = $1::jsonb WHERE id = $2",
                json.dumps(config_data),
                connector_id,
            )

        finally:
            await conn.close()


# Singleton
oauth_service = OAuthService()
