"""
Microsoft Graph API v1.0 Client Service for OneDrive.

Provides methods for interacting with OneDrive for Business:
- List files in folders (recursive)
- Download files (direct — no export needed, unlike Google Workspace)
- Search files
- Get metadata
- Create folders, upload, move, delete

Uses httpx for async HTTP calls to the MS Graph REST API.

API Reference: https://learn.microsoft.com/en-us/graph/api/resources/onedrive
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from ..core.config import OneDriveInstanceConfig

logger = logging.getLogger(__name__)

# Microsoft Graph API base URL
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

# Supported MIME types for indexing
SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/plain": "txt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint": "ppt",
}


class OneDriveItem(BaseModel):
    """Represents a OneDrive item (file or folder)."""
    id: str
    name: str
    mime_type: Optional[str] = None
    is_folder: bool = False
    size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    web_url: Optional[str] = None
    parent_path: Optional[str] = None
    drive_id: Optional[str] = None


class OneDriveService:
    """
    Microsoft Graph API v1.0 async client for OneDrive.

    Uses httpx AsyncClient with Bearer token auth.
    Token refresh is handled by the OAuthService.
    """

    def __init__(self, access_token: str, config: OneDriveInstanceConfig):
        self.access_token = access_token
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def _drive_base(self) -> str:
        """Base URL for drive operations, using specific drive_id if configured."""
        if self.config.drive_id:
            return f"{GRAPH_API_BASE}/drives/{self.config.drive_id}"
        return f"{GRAPH_API_BASE}/me/drive"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.config.timeout_seconds),
                    write=30.0,
                    pool=5.0,
                ),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _parse_item(self, item: Dict[str, Any]) -> OneDriveItem:
        """Parse Graph API item response into OneDriveItem."""
        created_at = None
        if item.get("createdDateTime"):
            try:
                created_at = datetime.fromisoformat(
                    item["createdDateTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        modified_at = None
        if item.get("lastModifiedDateTime"):
            try:
                modified_at = datetime.fromisoformat(
                    item["lastModifiedDateTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # OneDrive uses facets instead of MIME types for folder detection
        is_folder = "folder" in item

        # MIME type from file facet
        mime_type = None
        if item.get("file") and item["file"].get("mimeType"):
            mime_type = item["file"]["mimeType"]

        # Parent path
        parent_path = None
        if item.get("parentReference") and item["parentReference"].get("path"):
            parent_path = item["parentReference"]["path"]

        # Drive ID
        drive_id = None
        if item.get("parentReference") and item["parentReference"].get("driveId"):
            drive_id = item["parentReference"]["driveId"]

        return OneDriveItem(
            id=item["id"],
            name=item.get("name", ""),
            mime_type=mime_type,
            is_folder=is_folder,
            size_bytes=item.get("size"),
            created_at=created_at,
            modified_at=modified_at,
            web_url=item.get("webUrl"),
            parent_path=parent_path,
            drive_id=drive_id,
        )

    async def list_items(
        self,
        folder_id: Optional[str] = None,
        include_subfolders: bool = True,
        file_types: Optional[List[str]] = None,
        max_results: int = 1000,
    ) -> List[OneDriveItem]:
        """
        List all items in a folder (and optionally subfolders).

        Uses BFS to traverse folder tree.
        folder_id: OneDrive item ID. None or "root" means the drive root.
        """
        client = await self._get_client()
        items: List[OneDriveItem] = []

        effective_folder = folder_id or "root"
        folders_to_process = [effective_folder]

        while folders_to_process and len(items) < max_results:
            current_folder = folders_to_process.pop(0)

            # Build URL for children
            if current_folder == "root":
                url = f"{self._drive_base}/root/children"
            else:
                url = f"{self._drive_base}/items/{current_folder}/children"

            # Paginate through all children
            while url and len(items) < max_results:
                params = {
                    "$top": 200,
                    "$select": "id,name,file,folder,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference",
                }
                # Only use params on the first request; @odata.nextLink includes them
                if url.startswith("http") and "@" not in url:
                    response = await client.get(url, params=params)
                else:
                    # nextLink is a full URL with params already embedded
                    response = await client.get(url)

                response.raise_for_status()
                data = response.json()

                for raw_item in data.get("value", []):
                    if "folder" in raw_item:
                        if include_subfolders:
                            folders_to_process.append(raw_item["id"])
                    else:
                        # Filter by file type if specified
                        if file_types:
                            file_mime = raw_item.get("file", {}).get("mimeType", "")
                            ext = SUPPORTED_MIME_TYPES.get(file_mime)
                            if ext and ext not in file_types:
                                continue
                        items.append(self._parse_item(raw_item))

                url = data.get("@odata.nextLink")

        return items

    async def search_items(
        self,
        query: str,
        folder_id: Optional[str] = None,
        max_results: int = 50,
    ) -> List[OneDriveItem]:
        """Search items by query string."""
        client = await self._get_client()

        if folder_id and folder_id != "root":
            url = f"{self._drive_base}/items/{folder_id}/search(q='{query}')"
        else:
            url = f"{self._drive_base}/root/search(q='{query}')"

        params = {
            "$top": min(max_results, 200),
            "$select": "id,name,file,folder,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference",
        }

        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        return [self._parse_item(item) for item in data.get("value", [])]

    async def get_item_metadata(self, item_id: str) -> OneDriveItem:
        """Get detailed metadata for an item."""
        client = await self._get_client()

        params = {
            "$select": "id,name,file,folder,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference,description,shared",
        }

        response = await client.get(
            f"{self._drive_base}/items/{item_id}",
            params=params,
        )
        response.raise_for_status()
        return self._parse_item(response.json())

    async def download_item(
        self,
        item_id: str,
    ) -> Tuple[bytes, str]:
        """
        Download item content.

        OneDrive files are native Office formats — no export/conversion needed.
        The /content endpoint returns a 302 redirect to a temporary download URL.

        Returns:
            Tuple of (content bytes, mime_type)
        """
        # Get metadata first to know the mime type
        client = await self._get_client()
        meta_resp = await client.get(
            f"{self._drive_base}/items/{item_id}",
            params={"$select": "file"},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        mime_type = meta.get("file", {}).get("mimeType", "application/octet-stream")

        # Download content (follows 302 redirect automatically)
        download_timeout = httpx.Timeout(
            connect=10.0,
            read=float(self.config.download_timeout_seconds),
            write=30.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=download_timeout,
            follow_redirects=True,
        ) as dl_client:
            response = await dl_client.get(
                f"{self._drive_base}/items/{item_id}/content",
            )
            response.raise_for_status()
            return response.content, mime_type

    async def get_folder_tree(
        self,
        folder_id: Optional[str] = None,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """Get folder tree structure recursively."""
        client = await self._get_client()
        effective_folder = folder_id or "root"

        async def _get_children(fid: str, depth: int) -> Dict[str, Any]:
            # Get folder info
            if fid == "root":
                resp = await client.get(
                    f"{self._drive_base}/root",
                    params={"$select": "id,name"},
                )
            else:
                resp = await client.get(
                    f"{self._drive_base}/items/{fid}",
                    params={"$select": "id,name"},
                )
            resp.raise_for_status()
            folder_info = resp.json()

            result = {
                "id": folder_info["id"],
                "name": folder_info.get("name", "root"),
                "children": [],
            }

            if depth >= max_depth:
                return result

            # List children that are folders
            if fid == "root":
                children_url = f"{self._drive_base}/root/children"
            else:
                children_url = f"{self._drive_base}/items/{fid}/children"

            resp = await client.get(
                children_url,
                params={
                    "$filter": "folder ne null",
                    "$select": "id,name,folder",
                    "$top": 200,
                },
            )
            resp.raise_for_status()

            for child in resp.json().get("value", []):
                if "folder" in child:
                    child_tree = await _get_children(child["id"], depth + 1)
                    result["children"].append(child_tree)

            return result

        return await _get_children(effective_folder, 0)

    async def validate_folder_access(self, folder_id: str) -> Tuple[bool, str]:
        """Validate access to a folder."""
        client = await self._get_client()
        try:
            if folder_id == "root":
                resp = await client.get(
                    f"{self._drive_base}/root",
                    params={"$select": "id,name,folder"},
                )
            else:
                resp = await client.get(
                    f"{self._drive_base}/items/{folder_id}",
                    params={"$select": "id,name,folder"},
                )
            resp.raise_for_status()
            data = resp.json()
            if "folder" not in data:
                return False, "Specified ID is not a folder"
            return True, f"Access validated: {data.get('name')}"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False, "Folder not found or no access"
            return False, f"HTTP error: {e.response.status_code}"
        except Exception as e:
            return False, str(e)

    async def create_folder(
        self,
        name: str,
        parent_id: Optional[str] = None,
    ) -> OneDriveItem:
        """Create a new folder in OneDrive."""
        client = await self._get_client()

        effective_parent = parent_id or "root"
        if effective_parent == "root":
            url = f"{self._drive_base}/root/children"
        else:
            url = f"{self._drive_base}/items/{effective_parent}/children"

        body = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        }

        response = await client.post(url, json=body)
        response.raise_for_status()
        return self._parse_item(response.json())

    async def upload_item(
        self,
        name: str,
        content: bytes,
        parent_id: Optional[str] = None,
    ) -> OneDriveItem:
        """
        Upload a file to OneDrive.

        Uses simple upload for files ≤4MB.
        For larger files, an upload session would be needed (not implemented here).
        """
        effective_parent = parent_id or "root"

        if effective_parent == "root":
            url = f"{self._drive_base}/root:/{name}:/content"
        else:
            url = f"{self._drive_base}/items/{effective_parent}:/{name}:/content"

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=5.0),
        ) as client:
            response = await client.put(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/octet-stream",
                },
                content=content,
            )
            response.raise_for_status()
            return self._parse_item(response.json())

    async def move_item(
        self,
        item_id: str,
        target_parent_id: str,
    ) -> OneDriveItem:
        """Move an item to a different folder."""
        client = await self._get_client()

        body: Dict[str, Any] = {
            "parentReference": {"id": target_parent_id},
        }

        response = await client.patch(
            f"{self._drive_base}/items/{item_id}",
            json=body,
        )
        response.raise_for_status()
        return self._parse_item(response.json())

    async def delete_item(self, item_id: str, permanent: bool = False) -> bool:
        """
        Delete an item.

        OneDrive DELETE moves to the recycle bin by default.
        Permanent deletion requires additional API calls to empty recycle bin,
        which is not commonly needed.
        """
        client = await self._get_client()

        response = await client.delete(f"{self._drive_base}/items/{item_id}")
        response.raise_for_status()
        return True
