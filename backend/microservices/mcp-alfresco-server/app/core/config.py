"""
Configuration for MCP Alfresco Server.

Loads Alfresco connector configurations from the backend database.
Each tenant configures their own Alfresco connector via the UI.

The MCP server connects to PostgreSQL to read connector configurations
from the `connectors` table where connector_type = 'alfresco'.

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
    CONNECTOR_CACHE_TTL: Cache TTL in seconds (default: 300)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class AlfrescoInstanceConfig(BaseModel):
    """Configuration for a single Alfresco instance (from connector)."""

    # Connector identification
    connector_id: UUID = Field(..., description="Connector UUID from database")
    tenant_id: UUID = Field(..., description="Tenant UUID")
    name: str = Field(..., description="Connector name")
    description: Optional[str] = Field(default=None)

    # Connection
    url: str = Field(..., description="Alfresco base URL")
    username: str = Field(..., description="Service account username")
    password: str = Field(..., description="Service account password")

    # API paths (Alfresco 7.x defaults)
    api_path: str = Field(
        default="/alfresco/api/-default-/public/alfresco/versions/1",
        description="REST API base path"
    )
    search_api_path: str = Field(
        default="/alfresco/api/-default-/public/search/versions/1",
        description="Search API base path"
    )

    # Default settings
    default_site_id: Optional[str] = Field(default=None, description="Default site ID")
    default_folder_id: Optional[str] = Field(default=None, description="Default folder node ID")

    # Timeouts
    timeout_seconds: int = Field(default=60, description="Request timeout")
    download_timeout_seconds: int = Field(default=300, description="Download timeout")

    # Limits
    max_results: int = Field(default=100, description="Max search results")
    max_upload_size_mb: int = Field(default=100, description="Max upload size in MB")

    # Status
    is_active: bool = Field(default=True)

    @property
    def api_url(self) -> str:
        """Full API URL."""
        return f"{self.url.rstrip('/')}{self.api_path}"

    @property
    def search_url(self) -> str:
        """Full Search API URL."""
        return f"{self.url.rstrip('/')}{self.search_api_path}"


class Settings(BaseSettings):
    """MCP Alfresco Server settings."""

    service_name: str = "mcp-alfresco-server"
    service_port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database connection (required - no hardcoded credentials)
    database_url: str = os.getenv("DATABASE_URL", "")

    # Cache settings
    connector_cache_ttl: int = int(os.getenv("CONNECTOR_CACHE_TTL", "300"))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to: postgresql+asyncpg://user:password@host:port/dbname"
            )

    class Config:
        env_file = ".env"


settings = Settings()


# =============================================================================
# Connector Cache
# =============================================================================

class ConnectorCache:
    """In-memory cache for connector configurations."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple[AlfrescoInstanceConfig, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _cache_key(self, connector_id: UUID, tenant_id: UUID) -> str:
        """Generate cache key."""
        return f"{tenant_id}:{connector_id}"

    async def get(
        self,
        connector_id: UUID,
        tenant_id: UUID
    ) -> Optional[AlfrescoInstanceConfig]:
        """Get cached connector config."""
        key = self._cache_key(connector_id, tenant_id)
        async with self._lock:
            if key in self._cache:
                config, cached_at = self._cache[key]
                if datetime.utcnow() - cached_at < self._ttl:
                    return config
                # Expired
                del self._cache[key]
        return None

    async def set(
        self,
        connector_id: UUID,
        tenant_id: UUID,
        config: AlfrescoInstanceConfig
    ) -> None:
        """Cache connector config."""
        key = self._cache_key(connector_id, tenant_id)
        async with self._lock:
            self._cache[key] = (config, datetime.utcnow())

    async def invalidate(self, connector_id: UUID, tenant_id: UUID) -> None:
        """Invalidate cached config."""
        key = self._cache_key(connector_id, tenant_id)
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all cached configs."""
        async with self._lock:
            self._cache.clear()


# Global cache instance
_connector_cache = ConnectorCache(ttl_seconds=settings.connector_cache_ttl)


# =============================================================================
# Database Access
# =============================================================================

async def _get_db_connection():
    """Get async database connection."""
    try:
        import asyncpg

        # Convert SQLAlchemy URL to asyncpg format
        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

        return await asyncpg.connect(db_url)
    except ImportError:
        logger.error("asyncpg not installed. Install with: pip install asyncpg")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


async def load_connector_from_db(
    connector_id: UUID,
    tenant_id: UUID
) -> Optional[AlfrescoInstanceConfig]:
    """
    Load Alfresco connector configuration from database.

    Args:
        connector_id: Connector UUID
        tenant_id: Tenant UUID (for validation)

    Returns:
        AlfrescoInstanceConfig or None if not found/not active
    """
    conn = None
    try:
        conn = await _get_db_connection()

        # Query connector with tenant validation
        row = await conn.fetchrow(
            """
            SELECT
                id, tenant_id, name, description, config,
                is_active, connector_type
            FROM connectors
            WHERE id = $1
              AND tenant_id = $2
              AND connector_type = 'alfresco'
              AND is_active = true
            """,
            connector_id,
            tenant_id
        )

        if not row:
            logger.warning(
                f"Alfresco connector not found: {connector_id} for tenant {tenant_id}"
            )
            return None

        # Parse config JSON (may be string or dict depending on DB driver)
        raw_config = row['config']
        if isinstance(raw_config, str):
            config_data: Dict[str, Any] = json.loads(raw_config) if raw_config else {}
        else:
            config_data = raw_config or {}

        # Build instance config
        instance = AlfrescoInstanceConfig(
            connector_id=row['id'],
            tenant_id=row['tenant_id'],
            name=row['name'],
            description=row['description'],
            url=config_data.get('url', ''),
            username=config_data.get('username', ''),
            password=config_data.get('password', ''),
            api_path=config_data.get(
                'api_path',
                '/alfresco/api/-default-/public/alfresco/versions/1'
            ),
            search_api_path=config_data.get(
                'search_api_path',
                '/alfresco/api/-default-/public/search/versions/1'
            ),
            default_site_id=config_data.get('default_site_id'),
            default_folder_id=config_data.get('default_folder_id'),
            timeout_seconds=config_data.get('timeout_seconds', 60),
            download_timeout_seconds=config_data.get('download_timeout_seconds', 300),
            max_results=config_data.get('max_results', 100),
            max_upload_size_mb=config_data.get('max_upload_size_mb', 100),
            is_active=row['is_active'],
        )

        return instance

    except Exception as e:
        logger.error(f"Failed to load connector from DB: {e}")
        return None
    finally:
        if conn:
            await conn.close()


async def list_connectors_for_tenant(tenant_id: UUID) -> list[AlfrescoInstanceConfig]:
    """
    List all active Alfresco connectors for a tenant.

    Args:
        tenant_id: Tenant UUID

    Returns:
        List of AlfrescoInstanceConfig
    """
    conn = None
    try:
        conn = await _get_db_connection()

        rows = await conn.fetch(
            """
            SELECT
                id, tenant_id, name, description, config,
                is_active, connector_type
            FROM connectors
            WHERE tenant_id = $1
              AND connector_type = 'alfresco'
              AND is_active = true
            ORDER BY name
            """,
            tenant_id
        )

        connectors = []
        for row in rows:
            # Parse config JSON (may be string or dict depending on DB driver)
            raw_config = row['config']
            if isinstance(raw_config, str):
                config_data: Dict[str, Any] = json.loads(raw_config) if raw_config else {}
            else:
                config_data = raw_config or {}
            instance = AlfrescoInstanceConfig(
                connector_id=row['id'],
                tenant_id=row['tenant_id'],
                name=row['name'],
                description=row['description'],
                url=config_data.get('url', ''),
                username=config_data.get('username', ''),
                password=config_data.get('password', ''),
                api_path=config_data.get(
                    'api_path',
                    '/alfresco/api/-default-/public/alfresco/versions/1'
                ),
                search_api_path=config_data.get(
                    'search_api_path',
                    '/alfresco/api/-default-/public/search/versions/1'
                ),
                default_site_id=config_data.get('default_site_id'),
                default_folder_id=config_data.get('default_folder_id'),
                timeout_seconds=config_data.get('timeout_seconds', 60),
                download_timeout_seconds=config_data.get('download_timeout_seconds', 300),
                max_results=config_data.get('max_results', 100),
                max_upload_size_mb=config_data.get('max_upload_size_mb', 100),
                is_active=row['is_active'],
            )
            connectors.append(instance)

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
    tenant_id: UUID
) -> Optional[AlfrescoInstanceConfig]:
    """
    Get Alfresco connector configuration with caching.

    Args:
        connector_id: Connector UUID
        tenant_id: Tenant UUID

    Returns:
        AlfrescoInstanceConfig or None
    """
    # Check cache first
    cached = await _connector_cache.get(connector_id, tenant_id)
    if cached:
        return cached

    # Load from database
    config = await load_connector_from_db(connector_id, tenant_id)
    if config:
        await _connector_cache.set(connector_id, tenant_id, config)

    return config


async def get_connectors_for_tenant(tenant_id: UUID) -> list[AlfrescoInstanceConfig]:
    """
    Get all active Alfresco connectors for a tenant.

    Args:
        tenant_id: Tenant UUID

    Returns:
        List of connector configurations
    """
    return await list_connectors_for_tenant(tenant_id)


async def invalidate_connector_cache(
    connector_id: UUID,
    tenant_id: UUID
) -> None:
    """Invalidate cached connector configuration."""
    await _connector_cache.invalidate(connector_id, tenant_id)


def get_instances() -> Dict[str, AlfrescoInstanceConfig]:
    """
    Get configured Alfresco instances (synchronous compatibility function).

    NOTE: This MCP server loads connectors dynamically from the database
    when tools are invoked. This function returns an empty dict for startup
    compatibility - actual connectors are loaded via get_connector() or
    get_connectors_for_tenant() when tools are called with tenant_id.

    Returns:
        Empty dict - connectors are loaded dynamically per-request
    """
    return {}
