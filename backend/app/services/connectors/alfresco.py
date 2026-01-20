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

    # =========================================================================
    # Data Learning Methods - Content Model Discovery
    # =========================================================================

    async def fetch_content_model(self) -> Dict[str, Any]:
        """
        Fetch the content model from Alfresco Dictionary API.

        Returns a dict with:
        - types: List of content type definitions
        - aspects: List of aspect definitions
        - properties: Dict of property definitions (by name)
        - association_types: Dict of association type definitions

        Uses the Discovery API endpoints:
        - GET /alfresco/api/-default-/public/model/versions/1/types
        - GET /alfresco/api/-default-/public/model/versions/1/aspects

        For older Alfresco versions, falls back to the CMIS API or sample-based inference.
        """
        logger.info(f"[{self.connector_id}] Fetching content model from Alfresco")

        result = {
            "types": [],
            "aspects": [],
            "properties": {},
            "association_types": {},
        }

        try:
            async with httpx.AsyncClient(
                headers=self._get_auth_headers(),
                timeout=httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0)
            ) as client:
                # Try to fetch types from Model API (Alfresco 7.x+)
                try:
                    types_response = await client.get(
                        f"{self.base_url}/alfresco/api/-default-/public/model/versions/1/types",
                        params={"skipCount": 0, "maxItems": 500}
                    )
                    types_response.raise_for_status()
                    types_data = types_response.json()
                    result["types"] = self._parse_model_entries(
                        types_data.get("list", {}).get("entries", [])
                    )
                    logger.info(f"[{self.connector_id}] Discovered {len(result['types'])} content types")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"[{self.connector_id}] Model API not available, using fallback")
                        result["types"] = await self._discover_types_from_search()
                    else:
                        raise

                # Fetch aspects
                try:
                    aspects_response = await client.get(
                        f"{self.base_url}/alfresco/api/-default-/public/model/versions/1/aspects",
                        params={"skipCount": 0, "maxItems": 500}
                    )
                    aspects_response.raise_for_status()
                    aspects_data = aspects_response.json()
                    result["aspects"] = self._parse_model_entries(
                        aspects_data.get("list", {}).get("entries", [])
                    )
                    logger.info(f"[{self.connector_id}] Discovered {len(result['aspects'])} aspects")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"[{self.connector_id}] Aspects API not available")
                        result["aspects"] = await self._discover_aspects_from_search()
                    else:
                        raise

                # Build property dictionary from types and aspects
                for type_def in result["types"]:
                    for prop in type_def.get("properties", []):
                        prop_name = prop.get("name") or prop.get("id")
                        if prop_name:
                            result["properties"][prop_name] = prop

                for aspect_def in result["aspects"]:
                    for prop in aspect_def.get("properties", []):
                        prop_name = prop.get("name") or prop.get("id")
                        if prop_name:
                            result["properties"][prop_name] = prop

                # Extract association types from types that have them
                for type_def in result["types"]:
                    for assoc in type_def.get("associations", []):
                        assoc_name = assoc.get("name") or assoc.get("id")
                        if assoc_name:
                            result["association_types"][assoc_name] = assoc

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
