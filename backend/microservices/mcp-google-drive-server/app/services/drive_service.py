"""
Google Drive API v3 Client Service.

Provides methods for interacting with Google Drive:
- List files in folders (recursive)
- Download files (including Google Docs export)
- Search files
- Get metadata
- Create folders, upload, move, delete

Uses httpx for async HTTP calls to the Drive REST API directly,
avoiding the synchronous googleapiclient in the hot path.
The googleapiclient is only used for MediaIoBaseDownload (binary downloads).

API Reference: https://developers.google.com/drive/api/reference/rest/v3
"""

import logging
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel

from ..core.config import GoogleDriveInstanceConfig

logger = logging.getLogger(__name__)

# Google Drive API base URL
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

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
    "application/vnd.google-apps.document": "gdoc",
    "application/vnd.google-apps.spreadsheet": "gsheet",
    "application/vnd.google-apps.presentation": "gslides",
}

# Export MIME types for Google Workspace files
GOOGLE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class DriveFile(BaseModel):
    """Represents a Google Drive file."""
    id: str
    name: str
    mime_type: str
    is_folder: bool = False
    size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    web_view_link: Optional[str] = None
    parents: Optional[List[str]] = None
    path: Optional[str] = None
    owners: Optional[List[str]] = None


class DriveService:
    """
    Google Drive API v3 async client.

    Uses httpx AsyncClient with Bearer token auth.
    Token refresh is handled by the OAuthService.
    """

    def __init__(self, access_token: str, config: GoogleDriveInstanceConfig):
        self.access_token = access_token
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

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

    def _parse_file(self, item: Dict[str, Any]) -> DriveFile:
        """Parse Drive API file response into DriveFile."""
        created_at = None
        if item.get("createdTime"):
            try:
                created_at = datetime.fromisoformat(
                    item["createdTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        modified_at = None
        if item.get("modifiedTime"):
            try:
                modified_at = datetime.fromisoformat(
                    item["modifiedTime"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        owners = None
        if item.get("owners"):
            owners = [o.get("emailAddress", o.get("displayName", "")) for o in item["owners"]]

        return DriveFile(
            id=item["id"],
            name=item["name"],
            mime_type=item["mimeType"],
            is_folder=item["mimeType"] == "application/vnd.google-apps.folder",
            size_bytes=int(item["size"]) if item.get("size") else None,
            created_at=created_at,
            modified_at=modified_at,
            web_view_link=item.get("webViewLink"),
            parents=item.get("parents"),
            owners=owners,
        )

    async def list_files(
        self,
        folder_id: str,
        include_subfolders: bool = True,
        file_types: Optional[List[str]] = None,
        max_results: int = 1000,
    ) -> List[DriveFile]:
        """
        List all files in a folder (and optionally subfolders).

        Uses BFS to traverse folder tree.
        """
        client = await self._get_client()
        files: List[DriveFile] = []
        folders_to_process = [folder_id]

        while folders_to_process and len(files) < max_results:
            current_folder = folders_to_process.pop(0)

            query = f"'{current_folder}' in parents and trashed=false"

            page_token = None
            while True:
                params = {
                    "q": query,
                    "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, size, webViewLink, parents, owners)",
                    "pageSize": 100,
                    "spaces": "drive",
                }
                if page_token:
                    params["pageToken"] = page_token

                response = await client.get(f"{DRIVE_API_BASE}/files", params=params)
                response.raise_for_status()
                data = response.json()

                for item in data.get("files", []):
                    if item["mimeType"] == "application/vnd.google-apps.folder":
                        if include_subfolders:
                            folders_to_process.append(item["id"])
                    else:
                        # Filter by file type if specified
                        if file_types:
                            ext = SUPPORTED_MIME_TYPES.get(item["mimeType"])
                            if ext and ext not in file_types:
                                continue
                        files.append(self._parse_file(item))

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        return files

    async def search_files(
        self,
        query: str,
        folder_id: Optional[str] = None,
        max_results: int = 50,
    ) -> List[DriveFile]:
        """Search files by full-text query."""
        client = await self._get_client()

        q_parts = [f"fullText contains '{query}'", "trashed=false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")

        params = {
            "q": " and ".join(q_parts),
            "fields": "files(id, name, mimeType, modifiedTime, createdTime, size, webViewLink, parents, owners)",
            "pageSize": min(max_results, 100),
            "spaces": "drive",
        }

        response = await client.get(f"{DRIVE_API_BASE}/files", params=params)
        response.raise_for_status()
        data = response.json()

        return [self._parse_file(item) for item in data.get("files", [])]

    async def get_file_metadata(self, file_id: str) -> DriveFile:
        """Get detailed metadata for a file."""
        client = await self._get_client()

        params = {
            "fields": "id, name, mimeType, modifiedTime, createdTime, size, webViewLink, parents, owners, description, starred, shared, permissions",
        }

        response = await client.get(f"{DRIVE_API_BASE}/files/{file_id}", params=params)
        response.raise_for_status()
        return self._parse_file(response.json())

    async def download_file(
        self,
        file_id: str,
        mime_type: str,
    ) -> Tuple[bytes, str]:
        """
        Download file content.

        For Google Workspace files (Docs/Sheets/Slides), exports to standard format.

        Returns:
            Tuple of (content bytes, effective mime_type)
        """
        client = await self._get_client()

        download_timeout = httpx.Timeout(
            connect=10.0,
            read=float(self.config.download_timeout_seconds),
            write=30.0,
            pool=5.0,
        )

        if mime_type in GOOGLE_EXPORT_TYPES:
            # Export Google Workspace file
            export_mime = GOOGLE_EXPORT_TYPES[mime_type]
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=download_timeout,
            ) as dl_client:
                response = await dl_client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    params={"mimeType": export_mime},
                )
                response.raise_for_status()
                return response.content, export_mime
        else:
            # Download regular file
            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=download_timeout,
            ) as dl_client:
                response = await dl_client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}",
                    params={"alt": "media"},
                )
                response.raise_for_status()
                return response.content, mime_type

    async def get_folder_tree(
        self,
        folder_id: str,
        max_depth: int = 5,
    ) -> Dict[str, Any]:
        """Get folder tree structure recursively."""
        client = await self._get_client()

        async def _get_children(fid: str, depth: int) -> Dict[str, Any]:
            # Get folder info
            params = {"fields": "id, name, mimeType"}
            resp = await client.get(f"{DRIVE_API_BASE}/files/{fid}", params=params)
            resp.raise_for_status()
            folder_info = resp.json()

            result = {
                "id": folder_info["id"],
                "name": folder_info["name"],
                "children": [],
            }

            if depth >= max_depth:
                return result

            # List children that are folders
            q = f"'{fid}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            resp = await client.get(
                f"{DRIVE_API_BASE}/files",
                params={"q": q, "fields": "files(id, name, mimeType)", "pageSize": 100},
            )
            resp.raise_for_status()

            for child in resp.json().get("files", []):
                child_tree = await _get_children(child["id"], depth + 1)
                result["children"].append(child_tree)

            return result

        return await _get_children(folder_id, 0)

    async def validate_folder_access(self, folder_id: str) -> Tuple[bool, str]:
        """Validate access to a folder."""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{DRIVE_API_BASE}/files/{folder_id}",
                params={"fields": "id, name, mimeType"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("mimeType") != "application/vnd.google-apps.folder":
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
    ) -> DriveFile:
        """Create a new folder in Google Drive."""
        client = await self._get_client()

        body: Dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            body["parents"] = [parent_id]

        response = await client.post(
            f"{DRIVE_API_BASE}/files",
            json=body,
            params={"fields": "id, name, mimeType, createdTime, webViewLink, parents"},
        )
        response.raise_for_status()
        return self._parse_file(response.json())

    async def upload_file(
        self,
        name: str,
        content: bytes,
        mime_type: str,
        parent_id: Optional[str] = None,
    ) -> DriveFile:
        """Upload a file to Google Drive using simple upload."""
        metadata: Dict[str, Any] = {"name": name}
        if parent_id:
            metadata["parents"] = [parent_id]

        # Use multipart upload
        import json
        boundary = "foo_bar_baz"
        body = (
            f"--{boundary}\r\n"
            f'Content-Type: application/json; charset=UTF-8\r\n\r\n'
            f'{json.dumps(metadata)}\r\n'
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--".encode("utf-8")

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=5.0),
        ) as client:
            response = await client.post(
                f"{DRIVE_UPLOAD_BASE}/files",
                params={
                    "uploadType": "multipart",
                    "fields": "id, name, mimeType, size, createdTime, webViewLink, parents",
                },
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                content=body,
            )
            response.raise_for_status()
            return self._parse_file(response.json())

    async def move_file(
        self,
        file_id: str,
        new_parent_id: str,
        remove_from_current: bool = True,
    ) -> DriveFile:
        """Move a file to a different folder."""
        client = await self._get_client()

        # Get current parents
        params = {"fields": "id, parents"}
        resp = await client.get(f"{DRIVE_API_BASE}/files/{file_id}", params=params)
        resp.raise_for_status()
        current_parents = resp.json().get("parents", [])

        # Update parents
        update_params: Dict[str, str] = {
            "addParents": new_parent_id,
            "fields": "id, name, mimeType, parents, webViewLink",
        }
        if remove_from_current and current_parents:
            update_params["removeParents"] = ",".join(current_parents)

        response = await client.patch(
            f"{DRIVE_API_BASE}/files/{file_id}",
            params=update_params,
        )
        response.raise_for_status()
        return self._parse_file(response.json())

    async def delete_file(self, file_id: str, permanent: bool = False) -> bool:
        """Delete (trash) or permanently delete a file."""
        client = await self._get_client()

        if permanent:
            response = await client.delete(f"{DRIVE_API_BASE}/files/{file_id}")
        else:
            # Move to trash
            response = await client.patch(
                f"{DRIVE_API_BASE}/files/{file_id}",
                json={"trashed": True},
            )

        response.raise_for_status()
        return True
