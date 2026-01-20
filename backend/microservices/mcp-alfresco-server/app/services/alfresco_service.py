"""
Alfresco 7.x REST API Client Service.

Implements communication with Alfresco Content Services REST API.

API Documentation:
https://docs.alfresco.com/content-services/latest/develop/rest-api-guide/

Endpoints used:
- /nodes/{nodeId} - Node CRUD operations
- /nodes/{nodeId}/children - List folder contents
- /nodes/{nodeId}/content - Download content
- /nodes/{nodeId}/versions - Version history
- /search - AFTS search queries
"""

import base64
import mimetypes
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from ..core.config import AlfrescoInstanceConfig


class AlfrescoNode(BaseModel):
    """Represents an Alfresco node (document or folder)."""

    id: str
    name: str
    node_type: str
    is_folder: bool
    is_file: bool
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None
    content_size: Optional[int] = None
    mime_type: Optional[str] = None
    parent_id: Optional[str] = None
    path: Optional[str] = None
    properties: Dict[str, Any] = {}


class AlfrescoVersion(BaseModel):
    """Represents a document version."""

    id: str
    version_label: str
    is_major: bool
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    content_size: Optional[int] = None
    comment: Optional[str] = None


class SearchResult(BaseModel):
    """Search result with pagination info."""

    nodes: List[AlfrescoNode]
    total: int
    has_more: bool
    skip: int
    max_items: int


class HealthCheckResult(BaseModel):
    """Result of health check."""

    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    api_version: Optional[str] = None
    authenticated_user: Optional[str] = None
    repository_id: Optional[str] = None
    edition: Optional[str] = None  # Community/Enterprise
    sites_accessible: int = 0
    search_api_working: bool = False
    response_time_ms: Optional[float] = None
    details: Dict[str, Any] = {}


class AlfrescoService:
    """
    Alfresco 7.x REST API Client.

    Provides methods for interacting with Alfresco Content Services,
    including search, download, upload, and metadata operations.
    """

    def __init__(self, config: AlfrescoInstanceConfig):
        """
        Initialize Alfresco service.

        Args:
            config: Alfresco instance configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with authentication."""
        if self._client is None or self._client.is_closed:
            # Basic auth for Alfresco
            auth_str = f"{self.config.username}:{self.config.password}"
            auth_bytes = base64.b64encode(auth_str.encode()).decode()

            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Basic {auth_bytes}",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.config.timeout_seconds),
                    write=float(self.config.timeout_seconds),
                    pool=5.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _parse_node(self, entry: Dict[str, Any]) -> AlfrescoNode:
        """Parse API response into AlfrescoNode."""
        node = entry.get("entry", entry)

        created_at = None
        if node.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(
                    node["createdAt"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        modified_at = None
        if node.get("modifiedAt"):
            try:
                modified_at = datetime.fromisoformat(
                    node["modifiedAt"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        content = node.get("content", {})
        path_info = node.get("path", {})
        path_elements = path_info.get("elements", [])
        path = "/" + "/".join(e.get("name", "") for e in path_elements) if path_elements else None

        return AlfrescoNode(
            id=node["id"],
            name=node["name"],
            node_type=node.get("nodeType", "cm:content"),
            is_folder=node.get("isFolder", False),
            is_file=node.get("isFile", True),
            created_at=created_at,
            modified_at=modified_at,
            created_by=node.get("createdByUser", {}).get("displayName"),
            modified_by=node.get("modifiedByUser", {}).get("displayName"),
            content_size=content.get("sizeInBytes"),
            mime_type=content.get("mimeType"),
            parent_id=node.get("parentId"),
            path=path,
            properties=node.get("properties", {}),
        )

    def _parse_version(self, entry: Dict[str, Any]) -> AlfrescoVersion:
        """Parse API response into AlfrescoVersion."""
        version = entry.get("entry", entry)

        created_at = None
        if version.get("modifiedAt"):
            try:
                created_at = datetime.fromisoformat(
                    version["modifiedAt"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        content = version.get("content", {})

        return AlfrescoVersion(
            id=version["id"],
            version_label=version.get("versionLabel", version["id"]),
            is_major=version.get("isMajorVersion", True),
            created_at=created_at,
            created_by=version.get("modifiedByUser", {}).get("displayName"),
            content_size=content.get("sizeInBytes"),
            comment=version.get("versionComment"),
        )

    async def search(
        self,
        query: str,
        skip: int = 0,
        max_items: int = 100,
        include_path: bool = True,
        node_type: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> SearchResult:
        """
        Search documents using AFTS (Alfresco Full Text Search).

        AFTS supports:
        - Full-text search: "financial report 2024"
        - Property search: cm:name:"budget.pdf"
        - Type filtering: TYPE:"cm:content"
        - Path filtering: PATH:"/app:company_home/..."

        Args:
            query: AFTS query string
            skip: Number of results to skip (pagination)
            max_items: Maximum results to return
            include_path: Include path information in results
            node_type: Filter by node type (e.g., "cm:content", "cm:folder")
            site_id: Restrict search to a specific site

        Returns:
            SearchResult with nodes and pagination info
        """
        client = await self._get_client()

        # Build AFTS query
        afts_query = query

        # Add type filter if specified
        if node_type:
            afts_query = f"({afts_query}) AND TYPE:\"{node_type}\""

        # Add site filter if specified
        if site_id:
            afts_query = f"({afts_query}) AND SITE:\"{site_id}\""
        elif self.config.default_site_id:
            afts_query = f"({afts_query}) AND SITE:\"{self.config.default_site_id}\""

        # Build request body
        body = {
            "query": {
                "query": afts_query,
                "language": "afts",
            },
            "paging": {
                "skipCount": skip,
                "maxItems": min(max_items, self.config.max_results),
            },
            "include": ["properties", "allowableOperations"],
        }

        if include_path:
            body["include"].append("path")

        response = await client.post(
            f"{self.config.search_url}/search",
            json=body,
        )
        response.raise_for_status()

        data = response.json()
        entries = data.get("list", {}).get("entries", [])
        pagination = data.get("list", {}).get("pagination", {})

        nodes = [self._parse_node(e) for e in entries]

        return SearchResult(
            nodes=nodes,
            total=pagination.get("totalItems", len(nodes)),
            has_more=pagination.get("hasMoreItems", False),
            skip=skip,
            max_items=max_items,
        )

    async def get_node(
        self,
        node_id: str,
        include_path: bool = True,
    ) -> AlfrescoNode:
        """
        Get node metadata by ID.

        Args:
            node_id: Node ID (UUID or special alias like -root-, -my-)
            include_path: Include path information

        Returns:
            AlfrescoNode with metadata
        """
        client = await self._get_client()

        params = {"include": "properties,allowableOperations"}
        if include_path:
            params["include"] += ",path"

        response = await client.get(
            f"{self.config.api_url}/nodes/{node_id}",
            params=params,
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def list_children(
        self,
        folder_id: str = "-root-",
        skip: int = 0,
        max_items: int = 100,
        include_path: bool = False,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> SearchResult:
        """
        List contents of a folder.

        Args:
            folder_id: Folder node ID (default: -root- for Company Home)
            skip: Number of results to skip
            max_items: Maximum results to return
            include_path: Include path information
            where: Filter clause (e.g., "(isFile=true)")
            order_by: Order by clause (e.g., "name ASC")

        Returns:
            SearchResult with child nodes
        """
        client = await self._get_client()

        # Use default folder if configured
        if folder_id == "-root-" and self.config.default_folder_id:
            folder_id = self.config.default_folder_id

        params = {
            "skipCount": skip,
            "maxItems": min(max_items, self.config.max_results),
            "include": "properties",
        }

        if include_path:
            params["include"] += ",path"

        if where:
            params["where"] = where

        if order_by:
            params["orderBy"] = order_by

        response = await client.get(
            f"{self.config.api_url}/nodes/{folder_id}/children",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        entries = data.get("list", {}).get("entries", [])
        pagination = data.get("list", {}).get("pagination", {})

        nodes = [self._parse_node(e) for e in entries]

        return SearchResult(
            nodes=nodes,
            total=pagination.get("totalItems", len(nodes)),
            has_more=pagination.get("hasMoreItems", False),
            skip=skip,
            max_items=max_items,
        )

    async def download_content(
        self,
        node_id: str,
        version_id: Optional[str] = None,
    ) -> Tuple[bytes, str, Optional[str]]:
        """
        Download document content.

        Args:
            node_id: Document node ID
            version_id: Specific version ID (optional)

        Returns:
            Tuple of (content bytes, filename, mime_type)
        """
        client = await self._get_client()

        # Get node info first for filename and mime type
        node = await self.get_node(node_id, include_path=False)

        # Build URL based on whether version is specified
        if version_id:
            url = f"{self.config.api_url}/nodes/{node_id}/versions/{version_id}/content"
        else:
            url = f"{self.config.api_url}/nodes/{node_id}/content"

        # Use longer timeout for downloads
        download_timeout = httpx.Timeout(
            connect=10.0,
            read=float(self.config.download_timeout_seconds),
            write=30.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(
            headers=client.headers,
            timeout=download_timeout,
        ) as download_client:
            response = await download_client.get(url)
            response.raise_for_status()

            return response.content, node.name, node.mime_type

    async def upload_content(
        self,
        parent_id: str,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        overwrite: bool = False,
        properties: Optional[Dict[str, Any]] = None,
        major_version: bool = True,
        comment: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Upload a new document.

        Args:
            parent_id: Parent folder node ID
            filename: Name for the new document
            content: File content as bytes
            mime_type: MIME type (auto-detected if not provided)
            overwrite: If True, update existing file with same name
            properties: Additional properties to set
            major_version: If True, creates major version
            comment: Version comment

        Returns:
            Created AlfrescoNode
        """
        client = await self._get_client()

        # Auto-detect MIME type if not provided
        if not mime_type:
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Check file size limit
        size_mb = len(content) / (1024 * 1024)
        if size_mb > self.config.max_upload_size_mb:
            raise ValueError(
                f"File size {size_mb:.1f}MB exceeds limit of {self.config.max_upload_size_mb}MB"
            )

        # Use default folder if specified
        if parent_id == "-root-" and self.config.default_folder_id:
            parent_id = self.config.default_folder_id

        # Build multipart form data
        files = {
            "filedata": (filename, content, mime_type),
        }

        data = {
            "name": filename,
            "nodeType": "cm:content",
            "autoRename": str(not overwrite).lower(),
            "majorVersion": str(major_version).lower(),
        }

        if comment:
            data["comment"] = comment

        # Add custom properties if provided
        if properties:
            for key, value in properties.items():
                data[f"cm:{key}" if not key.startswith("cm:") else key] = value

        # Remove Authorization from headers for multipart (will use auth)
        auth_str = f"{self.config.username}:{self.config.password}"
        auth_bytes = base64.b64encode(auth_str.encode()).decode()

        response = await client.post(
            f"{self.config.api_url}/nodes/{parent_id}/children",
            files=files,
            data=data,
            headers={"Authorization": f"Basic {auth_bytes}"},
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def update_content(
        self,
        node_id: str,
        content: bytes,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        major_version: bool = False,
        comment: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Update existing document content (creates new version).

        Args:
            node_id: Document node ID
            content: New file content
            filename: New filename (optional)
            mime_type: MIME type (auto-detected if not provided)
            major_version: If True, creates major version
            comment: Version comment

        Returns:
            Updated AlfrescoNode
        """
        client = await self._get_client()

        # Get existing node for filename if not provided
        if not filename:
            existing = await self.get_node(node_id, include_path=False)
            filename = existing.name

        # Auto-detect MIME type if not provided
        if not mime_type:
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Check file size limit
        size_mb = len(content) / (1024 * 1024)
        if size_mb > self.config.max_upload_size_mb:
            raise ValueError(
                f"File size {size_mb:.1f}MB exceeds limit of {self.config.max_upload_size_mb}MB"
            )

        params = {
            "majorVersion": str(major_version).lower(),
        }

        if comment:
            params["comment"] = comment

        response = await client.put(
            f"{self.config.api_url}/nodes/{node_id}/content",
            content=content,
            params=params,
            headers={
                "Content-Type": mime_type,
            },
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def get_versions(
        self,
        node_id: str,
        skip: int = 0,
        max_items: int = 100,
    ) -> List[AlfrescoVersion]:
        """
        Get version history for a document.

        Args:
            node_id: Document node ID
            skip: Number of results to skip
            max_items: Maximum results to return

        Returns:
            List of AlfrescoVersion objects
        """
        client = await self._get_client()

        params = {
            "skipCount": skip,
            "maxItems": max_items,
        }

        response = await client.get(
            f"{self.config.api_url}/nodes/{node_id}/versions",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        entries = data.get("list", {}).get("entries", [])

        return [self._parse_version(e) for e in entries]

    async def move_node(
        self,
        node_id: str,
        target_parent_id: str,
        new_name: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Move a node to a different folder.

        Args:
            node_id: Node ID to move
            target_parent_id: Target folder node ID
            new_name: New name (optional, keeps original if not specified)

        Returns:
            Moved AlfrescoNode
        """
        client = await self._get_client()

        body = {
            "targetParentId": target_parent_id,
        }

        if new_name:
            body["name"] = new_name

        response = await client.post(
            f"{self.config.api_url}/nodes/{node_id}/move",
            json=body,
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def copy_node(
        self,
        node_id: str,
        target_parent_id: str,
        new_name: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Copy a node to a folder.

        Args:
            node_id: Node ID to copy
            target_parent_id: Target folder node ID
            new_name: New name (optional, auto-generates if not specified)

        Returns:
            New AlfrescoNode (the copy)
        """
        client = await self._get_client()

        body = {
            "targetParentId": target_parent_id,
        }

        if new_name:
            body["name"] = new_name

        response = await client.post(
            f"{self.config.api_url}/nodes/{node_id}/copy",
            json=body,
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def delete_node(
        self,
        node_id: str,
        permanent: bool = False,
    ) -> bool:
        """
        Delete a node.

        Args:
            node_id: Node ID to delete
            permanent: If True, permanently delete (skip trash)

        Returns:
            True if deleted successfully
        """
        client = await self._get_client()

        params = {}
        if permanent:
            params["permanent"] = "true"

        response = await client.delete(
            f"{self.config.api_url}/nodes/{node_id}",
            params=params,
        )
        response.raise_for_status()

        return True

    async def update_properties(
        self,
        node_id: str,
        properties: Dict[str, Any],
        name: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Update node properties.

        Args:
            node_id: Node ID
            properties: Properties to update (key-value pairs)
            name: New name (optional)

        Returns:
            Updated AlfrescoNode
        """
        client = await self._get_client()

        body = {
            "properties": properties,
        }

        if name:
            body["name"] = name

        response = await client.put(
            f"{self.config.api_url}/nodes/{node_id}",
            json=body,
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def create_folder(
        self,
        parent_id: str,
        name: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> AlfrescoNode:
        """
        Create a new folder.

        Args:
            parent_id: Parent folder node ID
            name: Folder name
            title: Folder title (cm:title property)
            description: Folder description (cm:description property)

        Returns:
            Created AlfrescoNode
        """
        client = await self._get_client()

        body = {
            "name": name,
            "nodeType": "cm:folder",
        }

        properties = {}
        if title:
            properties["cm:title"] = title
        if description:
            properties["cm:description"] = description

        if properties:
            body["properties"] = properties

        response = await client.post(
            f"{self.config.api_url}/nodes/{parent_id}/children",
            json=body,
        )
        response.raise_for_status()

        return self._parse_node(response.json())

    async def get_sites(
        self,
        skip: int = 0,
        max_items: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List available sites.

        Args:
            skip: Number of results to skip
            max_items: Maximum results to return

        Returns:
            List of site information dictionaries
        """
        client = await self._get_client()

        params = {
            "skipCount": skip,
            "maxItems": max_items,
        }

        response = await client.get(
            f"{self.config.api_url}/sites",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        entries = data.get("list", {}).get("entries", [])

        return [e.get("entry", e) for e in entries]

    async def get_site_doclib(self, site_id: str) -> Optional[str]:
        """
        Get the document library folder ID for a site.

        Args:
            site_id: Site ID

        Returns:
            Document library folder node ID or None
        """
        client = await self._get_client()

        try:
            response = await client.get(
                f"{self.config.api_url}/sites/{site_id}/containers/documentLibrary",
            )
            response.raise_for_status()

            data = response.json()
            return data.get("entry", {}).get("id")
        except httpx.HTTPStatusError:
            return None

    async def health_check(self) -> HealthCheckResult:
        """
        Perform comprehensive health check on Alfresco connection.

        Tests:
        1. Authentication by getting current user info
        2. API access by fetching repository info
        3. Search API by running a simple AFTS query
        4. Site access by listing available sites

        Returns:
            HealthCheckResult with detailed status
        """
        import time
        start_time = time.time()
        details: Dict[str, Any] = {}
        issues: List[str] = []

        authenticated_user = None
        api_version = None
        repository_id = None
        edition = None
        sites_count = 0
        search_working = False

        try:
            client = await self._get_client()

            # Test 1: Get current user (tests authentication)
            try:
                response = await client.get(f"{self.config.api_url}/people/-me-")
                response.raise_for_status()
                user_data = response.json().get("entry", {})
                authenticated_user = user_data.get("displayName") or user_data.get("id")
                details["user_id"] = user_data.get("id")
                details["user_email"] = user_data.get("email")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    return HealthCheckResult(
                        status="unhealthy",
                        message="Authentication failed: Invalid credentials",
                        response_time_ms=(time.time() - start_time) * 1000,
                        details={"error": str(e), "status_code": e.response.status_code}
                    )
                issues.append(f"Failed to get user info: {e.response.status_code}")

            # Test 2: Get repository info (tests API version)
            try:
                response = await client.get(
                    f"{self.config.url}/alfresco/api/discovery"
                )
                if response.status_code == 200:
                    discovery = response.json().get("entry", {}).get("repository", {})
                    api_version = discovery.get("version", {}).get("display")
                    repository_id = discovery.get("id")
                    edition = discovery.get("edition")
                    details["repository_version"] = api_version
                    details["repository_edition"] = edition
                    details["repository_id"] = repository_id
            except Exception as e:
                # Discovery endpoint might not be available in all versions
                details["discovery_error"] = str(e)

            # Test 3: Test Search API with simple query
            try:
                search_body = {
                    "query": {
                        "query": "TYPE:\"cm:folder\"",
                        "language": "afts"
                    },
                    "paging": {"maxItems": 1}
                }
                response = await client.post(
                    f"{self.config.search_url}/search",
                    json=search_body
                )
                response.raise_for_status()
                search_data = response.json()
                search_working = True
                details["search_api_status"] = "working"
                details["search_test_results"] = search_data.get("list", {}).get("pagination", {}).get("totalItems", 0)
            except httpx.HTTPStatusError as e:
                issues.append(f"Search API failed: {e.response.status_code}")
                details["search_api_status"] = f"error: {e.response.status_code}"

            # Test 4: List sites (tests site access)
            try:
                sites = await self.get_sites(max_items=50)
                sites_count = len(sites)
                details["sites_available"] = [s.get("id") for s in sites[:10]]  # First 10

                # If default site configured, verify it exists
                if self.config.default_site_id:
                    site_exists = any(
                        s.get("id") == self.config.default_site_id
                        for s in sites
                    )
                    details["default_site_accessible"] = site_exists
                    if not site_exists:
                        issues.append(f"Default site '{self.config.default_site_id}' not found")
            except Exception as e:
                issues.append(f"Failed to list sites: {e}")

            # Determine overall status
            response_time = (time.time() - start_time) * 1000

            if not authenticated_user:
                status = "unhealthy"
                message = "Failed to authenticate with Alfresco"
            elif not search_working:
                status = "degraded"
                message = f"Connected but Search API not working. Issues: {'; '.join(issues)}"
            elif issues:
                status = "degraded"
                message = f"Connected with issues: {'; '.join(issues)}"
            else:
                status = "healthy"
                message = f"Successfully connected to Alfresco as {authenticated_user}"

            return HealthCheckResult(
                status=status,
                message=message,
                api_version=api_version,
                authenticated_user=authenticated_user,
                repository_id=repository_id,
                edition=edition,
                sites_accessible=sites_count,
                search_api_working=search_working,
                response_time_ms=response_time,
                details=details
            )

        except httpx.ConnectError as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection failed: Unable to reach {self.config.url}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e), "url": self.config.url}
            )
        except httpx.TimeoutException as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Connection timeout after {self.config.timeout_seconds}s",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e), "timeout": self.config.timeout_seconds}
            )
        except Exception as e:
            return HealthCheckResult(
                status="unhealthy",
                message=f"Unexpected error: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e), "error_type": type(e).__name__}
            )

    async def search_with_filters(
        self,
        query: str = "*",
        skip: int = 0,
        max_items: int = 100,
        include_path: bool = True,
        node_type: Optional[str] = None,
        aspects: Optional[List[str]] = None,
        site_id: Optional[str] = None,
        path_filter: Optional[str] = None,
        mime_types: Optional[List[str]] = None,
        modified_after: Optional[datetime] = None,
        modified_before: Optional[datetime] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
    ) -> SearchResult:
        """
        Advanced search with AFTS filters.

        AFTS Filter Examples:
        - TYPE:"cm:content" - Filter by node type
        - ASPECT:"cm:titled" - Filter by aspect
        - PATH:"/app:company_home/st:sites/cm:mysite//*" - Filter by path
        - @cm\\:content.mimetype:"application/pdf" - Filter by MIME type

        Args:
            query: Text query or "*" for all
            skip: Pagination offset
            max_items: Maximum results
            include_path: Include path in results
            node_type: Filter by node type (e.g., "cm:content", "cm:document")
            aspects: List of aspects to filter (e.g., ["cm:titled", "cm:versionable"])
            site_id: Restrict to specific site
            path_filter: AFTS path pattern (e.g., "/app:company_home/st:sites/cm:mysite//*")
            mime_types: List of MIME types (e.g., ["application/pdf", "application/msword"])
            modified_after: Filter by modification date
            modified_before: Filter by modification date
            created_after: Filter by creation date
            created_before: Filter by creation date

        Returns:
            SearchResult with matching nodes
        """
        client = await self._get_client()

        # Build AFTS query with filters
        afts_parts = []

        # Base query
        if query and query != "*":
            afts_parts.append(f"({query})")
        else:
            afts_parts.append("ISNODE:T")  # Match all nodes

        # Type filter
        if node_type:
            afts_parts.append(f'TYPE:"{node_type}"')

        # Aspect filters
        if aspects:
            for aspect in aspects:
                afts_parts.append(f'ASPECT:"{aspect}"')

        # Site filter
        effective_site = site_id or self.config.default_site_id
        if effective_site:
            afts_parts.append(f'SITE:"{effective_site}"')

        # Path filter
        if path_filter:
            afts_parts.append(f'PATH:"{path_filter}"')

        # MIME type filter
        if mime_types:
            mime_conditions = " OR ".join(
                f'@cm\\:content.mimetype:"{mt}"' for mt in mime_types
            )
            afts_parts.append(f"({mime_conditions})")

        # Date filters
        if modified_after:
            afts_parts.append(
                f'@cm\\:modified:["{modified_after.isoformat()}Z" TO MAX]'
            )
        if modified_before:
            afts_parts.append(
                f'@cm\\:modified:[MIN TO "{modified_before.isoformat()}Z"]'
            )
        if created_after:
            afts_parts.append(
                f'@cm\\:created:["{created_after.isoformat()}Z" TO MAX]'
            )
        if created_before:
            afts_parts.append(
                f'@cm\\:created:[MIN TO "{created_before.isoformat()}Z"]'
            )

        # Join all parts with AND
        afts_query = " AND ".join(afts_parts)

        # Build request body
        body = {
            "query": {
                "query": afts_query,
                "language": "afts",
            },
            "paging": {
                "skipCount": skip,
                "maxItems": min(max_items, self.config.max_results),
            },
            "include": ["properties", "allowableOperations"],
            "sort": [{"type": "FIELD", "field": "cm:modified", "ascending": False}]
        }

        if include_path:
            body["include"].append("path")

        response = await client.post(
            f"{self.config.search_url}/search",
            json=body,
        )
        response.raise_for_status()

        data = response.json()
        entries = data.get("list", {}).get("entries", [])
        pagination = data.get("list", {}).get("pagination", {})

        nodes = [self._parse_node(e) for e in entries]

        return SearchResult(
            nodes=nodes,
            total=pagination.get("totalItems", len(nodes)),
            has_more=pagination.get("hasMoreItems", False),
            skip=skip,
            max_items=max_items,
        )
