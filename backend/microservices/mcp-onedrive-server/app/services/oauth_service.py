"""
OAuth2 Service for OneDrive (Azure AD) authentication.

Handles the complete OAuth2 flow:
1. Generate authorization URL (admin clicks to authorize)
2. Handle callback (exchange code for tokens via MSAL)
3. Encrypt and store tokens in connectors.config JSONB
4. Auto-refresh expired access tokens
5. Revoke tokens (clear from DB — MS has no standard revoke endpoint)

Token storage format in connectors.config:
{
    "drive_id": "...",
    "folder_id": "...",
    "access_token_encrypted": "gAAAAA...",
    "refresh_token_encrypted": "gAAAAA...",
    "token_expiry": "2026-02-06T12:00:00+00:00",
    "microsoft_email": "admin@company.onmicrosoft.com",
    "scopes": ["Files.ReadWrite.All", "User.Read"]
}
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
import msal

from ..core.config import settings, encrypt_token, decrypt_token, invalidate_connector_cache

logger = logging.getLogger(__name__)


class OAuthService:
    """Manages OAuth2 flow and token lifecycle for OneDrive connectors via Azure AD."""

    AUTHORITY_BASE = "https://login.microsoftonline.com"
    GRAPH_USERINFO = "https://graph.microsoft.com/v1.0/me"

    @property
    def authority(self) -> str:
        """Azure AD authority URL using configured Azure tenant (external)."""
        return f"{self.AUTHORITY_BASE}/{settings.ms_oauth_tenant_id}"

    @property
    def auth_endpoint(self) -> str:
        return f"{self.authority}/oauth2/v2.0/authorize"

    @property
    def token_endpoint(self) -> str:
        return f"{self.authority}/oauth2/v2.0/token"

    def _get_msal_app(self) -> msal.ConfidentialClientApplication:
        """Create MSAL confidential client application."""
        if not settings.ms_oauth_client_id or not settings.ms_oauth_client_secret:
            raise ValueError("Microsoft OAuth client ID/secret not configured")
        return msal.ConfidentialClientApplication(
            client_id=settings.ms_oauth_client_id,
            client_credential=settings.ms_oauth_client_secret,
            authority=self.authority,
        )

    def generate_auth_url(
        self,
        connector_id: str,
        login_hint: str = None,
    ) -> str:
        """
        Generate Microsoft OAuth authorization URL.

        The state parameter encodes connector_id so the callback
        knows which connector to store the tokens under.
        """
        state = str(connector_id)
        app = self._get_msal_app()

        auth_url = app.get_authorization_request_url(
            scopes=settings.ms_oauth_scopes_list,
            state=state,
            redirect_uri=settings.ms_oauth_redirect_uri,
            login_hint=login_hint,
            prompt="consent",
        )

        return auth_url

    async def fetch_userinfo(self, access_token: str) -> dict:
        """Fetch Microsoft user info (email, displayName, etc.) from Graph /me."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                self.GRAPH_USERINFO,
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
        Handle OAuth callback: exchange code via MSAL, encrypt tokens, save to DB.

        Args:
            code: Authorization code from Azure AD
            state: connector_id (possibly followed by legacy ":<ignored>")

        Returns:
            Dict with connector_id, microsoft_email, success status
        """
        # Parse state — accept bare UUID or legacy "connector_id:<anything>" format
        connector_id_str = state.split(":", 1)[0] if ":" in state else state
        connector_id = UUID(connector_id_str)

        # Exchange code for tokens via MSAL
        app = self._get_msal_app()
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=settings.ms_oauth_scopes_list,
            redirect_uri=settings.ms_oauth_redirect_uri,
        )

        if "error" in result:
            raise ValueError(
                f"Token exchange failed: {result.get('error_description', result.get('error'))}"
            )

        access_token = result["access_token"]
        refresh_token = result.get("refresh_token")

        # Calculate expiry from expires_in
        expires_in = result.get("expires_in", 3600)
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get user info
        userinfo = await self.fetch_userinfo(access_token)
        microsoft_email = (
            userinfo.get("mail")
            or userinfo.get("userPrincipalName")
            or ""
        )

        # Get granted scopes
        granted_scopes = result.get("scope", "").split() if result.get("scope") else settings.ms_oauth_scopes_list

        # Encrypt tokens
        access_token_encrypted = encrypt_token(access_token)
        refresh_token_encrypted = encrypt_token(refresh_token)

        # Save to database
        await self._save_tokens_to_db(
            connector_id=connector_id,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            token_expiry=token_expiry,
            microsoft_email=microsoft_email,
            scopes=granted_scopes,
        )

        # Invalidate cache
        await invalidate_connector_cache(connector_id)

        logger.info(f"OAuth tokens saved for connector {connector_id}, email: {microsoft_email}")

        return {
            "success": True,
            "connector_id": str(connector_id),
            "microsoft_email": microsoft_email,
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
            app = self._get_msal_app()
            result = app.acquire_token_by_refresh_token(
                refresh_token=config.refresh_token,
                scopes=config.scopes or settings.ms_oauth_scopes_list,
            )

            if "error" in result:
                logger.error(
                    f"Token refresh failed for connector {connector_id}: "
                    f"{result.get('error_description', result.get('error'))}"
                )
                return None

            new_access_token = result["access_token"]
            new_refresh_token = result.get("refresh_token", config.refresh_token)
            expires_in = result.get("expires_in", 3600)
            token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Save refreshed tokens
            await self._save_tokens_to_db(
                connector_id=connector_id,
                access_token_encrypted=encrypt_token(new_access_token),
                refresh_token_encrypted=encrypt_token(new_refresh_token),
                token_expiry=token_expiry,
                microsoft_email=config.microsoft_email,
                scopes=config.scopes,
            )

            await invalidate_connector_cache(connector_id)

            logger.info(f"Refreshed access token for connector {connector_id}")
            return new_access_token

        except Exception as e:
            logger.error(f"Failed to refresh token for connector {connector_id}: {e}")
            return None

    async def revoke_token(
        self,
        connector_id: UUID,
    ) -> bool:
        """
        Revoke OAuth tokens.

        Microsoft doesn't have a standard token revoke endpoint.
        We simply clear the tokens from the database.
        Users can revoke app permissions at https://myaccount.microsoft.com/
        """
        from ..core.config import load_connector_from_db

        config = await load_connector_from_db(connector_id)
        if not config or not config.access_token:
            return False

        # Clear tokens in DB
        await self._clear_tokens_in_db(connector_id)
        await invalidate_connector_cache(connector_id)

        logger.info(f"Cleared OAuth tokens for connector {connector_id}")
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
            "microsoft_email": config.microsoft_email,
            "token_expired": token_expired,
            "token_expiry": config.token_expiry.isoformat() if config.token_expiry else None,
            "scopes": config.scopes,
            "drive_id": config.drive_id,
            "folder_id": config.folder_id,
        }

    async def ensure_fresh_token(
        self,
        config: "OneDriveInstanceConfig",
    ) -> str:
        """
        Ensure we have a valid (non-expired) access token.

        Auto-refreshes if expired.

        Returns:
            Valid access token string

        Raises:
            ValueError if no token available or refresh fails
        """
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
                "Please re-authorize OneDrive."
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
        microsoft_email: Optional[str],
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
            config_data['microsoft_email'] = microsoft_email
            config_data['scopes'] = scopes

            # Save back
            await conn.execute(
                "UPDATE connectors SET config = $1::jsonb WHERE id = $2",
                json.dumps(config_data),
                connector_id,
            )

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
                        'token_expiry', 'microsoft_email', 'scopes']:
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
