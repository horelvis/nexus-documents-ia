"""
Configuration for MCP Google Drive Server.

Loads Google Drive connector configurations from the backend database.
Each connector is configured via the UI.

The MCP server connects to PostgreSQL to read connector configurations
from the `connectors` table where connector_type = 'google_drive'.

Unlike Alfresco (Basic Auth), Google Drive uses OAuth2 tokens stored
encrypted in the connector's config JSONB column.

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
    CONNECTOR_CACHE_TTL: Cache TTL in seconds (default: 300)
    GOOGLE_OAUTH_CLIENT_ID: Google OAuth client ID
    GOOGLE_OAUTH_CLIENT_SECRET: Google OAuth client secret
    GOOGLE_OAUTH_REDIRECT_URI: OAuth callback URL
    CREDENTIALS_ENCRYPTION_KEY: Fernet key for token encryption
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class GoogleDriveInstanceConfig(BaseModel):
    """Configuration for a single Google Drive connector instance."""

    # Connector identification
    connector_id: UUID = Field(..., description="Connector UUID from database")
    name: str = Field(..., description="Connector name")
    description: Optional[str] = Field(default=None)

    # Google Drive settings
    folder_id: Optional[str] = Field(default=None, description="Root folder ID to sync")
    include_subfolders: bool = Field(default=True, description="Recurse into subfolders")
    file_types: Optional[List[str]] = Field(default=None, description="File extensions to include")
    max_file_size_mb: int = Field(default=50, description="Max file size in MB")

    # OAuth tokens (encrypted in DB, decrypted here)
    access_token: Optional[str] = Field(default=None, description="Decrypted access token")
    refresh_token: Optional[str] = Field(default=None, description="Decrypted refresh token")
    token_expiry: Optional[datetime] = Field(default=None, description="Token expiry time")
    google_email: Optional[str] = Field(default=None, description="Google account email")
    scopes: Optional[List[str]] = Field(default=None, description="OAuth scopes")

    # Timeouts
    timeout_seconds: int = Field(default=60, description="Request timeout")
    download_timeout_seconds: int = Field(default=300, description="Download timeout")

    # Limits
    max_results: int = Field(default=100, description="Max search results")

    # Status
    is_active: bool = Field(default=True)

    @property
    def is_authenticated(self) -> bool:
        """Check if OAuth tokens are present."""
        return bool(self.access_token and self.refresh_token)


class Settings(BaseSettings):
    """MCP Google Drive Server settings."""

    service_name: str = "mcp-google-drive-server"
    service_port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database connection (required - no hardcoded credentials)
    database_url: str = os.getenv("DATABASE_URL", "")

    # Cache settings
    connector_cache_ttl: int = int(os.getenv("CONNECTOR_CACHE_TTL", "300"))

    # Google OAuth settings
    google_oauth_client_id: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    google_oauth_client_secret: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    google_oauth_redirect_uri: str = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/v1/connectors/oauth/callback"
    )
    google_oauth_scopes: str = os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/drive.readonly"
    )

    # Encryption key for OAuth tokens (shared with backend)
    credentials_encryption_key: str = os.getenv("CREDENTIALS_ENCRYPTION_KEY", "")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to: postgresql+asyncpg://user:password@host:port/dbname"
            )

    @property
    def google_oauth_scopes_list(self) -> List[str]:
        """Parse scopes string into list."""
        return [s.strip() for s in self.google_oauth_scopes.split() if s.strip()]

    class Config:
        env_file = ".env"


settings = Settings()


# =============================================================================
# Connector Cache
# =============================================================================

class ConnectorCache:
    """In-memory cache for connector configurations."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple[GoogleDriveInstanceConfig, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _cache_key(self, connector_id: UUID) -> str:
        return str(connector_id)

    async def get(
        self,
        connector_id: UUID,
    ) -> Optional[GoogleDriveInstanceConfig]:
        key = self._cache_key(connector_id)
        async with self._lock:
            if key in self._cache:
                config, cached_at = self._cache[key]
                if datetime.utcnow() - cached_at < self._ttl:
                    return config
                del self._cache[key]
        return None

    async def set(
        self,
        connector_id: UUID,
        config: GoogleDriveInstanceConfig
    ) -> None:
        key = self._cache_key(connector_id)
        async with self._lock:
            self._cache[key] = (config, datetime.utcnow())

    async def invalidate(self, connector_id: UUID) -> None:
        key = self._cache_key(connector_id)
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()


_connector_cache = ConnectorCache(ttl_seconds=settings.connector_cache_ttl)


# =============================================================================
# Token Encryption
# =============================================================================

def _get_fernet():
    """Get Fernet instance for token encryption/decryption."""
    import base64
    from cryptography.fernet import Fernet

    key = settings.credentials_encryption_key
    if not key:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY must be configured")
    decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
    if len(decoded) != 32:
        raise ValueError("CREDENTIALS_ENCRYPTION_KEY must decode to 32 bytes")
    return Fernet(key.encode("utf-8"))


def decrypt_token(encrypted_value: Optional[str]) -> Optional[str]:
    """Decrypt an encrypted token string."""
    if not encrypted_value:
        return None
    try:
        fernet = _get_fernet()
        return fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to decrypt token: {e}")
        return None


def encrypt_token(value: Optional[str]) -> Optional[str]:
    """Encrypt a token string."""
    if not value:
        return None
    fernet = _get_fernet()
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


# =============================================================================
# Database Access
# =============================================================================

async def _get_db_connection():
    """Get async database connection."""
    import asyncpg

    db_url = settings.database_url
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    return await asyncpg.connect(db_url)


def _instance_from_row(row, config_data: Dict[str, Any]) -> GoogleDriveInstanceConfig:
    """Build a GoogleDriveInstanceConfig from a DB row + decoded config JSON."""
    access_token = decrypt_token(config_data.get('access_token_encrypted'))
    refresh_token = decrypt_token(config_data.get('refresh_token_encrypted'))

    token_expiry = None
    expiry_str = config_data.get('token_expiry')
    if expiry_str:
        try:
            token_expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    scopes = config_data.get('scopes')
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split() if s.strip()]

    return GoogleDriveInstanceConfig(
        connector_id=row['id'],
        name=row['name'],
        description=row['description'],
        folder_id=config_data.get('folder_id'),
        include_subfolders=config_data.get('include_subfolders', True),
        file_types=config_data.get('file_types'),
        max_file_size_mb=config_data.get('max_file_size_mb', 50),
        access_token=access_token,
        refresh_token=refresh_token,
        token_expiry=token_expiry,
        google_email=config_data.get('google_email'),
        scopes=scopes,
        timeout_seconds=config_data.get('timeout_seconds', 60),
        download_timeout_seconds=config_data.get('download_timeout_seconds', 300),
        max_results=config_data.get('max_results', 100),
        is_active=row['is_active'],
    )


async def load_connector_from_db(
    connector_id: UUID,
) -> Optional[GoogleDriveInstanceConfig]:
    """
    Load Google Drive connector configuration from database.

    Decrypts OAuth tokens from the config JSONB column.
    """
    conn = None
    try:
        conn = await _get_db_connection()

        row = await conn.fetchrow(
            """
            SELECT
                id, name, description, config,
                is_active, connector_type
            FROM connectors
            WHERE id = $1
              AND connector_type = 'google_drive'
              AND is_active = true
            """,
            connector_id,
        )

        if not row:
            logger.warning(
                f"Google Drive connector not found: {connector_id}"
            )
            return None

        raw_config = row['config']
        if isinstance(raw_config, str):
            config_data: Dict[str, Any] = json.loads(raw_config) if raw_config else {}
        else:
            config_data = raw_config or {}

        return _instance_from_row(row, config_data)

    except Exception as e:
        logger.error(f"Failed to load connector from DB: {e}")
        return None
    finally:
        if conn:
            await conn.close()


async def list_all_connectors() -> list[GoogleDriveInstanceConfig]:
    """List all active Google Drive connectors."""
    conn = None
    try:
        conn = await _get_db_connection()

        rows = await conn.fetch(
            """
            SELECT
                id, name, description, config,
                is_active, connector_type
            FROM connectors
            WHERE connector_type = 'google_drive'
              AND is_active = true
            ORDER BY name
            """
        )

        connectors = []
        for row in rows:
            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}

            connectors.append(_instance_from_row(row, config_data))

        return connectors

    except Exception as e:
        logger.error(f"Failed to list connectors: {e}")
        return []
    finally:
        if conn:
            await conn.close()


# =============================================================================
# Public API
# =============================================================================

async def get_connector(
    connector_id: UUID,
) -> Optional[GoogleDriveInstanceConfig]:
    """Get Google Drive connector configuration with caching."""
    cached = await _connector_cache.get(connector_id)
    if cached:
        return cached

    config = await load_connector_from_db(connector_id)
    if config:
        await _connector_cache.set(connector_id, config)

    return config


async def get_all_connectors() -> list[GoogleDriveInstanceConfig]:
    """Get all active Google Drive connectors."""
    return await list_all_connectors()


async def invalidate_connector_cache(
    connector_id: UUID,
) -> None:
    """Invalidate cached connector configuration."""
    await _connector_cache.invalidate(connector_id)


def get_instances() -> Dict[str, GoogleDriveInstanceConfig]:
    """
    Synchronous compatibility function.
    Connectors are loaded dynamically per-request from DB.
    """
    return {}
