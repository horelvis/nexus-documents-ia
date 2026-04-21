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

        # Cache for folder metadata (avoid repeated API calls)
        self._folder_metadata_cache: Dict[str, Dict[str, Any]] = {}

        # Cache for site documentLibrary node IDs
        self._site_doc_library_cache: Dict[str, str] = {}

    async def get_site_document_library_id(self, site_id: str) -> Optional[str]:
        """
        Get the documentLibrary container node ID for a site.

        Uses Alfresco Sites API: GET /sites/{siteId}/containers/documentLibrary

        Args:
            site_id: Alfresco site ID (shortName or UUID)

        Returns:
            Node ID (UUID) of the documentLibrary container, or None if not found
        """
        # Check cache first
        if site_id in self._site_doc_library_cache:
            return self._site_doc_library_cache[site_id]

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.api_path}/sites/{site_id}/containers/documentLibrary"
                )
                response.raise_for_status()
                entry = response.json().get("entry", {})
                node_id = entry.get("id")

                if node_id:
                    self._site_doc_library_cache[site_id] = node_id
                    logger.info(f"[{self.connector_id}] Site {site_id} documentLibrary nodeId: {node_id}")
                    return node_id

                return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"[{self.connector_id}] Site {site_id} not found or no documentLibrary")
            else:
                logger.error(f"[{self.connector_id}] Error getting documentLibrary for site {site_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"[{self.connector_id}] Error getting documentLibrary for site {site_id}: {e}")
            return None

    async def get_folder_metadata(self, folder_id: str) -> Optional[Dict[str, Any]]:
        """
        Get folder metadata with all properties (cached).

        Args:
            folder_id: Alfresco node ID of the folder

        Returns:
            Folder metadata dict with all properties, or None if not found
        """
        # Check cache first
        if folder_id in self._folder_metadata_cache:
            return self._folder_metadata_cache[folder_id]

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
            ) as client:
                response = await client.get(
                    f"{self.base_url}{self.api_path}/nodes/{folder_id}",
                    params={"include": "properties,aspectNames,path"}
                )
                response.raise_for_status()
                entry = response.json().get("entry", {})

                # Parse folder metadata
                folder_meta = self._parse_folder(entry)

                # Cache it
                self._folder_metadata_cache[folder_id] = folder_meta
                return folder_meta

        except Exception as e:
            logger.warning(f"[{self.connector_id}] Failed to get folder metadata for {folder_id}: {e}")
            return None

    async def enrich_document_with_folder_metadata(
        self,
        document: UnifiedDocument,
    ) -> UnifiedDocument:
        """
        Enrich a document with metadata from its parent folders.

        This propagates folder metadata (classifications, registry numbers, etc.)
        to documents inside those folders.

        Args:
            document: UnifiedDocument to enrich

        Returns:
            Document with enriched custom_metadata
        """
        if not document.custom_metadata:
            return document

        parent_id = document.custom_metadata.get("alfresco_parent_id")
        if not parent_id:
            return document

        # Get parent folder metadata
        folder_meta = await self.get_folder_metadata(parent_id)
        if not folder_meta:
            return document

        # Extract custom properties from folder
        folder_custom_props = folder_meta.get("customProperties", {})
        if folder_custom_props:
            # Add folder properties to document metadata
            document.custom_metadata["parent_folder_properties"] = folder_custom_props
            document.custom_metadata["parent_folder_type"] = folder_meta.get("nodeType")
            document.custom_metadata["parent_folder_aspects"] = folder_meta.get("aspectNames", [])

            # Also merge key folder properties into alfresco_properties for easier access
            # Prefix with "folder_" to distinguish from document properties
            alfresco_props = document.custom_metadata.get("alfresco_properties", {})
            for prop_name, prop_value in folder_custom_props.items():
                if prop_value is not None:
                    alfresco_props[f"folder_{prop_name}"] = prop_value
            document.custom_metadata["alfresco_properties"] = alfresco_props

        return document

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get Basic authentication headers."""
        auth_str = f"{self.alfresco_config.username}:{self.alfresco_config.password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()
        return {
            "Authorization": f"Basic {auth_bytes}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _build_afts_query(
        self,
        modified_after: Optional[datetime] = None,
        document_library_node_id: Optional[str] = None,
    ) -> str:
        """
        Build AFTS query from configuration.

        Args:
            modified_after: Add date filter for incremental sync
            document_library_node_id: If provided, uses ANCESTOR instead of SITE filter

        Returns:
            Complete AFTS query string
        """
        # Build base query from config
        afts_query = self.alfresco_config.build_sync_afts_query()

        # If we have the documentLibrary nodeId, replace SITE filter with ANCESTOR
        # ANCESTOR is more precise and only searches within that specific folder tree
        if document_library_node_id:
            # Remove SITE filter if present (we'll use ANCESTOR instead)
            import re
            afts_query = re.sub(r'\s*AND\s*SITE:"[^"]*"', '', afts_query)
            afts_query = re.sub(r'SITE:"[^"]*"\s*AND\s*', '', afts_query)
            afts_query = re.sub(r'\s*AND\s*PATH:"//cm:documentLibrary//\*"', '', afts_query)

            # Add ANCESTOR filter for the documentLibrary folder
            ancestor_filter = f'ANCESTOR:"workspace://SpacesStore/{document_library_node_id}"'
            afts_query = f"({afts_query}) AND {ancestor_filter}"

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

        Uses Alfresco Sites API to get the documentLibrary node ID when a site
        is configured, then uses ANCESTOR filter for precise searching within
        that container only.

        Args:
            modified_after: Only return documents modified after this date
            skip: Number of results to skip
            max_items: Maximum results to return

        Returns:
            Tuple of (documents, has_more)
        """
        # If a site is configured, get the documentLibrary node ID for precise filtering
        document_library_node_id = None
        if self.alfresco_config.default_site_id and not self.alfresco_config.default_folder_id:
            document_library_node_id = await self.get_site_document_library_id(
                self.alfresco_config.default_site_id
            )
            if not document_library_node_id:
                logger.warning(
                    f"[{self.connector_id}] Could not get documentLibrary for site "
                    f"{self.alfresco_config.default_site_id}, falling back to SITE filter"
                )

        afts_query = await self._build_afts_query(modified_after, document_library_node_id)
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

    async def list_folders(
        self,
        parent_node_id: str = "-root-",
        skip: int = 0,
        max_items: int = 100,
        include_properties: bool = True,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        List folders with all their properties using Public API.

        Uses /nodes/{nodeId}/children endpoint with isFolder filter.

        Args:
            parent_node_id: Parent folder node ID (default: -root-)
            skip: Number of results to skip
            max_items: Maximum results to return
            include_properties: Include all properties in response

        Returns:
            Tuple of (folders list, has_more)
        """
        logger.info(f"[{self.connector_id}] Listing folders under {parent_node_id}")

        include_params = "properties,path,aspectNames" if include_properties else "path"

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=float(self.timeout), write=30.0, pool=5.0)
            ) as client:
                response = await client.get(
                    f"{self.base_url}/alfresco/api/-default-/public/alfresco/versions/1/nodes/{parent_node_id}/children",
                    params={
                        "where": "(isFolder=true)",
                        "include": include_params,
                        "skipCount": skip,
                        "maxItems": max_items,
                    }
                )
                response.raise_for_status()
                result = response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ConnectorAuthError("Authentication failed", self.connector_id, {"status_code": 401})
            raise ConnectorConnectionError(
                f"Alfresco API error: {e.response.status_code}",
                self.connector_id,
                {"status_code": e.response.status_code}
            )
        except httpx.ConnectError as e:
            raise ConnectorConnectionError(f"Cannot connect to Alfresco: {e}", self.connector_id)

        entries = result.get("list", {}).get("entries", [])
        pagination = result.get("list", {}).get("pagination", {})
        has_more = pagination.get("hasMoreItems", False)

        folders = []
        for entry_wrapper in entries:
            entry = entry_wrapper.get("entry", {})
            folder = self._parse_folder(entry)
            folders.append(folder)

        logger.info(f"[{self.connector_id}] Found {len(folders)} folders, has_more={has_more}")
        return folders, has_more

    def _parse_folder(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse folder entry with all properties.

        Args:
            entry: Folder entry from API response

        Returns:
            Parsed folder dict with all properties
        """
        node_id = entry.get("id")
        name = entry.get("name", "")
        properties = entry.get("properties", {})
        path_info = entry.get("path", {})

        # Build full path
        path_elements = path_info.get("elements", [])
        path_parts = [elem.get("name", "") for elem in path_elements]
        full_path = "/" + "/".join(path_parts) if path_parts else "/"

        # Extract ALL custom properties (exp:*, pmreg:*, etc.)
        custom_properties = {}
        standard_props = {"cm:name", "cm:title", "cm:description", "cm:created", "cm:modified", "cm:creator", "cm:modifier"}

        for prop_name, prop_value in properties.items():
            if prop_name in standard_props or prop_name.startswith("sys:"):
                continue
            if prop_value is not None:
                custom_properties[prop_name] = prop_value

        return {
            "id": node_id,
            "name": name,
            "path": full_path,
            "nodeType": entry.get("nodeType"),
            "aspectNames": entry.get("aspectNames", []),
            "title": properties.get("cm:title"),
            "description": properties.get("cm:description"),
            "created": properties.get("cm:created"),
            "modified": properties.get("cm:modified"),
            "creator": properties.get("cm:creator"),
            "modifier": properties.get("cm:modifier"),
            # ALL custom properties from content model
            "customProperties": custom_properties,
            "parentId": entry.get("parentId"),
            "isFolder": True,
        }

    async def list_all_folders_recursive(
        self,
        root_node_id: str = "-root-",
        max_depth: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Recursively list ALL folders starting from root with their properties.

        Args:
            root_node_id: Starting folder node ID
            max_depth: Maximum recursion depth

        Returns:
            Flat list of all folders with their properties
        """
        all_folders = []

        async def _crawl_folder(node_id: str, current_depth: int):
            if current_depth > max_depth:
                return

            skip = 0
            has_more = True

            while has_more:
                folders, has_more = await self.list_folders(
                    parent_node_id=node_id,
                    skip=skip,
                    max_items=100,
                    include_properties=True,
                )

                for folder in folders:
                    folder["depth"] = current_depth
                    all_folders.append(folder)

                    # Recurse into subfolder
                    await _crawl_folder(folder["id"], current_depth + 1)

                skip += len(folders)

        await _crawl_folder(root_node_id, 0)
        logger.info(f"[{self.connector_id}] Found {len(all_folders)} folders total (recursive)")
        return all_folders

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
        # No fallback: in single-tenant mode the caller must provide owner_id.
        owner_id = self._owner_id

        # Extract ALL custom properties (exp:*, pmreg:*, custom:*, etc.)
        # Exclude system properties (sys:*) and standard cm:* that are already mapped
        custom_properties = {}
        standard_cm_props = {
            "cm:name", "cm:title", "cm:description", "cm:created",
            "cm:modified", "cm:creator", "cm:modifier", "cm:content"
        }

        for prop_name, prop_value in properties.items():
            # Skip standard properties already mapped elsewhere
            if prop_name in standard_cm_props:
                continue
            # Skip system properties (usually not useful for search)
            if prop_name.startswith("sys:"):
                continue
            # Include everything else (exp:*, pmreg:*, custom:*, cm:author, etc.)
            if prop_value is not None:
                # Convert datetime strings to ISO format for JSON compatibility
                if isinstance(prop_value, str) and "T" in prop_value and "Z" in prop_value:
                    custom_properties[prop_name] = prop_value
                else:
                    custom_properties[prop_name] = prop_value

        # Extract parent folder info from path elements
        # Each path element can contain folder metadata (classification, etc.)
        parent_folders_metadata = []
        for path_elem in path_elements:
            elem_id = path_elem.get("id")
            elem_name = path_elem.get("name", "")
            # Skip root and system folders
            if elem_name and elem_id and elem_name not in {"Company Home", "Sites"}:
                parent_folders_metadata.append({
                    "id": elem_id,
                    "name": elem_name,
                    "nodeType": path_elem.get("nodeType"),
                    "aspectNames": path_elem.get("aspectNames", []),
                })

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
                # Alfresco system info
                "alfresco_aspects": entry.get("aspectNames", []),
                "alfresco_node_type": entry.get("nodeType"),
                "alfresco_parent_id": entry.get("parentId"),
                "alfresco_creator": properties.get("cm:creator"),
                "alfresco_modifier": properties.get("cm:modifier"),
                # ALL custom properties from content model (exp:*, pmreg:*, etc.)
                "alfresco_properties": custom_properties,
                # Parent folder chain (for propagating folder metadata to documents)
                "alfresco_parent_folders": parent_folders_metadata,
            },
        )

    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Alfresco-specific rate limits."""
        return {
            "requests_per_second": 5,  # Conservative for Alfresco
            "concurrent_downloads": 2,
            "retry_after_ms": 2000,
        }

    # =========================================================================
    # Data Learning Methods - Content Model Discovery
    # =========================================================================

    async def fetch_content_model(self) -> Dict[str, Any]:
        """
        Fetch the content model from Alfresco Public REST API.

        Returns a dict with:
        - types: List of content type definitions with properties
        - aspects: List of aspect definitions with properties
        - properties: Dict of ALL property definitions (by qualified name)
        - association_types: Dict of association type definitions
        - custom_namespaces: List of custom namespace prefixes found (exp:, pmreg:, etc.)

        Uses the Public REST API endpoints:
        - GET /alfresco/api/-default-/public/alfresco/versions/1/types?include=properties
        - GET /alfresco/api/-default-/public/alfresco/versions/1/aspects?include=properties

        For older Alfresco versions, falls back to search-based discovery.
        """
        logger.info(f"[{self.connector_id}] Fetching content model from Alfresco Public API")

        result = {
            "types": [],
            "aspects": [],
            "properties": {},
            "association_types": {},
            "custom_namespaces": set(),
        }

        # Standard Alfresco namespaces to exclude (we only want custom ones)
        standard_prefixes = {"cm", "sys", "app", "usr", "ver", "fm", "dl", "ia", "lnk", "st", "wf", "bpm"}

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
            ) as client:
                # Fetch ALL types with properties using Public API
                all_types = []
                skip_count = 0
                max_items = 100
                has_more = True

                while has_more:
                    try:
                        types_response = await client.get(
                            f"{self.base_url}/alfresco/api/-default-/public/alfresco/versions/1/types",
                            params={
                                "skipCount": skip_count,
                                "maxItems": max_items,
                                "include": "properties,mandatoryAspects,associations"
                            }
                        )
                        types_response.raise_for_status()
                        types_data = types_response.json()

                        entries = types_data.get("list", {}).get("entries", [])
                        pagination = types_data.get("list", {}).get("pagination", {})

                        for entry in entries:
                            type_def = self._parse_model_entry(entry.get("entry", {}))
                            all_types.append(type_def)

                            # Track custom namespaces
                            prefix = type_def.get("id", "").split(":")[0] if ":" in type_def.get("id", "") else None
                            if prefix and prefix not in standard_prefixes:
                                result["custom_namespaces"].add(prefix)

                            # Add properties to global dict
                            for prop in type_def.get("properties", []):
                                prop_id = prop.get("id")
                                if prop_id:
                                    result["properties"][prop_id] = prop

                        has_more = pagination.get("hasMoreItems", False)
                        skip_count += len(entries)

                        if not entries:
                            break

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            logger.warning(f"[{self.connector_id}] Types API not available, using fallback")
                            all_types = await self._discover_types_from_search()
                            break
                        raise

                result["types"] = all_types
                logger.info(f"[{self.connector_id}] Discovered {len(result['types'])} content types")

                # Fetch ALL aspects with properties
                all_aspects = []
                skip_count = 0
                has_more = True

                while has_more:
                    try:
                        aspects_response = await client.get(
                            f"{self.base_url}/alfresco/api/-default-/public/alfresco/versions/1/aspects",
                            params={
                                "skipCount": skip_count,
                                "maxItems": max_items,
                                "include": "properties,associations"
                            }
                        )
                        aspects_response.raise_for_status()
                        aspects_data = aspects_response.json()

                        entries = aspects_data.get("list", {}).get("entries", [])
                        pagination = aspects_data.get("list", {}).get("pagination", {})

                        for entry in entries:
                            aspect_def = self._parse_model_entry(entry.get("entry", {}))
                            all_aspects.append(aspect_def)

                            # Track custom namespaces
                            prefix = aspect_def.get("id", "").split(":")[0] if ":" in aspect_def.get("id", "") else None
                            if prefix and prefix not in standard_prefixes:
                                result["custom_namespaces"].add(prefix)

                            # Add properties to global dict
                            for prop in aspect_def.get("properties", []):
                                prop_id = prop.get("id")
                                if prop_id:
                                    result["properties"][prop_id] = prop

                        has_more = pagination.get("hasMoreItems", False)
                        skip_count += len(entries)

                        if not entries:
                            break

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            logger.warning(f"[{self.connector_id}] Aspects API not available")
                            all_aspects = await self._discover_aspects_from_search()
                            break
                        raise

                result["aspects"] = all_aspects
                logger.info(f"[{self.connector_id}] Discovered {len(result['aspects'])} aspects")

                # Extract association types from types that have them
                for type_def in result["types"]:
                    for assoc in type_def.get("associations", []):
                        assoc_name = assoc.get("name") or assoc.get("id")
                        if assoc_name:
                            result["association_types"][assoc_name] = assoc

                # Convert set to list for JSON serialization
                result["custom_namespaces"] = list(result["custom_namespaces"])

                logger.info(
                    f"[{self.connector_id}] Content model discovery complete: "
                    f"{len(result['types'])} types, {len(result['aspects'])} aspects, "
                    f"{len(result['properties'])} properties, "
                    f"custom namespaces: {result['custom_namespaces']}"
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"[{self.connector_id}] Failed to fetch content model: {e}")
            raise ConnectorConnectionError(
                f"Failed to fetch content model: HTTP {e.response.status_code}",
                self.connector_id,
                {"status_code": e.response.status_code}
            )
        except Exception as e:
            logger.error(f"[{self.connector_id}] Error fetching content model: {e}")
            raise

        return result

    def _parse_model_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a single type or aspect entry from the Public API.

        Args:
            entry: Type or aspect entry from API response

        Returns:
            Normalized definition dict
        """
        definition = {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "description": entry.get("description"),
            "parentId": entry.get("parentId"),
            "isContainer": entry.get("isContainer", False),
            "isArchive": entry.get("isArchive", False),
            "properties": [],
            "mandatoryAspects": entry.get("mandatoryAspects", []),
            "associations": [],
        }

        # Parse properties
        for prop in entry.get("properties", []):
            definition["properties"].append({
                "id": prop.get("id"),
                "title": prop.get("title"),
                "description": prop.get("description"),
                "dataType": prop.get("dataType"),
                "isMultiValued": prop.get("isMultiValued", False),
                "isMandatory": prop.get("isMandatory", False),
                "isMandatoryEnforced": prop.get("isMandatoryEnforced", False),
                "isProtected": prop.get("isProtected", False),
                "defaultValue": prop.get("defaultValue"),
                "constraints": prop.get("constraints", []),
            })

        # Parse associations
        for assoc in entry.get("associations", []):
            definition["associations"].append({
                "id": assoc.get("id"),
                "title": assoc.get("title"),
                "description": assoc.get("description"),
                "isChild": assoc.get("isChild", False),
                "isProtected": assoc.get("isProtected", False),
                "source": assoc.get("source"),
                "target": assoc.get("target"),
            })

        return definition

    def _parse_model_entries(self, entries: List[Dict]) -> List[Dict[str, Any]]:
        """
        Parse model API response entries into structured definitions.

        Args:
            entries: List of entry wrappers from Alfresco Model API

        Returns:
            List of parsed type/aspect definitions
        """
        parsed = []
        for entry_wrapper in entries:
            entry = entry_wrapper.get("entry", {})
            definition = {
                "name": entry.get("id") or entry.get("name"),
                "title": entry.get("title"),
                "description": entry.get("description"),
                "parent": entry.get("parentId"),
                "properties": [],
                "associations": [],
            }

            # Parse properties
            for prop in entry.get("properties", []):
                definition["properties"].append({
                    "name": prop.get("id") or prop.get("name"),
                    "title": prop.get("title"),
                    "description": prop.get("description"),
                    "data_type": prop.get("dataType"),
                    "is_mandatory": prop.get("isMandatory", False),
                    "is_multi_valued": prop.get("isMultiValued", False),
                    "default_value": prop.get("defaultValue"),
                    "constraints": prop.get("constraints", []),
                })

            # Parse associations
            for assoc in entry.get("associations", []):
                definition["associations"].append({
                    "name": assoc.get("id") or assoc.get("name"),
                    "title": assoc.get("title"),
                    "source_type": assoc.get("sourceId"),
                    "target_type": assoc.get("targetId"),
                    "is_child": assoc.get("isChild", False),
                    "is_mandatory": assoc.get("isMandatory", False),
                    "is_source_mandatory": assoc.get("isSourceMandatory", False),
                    "is_target_mandatory": assoc.get("isTargetMandatory", False),
                })

            parsed.append(definition)

        return parsed

    async def _discover_types_from_search(self) -> List[Dict[str, Any]]:
        """
        Fallback: Discover content types by sampling documents via search.

        Returns list of type definitions discovered from actual documents.
        """
        logger.info(f"[{self.connector_id}] Discovering types via search sampling")

        type_counts = {}

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0)
            ) as client:
                # Search for documents to sample types
                search_body = {
                    "query": {"query": 'TYPE:"cm:content"', "language": "afts"},
                    "paging": {"maxItems": 500, "skipCount": 0},
                    "include": ["properties", "aspectNames"],
                }

                response = await client.post(
                    f"{self.base_url}{self.search_api_path}/search",
                    json=search_body
                )
                response.raise_for_status()
                result = response.json()

                entries = result.get("list", {}).get("entries", [])
                for entry_wrapper in entries:
                    entry = entry_wrapper.get("entry", {})
                    node_type = entry.get("nodeType", "cm:content")

                    if node_type not in type_counts:
                        type_counts[node_type] = {
                            "name": node_type,
                            "count": 0,
                            "sample_properties": set(),
                        }

                    type_counts[node_type]["count"] += 1

                    # Collect property names
                    for prop_name in entry.get("properties", {}).keys():
                        type_counts[node_type]["sample_properties"].add(prop_name)

        except Exception as e:
            logger.error(f"[{self.connector_id}] Error sampling types: {e}")

        # Convert to type definitions
        types = []
        for type_name, info in type_counts.items():
            types.append({
                "name": type_name,
                "title": type_name.split(":")[-1].title() if ":" in type_name else type_name,
                "description": f"Discovered via sampling ({info['count']} documents)",
                "parent": "cm:content" if type_name != "cm:content" else None,
                "properties": [{"name": p, "data_type": "unknown"} for p in info["sample_properties"]],
                "associations": [],
            })

        return types

    async def _discover_aspects_from_search(self) -> List[Dict[str, Any]]:
        """
        Fallback: Discover aspects by sampling documents.

        Returns list of aspect definitions discovered from actual documents.
        """
        logger.info(f"[{self.connector_id}] Discovering aspects via search sampling")

        aspect_counts = {}

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0)
            ) as client:
                search_body = {
                    "query": {"query": 'TYPE:"cm:content"', "language": "afts"},
                    "paging": {"maxItems": 500, "skipCount": 0},
                    "include": ["aspectNames"],
                }

                response = await client.post(
                    f"{self.base_url}{self.search_api_path}/search",
                    json=search_body
                )
                response.raise_for_status()
                result = response.json()

                entries = result.get("list", {}).get("entries", [])
                for entry_wrapper in entries:
                    entry = entry_wrapper.get("entry", {})
                    aspect_names = entry.get("aspectNames", [])

                    for aspect_name in aspect_names:
                        if aspect_name not in aspect_counts:
                            aspect_counts[aspect_name] = {
                                "name": aspect_name,
                                "count": 0,
                            }
                        aspect_counts[aspect_name]["count"] += 1

        except Exception as e:
            logger.error(f"[{self.connector_id}] Error sampling aspects: {e}")

        # Convert to aspect definitions
        aspects = []
        for aspect_name, info in aspect_counts.items():
            aspects.append({
                "name": aspect_name,
                "title": aspect_name.split(":")[-1].title() if ":" in aspect_name else aspect_name,
                "description": f"Discovered via sampling ({info['count']} documents)",
                "properties": [],  # We don't know properties without the Model API
                "associations": [],
            })

        return aspects

    async def fetch_folder_tree(
        self,
        root_node_id: str = "-root-",
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """
        Fetch folder hierarchy from Alfresco.

        Args:
            root_node_id: Starting node ID (default "-root-" for company home)
            max_depth: Maximum folder depth to traverse

        Returns:
            Dict with folder tree structure including:
            - id: Node ID
            - name: Folder name
            - path: Full path
            - children: List of child folders
            - document_count: Number of documents in folder
        """
        logger.info(f"[{self.connector_id}] Fetching folder tree from {root_node_id}")

        async def fetch_children(node_id: str, current_depth: int, path: str) -> Dict[str, Any]:
            """Recursively fetch folder children."""
            if current_depth > max_depth:
                return None

            try:
                async with httpx.AsyncClient(
                    headers=self._get_auth_headers(),
                    timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
                ) as client:
                    # Get folder info
                    node_response = await client.get(
                        f"{self.base_url}{self.api_path}/nodes/{node_id}",
                        params={"include": "properties,path"}
                    )
                    node_response.raise_for_status()
                    node_data = node_response.json().get("entry", {})

                    folder_name = node_data.get("name", "")
                    folder_path = path + "/" + folder_name if path else folder_name

                    # Get children (folders only)
                    children_response = await client.get(
                        f"{self.base_url}{self.api_path}/nodes/{node_id}/children",
                        params={
                            "where": "(isFolder=true)",
                            "include": "properties",
                            "maxItems": 100,
                        }
                    )
                    children_response.raise_for_status()
                    children_data = children_response.json()

                    # Count documents in folder
                    doc_count_response = await client.get(
                        f"{self.base_url}{self.api_path}/nodes/{node_id}/children",
                        params={
                            "where": "(isFile=true)",
                            "skipCount": 0,
                            "maxItems": 1,
                        }
                    )
                    doc_count_response.raise_for_status()
                    doc_count_data = doc_count_response.json()
                    doc_count = doc_count_data.get("list", {}).get("pagination", {}).get("totalItems", 0)

                    folder_node = {
                        "id": node_id,
                        "name": folder_name,
                        "path": folder_path,
                        "document_count": doc_count,
                        "properties": node_data.get("properties", {}),
                        "children": [],
                    }

                    # Recursively fetch children
                    child_entries = children_data.get("list", {}).get("entries", [])
                    for child_wrapper in child_entries:
                        child = child_wrapper.get("entry", {})
                        child_node = await fetch_children(
                            child.get("id"),
                            current_depth + 1,
                            folder_path
                        )
                        if child_node:
                            folder_node["children"].append(child_node)

                    return folder_node

            except httpx.HTTPStatusError as e:
                logger.error(f"[{self.connector_id}] Error fetching folder {node_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"[{self.connector_id}] Unexpected error for folder {node_id}: {e}")
                return None

        # Start recursive fetch
        tree = await fetch_children(root_node_id, 0, "")
        return tree or {"id": root_node_id, "name": "root", "children": [], "document_count": 0}

    async def fetch_node_associations(self, node_id: str) -> Dict[str, List[str]]:
        """
        Fetch associations (relationships) for a document node.

        Args:
            node_id: Alfresco node UUID

        Returns:
            Dict mapping association type to list of target node IDs:
            {
                "cm:references": ["node-id-1", "node-id-2"],
                "peer:related": ["node-id-3"],
            }
        """
        logger.info(f"[{self.connector_id}] Fetching associations for node {node_id}")

        associations = {}

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)
            ) as client:
                # Get source associations (this node → other nodes)
                source_response = await client.get(
                    f"{self.base_url}{self.api_path}/nodes/{node_id}/sources",
                    params={"include": "properties", "maxItems": 100}
                )
                if source_response.status_code == 200:
                    source_data = source_response.json()
                    for entry_wrapper in source_data.get("list", {}).get("entries", []):
                        entry = entry_wrapper.get("entry", {})
                        assoc_type = entry.get("association", {}).get("assocType", "unknown")
                        target_id = entry.get("id")
                        if target_id:
                            if assoc_type not in associations:
                                associations[assoc_type] = []
                            associations[assoc_type].append(target_id)

                # Get target associations (other nodes → this node)
                target_response = await client.get(
                    f"{self.base_url}{self.api_path}/nodes/{node_id}/targets",
                    params={"include": "properties", "maxItems": 100}
                )
                if target_response.status_code == 200:
                    target_data = target_response.json()
                    for entry_wrapper in target_data.get("list", {}).get("entries", []):
                        entry = entry_wrapper.get("entry", {})
                        assoc_type = entry.get("association", {}).get("assocType", "unknown")
                        target_id = entry.get("id")
                        if target_id:
                            # Mark as incoming association
                            incoming_type = f"incoming:{assoc_type}"
                            if incoming_type not in associations:
                                associations[incoming_type] = []
                            associations[incoming_type].append(target_id)

        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:  # 404 is OK - no associations
                logger.error(f"[{self.connector_id}] Error fetching associations: {e}")
        except Exception as e:
            logger.error(f"[{self.connector_id}] Unexpected error fetching associations: {e}")

        return associations

    async def fetch_document_with_associations(
        self,
        node_id: str,
    ) -> Tuple[Optional[UnifiedDocument], Dict[str, List[str]]]:
        """
        Fetch a document with its associations in a single call.

        Args:
            node_id: Alfresco node UUID

        Returns:
            Tuple of (UnifiedDocument, associations dict)
        """
        document = await self.get_document_by_id(node_id)
        associations = await self.fetch_node_associations(node_id)
        return document, associations
