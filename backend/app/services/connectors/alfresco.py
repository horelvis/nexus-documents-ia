"""
Alfresco Connector Adapter

Implements ConnectorAdapter for Alfresco Content Services (7.x).
Uses Alfresco REST API v1 and Search API with AFTS queries.

Alfresco API Documentation:
https://docs.alfresco.com/content-services/latest/develop/rest-api-guide/

Key Features:
- AFTS (Alfresco Full Text Search) for flexible filtering
- Incremental sync via cm:modified date
- Site and path-based filtering
- MIME type filtering

Refactored from the original AlfrescoSyncService in connector_tasks.py
to use the unified adapter pattern.
"""
import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx

from app.db.models import Connector
from app.schemas.connector import AlfrescoConfig
from app.schemas.unified_document import (
    ConnectorType,
    HealthCheckResult,
    IndexingStatus,
    UnifiedDocument,
)

from .base import (
    ConnectorAdapter,
    ConnectorConnectionError,
    ConnectorAuthError,
    ConnectorRateLimitError,
)

logger = logging.getLogger(__name__)


class AlfrescoAdapter(ConnectorAdapter):
    """
    Alfresco Content Services adapter.

    Connects to Alfresco 7.x via REST API and Search API.
    Supports service account authentication with AFTS query filtering.

    Example config:
        {
            "url": "https://alfresco.company.com",
            "username": "admin",
            "password": "secret",
            "default_site_id": "gdapm",
            "afts_mime_types": ["application/pdf", "application/msword"],
            "afts_path_filter": "/app:company_home/st:sites/cm:gdapm//*"
        }
    """

    connector_type = ConnectorType.ALFRESCO

    def __init__(self, connector: Connector, config: Dict[str, Any]):
        """
        Initialize Alfresco adapter.

        Args:
            connector: Connector model from database
            config: Alfresco configuration (parsed from connector.config)
        """
        super().__init__(connector, config)

        # Parse and validate config
        self.alfresco_config = AlfrescoConfig(**config)
        self.base_url = self.alfresco_config.url.rstrip("/")
        self.api_path = self.alfresco_config.api_path
        self.search_api_path = self.alfresco_config.search_api_path
        self.timeout = self.alfresco_config.timeout_seconds
        self.download_timeout = self.alfresco_config.download_timeout_seconds

        # Get owner ID (admin who created the connector)
        self._owner_id = connector.created_by_id

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get Basic authentication headers."""
        auth_str = f"{self.alfresco_config.username}:{self.alfresco_config.password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {auth_bytes}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _build_afts_query(self, modified_after: Optional[datetime] = None) -> str:
        """
        Build AFTS query from configuration.

        Args:
            modified_after: Add date filter for incremental sync

        Returns:
            Complete AFTS query string
        """
        afts_query = self.alfresco_config.build_sync_afts_query()

        # Add date filter for incremental sync
        if modified_after:
            date_str = modified_after.strftime("%Y-%m-%dT%H:%M:%S")
            afts_query = f"({afts_query}) AND @cm\\:modified:['{date_str}' TO MAX]"

        return afts_query

    async def list_documents(
        self,
        modified_after: Optional[datetime] = None,
        skip: int = 0,
        max_items: int = 100,
    ) -> Tuple[List[UnifiedDocument], bool]:
        """
        Search for documents using AFTS query.

        Args:
            modified_after: Only return documents modified after this date
            skip: Number of results to skip
            max_items: Maximum results to return

        Returns:
            Tuple of (documents, has_more)
        """
        afts_query = self._build_afts_query(modified_after)
        logger.info(f"[{self.connector_id}] Executing AFTS query: {afts_query}")

        search_body = {
            "query": {
                "query": afts_query,
                "language": "afts"
            },
            "paging": {
                "maxItems": max_items,
                "skipCount": skip
            },
            "include": ["properties", "path", "aspectNames"],
            "sort": [{"type": "FIELD", "field": "cm:modified", "ascending": True}],
        }

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.timeout),
                    write=30.0,
                    pool=5.0
                )
            ) as client:
                response = await client.post(
                    f"{self.base_url}{self.search_api_path}/search",
                    json=search_body
                )
                response.raise_for_status()
                result = response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ConnectorAuthError(
                    "Authentication failed",
                    self.connector_id,
                    {"status_code": 401}
                )
            elif e.response.status_code == 429:
                raise ConnectorRateLimitError(
                    "Rate limited by Alfresco",
                    self.connector_id,
                    retry_after_seconds=60
                )
            raise ConnectorConnectionError(
                f"Alfresco API error: {e.response.status_code}",
                self.connector_id,
                {"status_code": e.response.status_code, "body": e.response.text}
            )
        except httpx.ConnectError as e:
            raise ConnectorConnectionError(
                f"Cannot connect to Alfresco: {e}",
                self.connector_id
            )

        # Parse results
        entries = result.get("list", {}).get("entries", [])
        pagination = result.get("list", {}).get("pagination", {})
        has_more = pagination.get("hasMoreItems", False)

        documents = []
        for entry_wrapper in entries:
            entry = entry_wrapper.get("entry", {})
            try:
                doc = self._parse_document(entry)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Error parsing document {entry.get('id')}: {e}")

        logger.info(f"[{self.connector_id}] Found {len(documents)} documents, has_more={has_more}")
        return documents, has_more

    async def download_content(self, document: UnifiedDocument) -> bytes:
        """
        Download document content from Alfresco.

        Args:
            document: UnifiedDocument with external_id set to node UUID

        Returns:
            bytes: File content
        """
        node_id = document.external_id

        logger.info(
            f"[{self.connector_id}] Downloading {document.filename} "
            f"({document.size_bytes} bytes) from node {node_id}"
        )

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.download_timeout),
                    write=30.0,
                    pool=5.0
                )
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.api_path}/nodes/{node_id}/content"
                )
                response.raise_for_status()
                return response.content

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise FileNotFoundError(
                    f"Document {node_id} not found in Alfresco"
                )
            elif e.response.status_code == 401:
                raise ConnectorAuthError(
                    "Authentication failed",
                    self.connector_id
                )
            raise ConnectorConnectionError(
                f"Download failed: {e.response.status_code}",
                self.connector_id
            )
        except httpx.ReadTimeout:
            raise TimeoutError(
                f"Download timeout after {self.download_timeout}s for {document.filename}"
            )

    async def health_check(self) -> HealthCheckResult:
        """
        Check Alfresco connectivity and permissions.

        Tests:
        1. API endpoint reachable
        2. Credentials valid
        3. Search API accessible
        """
        start_time = time.time()

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
            ) as client:
                # Test 1: Check API endpoint
                response = await client.get(
                    f"{self.base_url}{self.api_path}/people/-me-"
                )
                response.raise_for_status()
                user_info = response.json()

                # Test 2: Verify search API access
                search_response = await client.post(
                    f"{self.base_url}{self.search_api_path}/search",
                    json={
                        "query": {"query": 'TYPE:"cm:content"', "language": "afts"},
                        "paging": {"maxItems": 1}
                    }
                )
                search_response.raise_for_status()

                elapsed_ms = (time.time() - start_time) * 1000

                return HealthCheckResult(
                    is_healthy=True,
                    status="healthy",
                    message=f"Connected as {user_info.get('entry', {}).get('id', 'unknown')}",
                    details={
                        "user": user_info.get("entry", {}).get("id"),
                        "display_name": user_info.get("entry", {}).get("displayName"),
                        "api_version": "v1",
                        "search_api": "available",
                    },
                    response_time_ms=elapsed_ms,
                )

        except httpx.HTTPStatusError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            if e.response.status_code == 401:
                return HealthCheckResult(
                    is_healthy=False,
                    status="unhealthy",
                    message="Authentication failed - invalid credentials",
                    details={"status_code": 401},
                    response_time_ms=elapsed_ms,
                )
            return HealthCheckResult(
                is_healthy=False,
                status="unhealthy",
                message=f"API error: HTTP {e.response.status_code}",
                details={"status_code": e.response.status_code},
                response_time_ms=elapsed_ms,
            )

        except httpx.ConnectError as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                is_healthy=False,
                status="unhealthy",
                message=f"Connection failed: {e}",
                details={"error": str(e)},
                response_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(
                is_healthy=False,
                status="unhealthy",
                message=f"Health check failed: {e}",
                details={"error": str(e)},
                response_time_ms=elapsed_ms,
            )

    async def get_document_by_id(self, external_id: str) -> Optional[UnifiedDocument]:
        """
        Get a single document by node ID.

        Args:
            external_id: Alfresco node UUID

        Returns:
            UnifiedDocument if found
        """
        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.api_path}/nodes/{external_id}",
                    params={"include": "properties,path"}
                )
                response.raise_for_status()
                result = response.json()
                return self._parse_document(result.get("entry", {}))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Error getting document {external_id}: {e}")
            return None

    def _parse_document(self, entry: Dict[str, Any]) -> UnifiedDocument:
        """
        Parse Alfresco search result entry into UnifiedDocument.

        Args:
            entry: Single document entry from search results

        Returns:
            UnifiedDocument with metadata populated
        """
        node_id = entry.get("id")
        name = entry.get("name", "")
        properties = entry.get("properties", {})
        path_info = entry.get("path", {})
        content_info = entry.get("content", {})

        # Build external path
        path_elements = path_info.get("elements", [])
        path_parts = [elem.get("name", "") for elem in path_elements]
        external_path = "/" + "/".join(path_parts) if path_parts else "/"

        # Build external URL
        external_url = (
            f"{self.base_url}/share/page/document-details?"
            f"nodeRef=workspace://SpacesStore/{node_id}"
        )

        # Extract file extension
        file_extension = None
        if name and "." in name:
            file_extension = name.rsplit(".", 1)[-1].lower()

        # Parse dates
        source_created = None
        if properties.get("cm:created"):
            try:
                source_created = datetime.fromisoformat(
                    properties["cm:created"].replace("Z", "+00:00")
                )
            except Exception:
                pass

        source_modified = None
        if properties.get("cm:modified"):
            try:
                source_modified = datetime.fromisoformat(
                    properties["cm:modified"].replace("Z", "+00:00")
                )
            except Exception:
                pass

        # Use owner from connector (service account = docs belong to admin)
        owner_id = self._owner_id or self.tenant_id  # Fallback to tenant_id

        return self._create_unified_document(
            external_id=node_id,
            filename=name,
            owner_id=owner_id,
            external_url=external_url,
            external_path=external_path,
            title=properties.get("cm:title") or name,
            description=properties.get("cm:description"),
            mime_type=content_info.get("mimeType"),
            file_extension=file_extension,
            size_bytes=content_info.get("sizeInBytes", 0),
            source_created_at=source_created,
            source_modified_at=source_modified,
            is_tenant_public=True,  # Service account = public to tenant
            indexing_status=IndexingStatus.PENDING,
            custom_metadata={
                "alfresco_aspects": entry.get("aspectNames", []),
                "alfresco_node_type": entry.get("nodeType"),
                "alfresco_creator": properties.get("cm:creator"),
                "alfresco_modifier": properties.get("cm:modifier"),
            },
        )

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Alfresco-specific rate limits."""
        return {
            "requests_per_second": 5,  # Conservative for Alfresco
            "concurrent_downloads": 2,
            "retry_after_ms": 2000,
        }
