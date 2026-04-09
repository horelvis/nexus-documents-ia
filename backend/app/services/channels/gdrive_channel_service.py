"""
Google Drive Channel Service for syncing documents to RAG.

Handles:
- Listing files in specified Drive folder
- Detecting file changes via modifiedTime/hash
- Downloading and processing files
- Coordinating with Weaviate for indexing
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InformationChannel, ChannelDocument
from app.services.channels.channel_service import ChannelService
from app.services.channels.channel_credential_service import ChannelCredentialService

logger = logging.getLogger(__name__)

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
    "application/vnd.google-apps.document": "gdoc",  # Export as docx
    "application/vnd.google-apps.spreadsheet": "gsheet",  # Export as xlsx
    "application/vnd.google-apps.presentation": "gslides",  # Export as pptx
}

# Export MIME types for Google Docs/Sheets/Slides
GOOGLE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class GoogleDriveChannelService:
    """
    Service for syncing Google Drive folders to the RAG pipeline.

    Uses Google Drive API v3 to:
    - List files in configured folder
    - Track changes via modifiedTime
    - Download and process supported file types
    """

    def __init__(
        self,
        db: AsyncSession,
        channel_service: ChannelService,
        credential_service: ChannelCredentialService,
    ):
        self.db = db
        self.channel_service = channel_service
        self.credential_service = credential_service

    async def sync_channel(
        self,
        channel: InformationChannel,
        full_sync: bool = False,
    ) -> Dict[str, Any]:
        """
        Sync a Google Drive channel.

        Args:
            channel: The channel to sync
            full_sync: If True, re-sync all files regardless of changes

        Returns:
            Dict with sync statistics
        """
        stats = {
            "items_found": 0,
            "items_new": 0,
            "items_updated": 0,
            "items_deleted": 0,
            "items_failed": 0,
            "errors": [],
        }

        try:
            # Get credentials
            credentials = await self.credential_service.get_oauth_credentials(channel.id)
            if not credentials:
                raise ValueError("No valid credentials for channel")

            # Build Drive service
            service = build("drive", "v3", credentials=credentials)

            # Get configuration
            config = channel.configuration or {}
            folder_id = config.get("folder_id")
            if not folder_id:
                raise ValueError("folder_id not configured")

            include_subfolders = config.get("include_subfolders", True)
            file_types = config.get("file_types", list(SUPPORTED_MIME_TYPES.values()))
            max_file_size_mb = config.get("max_file_size_mb", 50)

            # List files in folder
            files = await self._list_folder_files(
                service,
                folder_id,
                include_subfolders,
                file_types,
            )
            stats["items_found"] = len(files)

            # Process each file
            for file_info in files:
                try:
                    result = await self._process_file(
                        service=service,
                        channel=channel,
                        file_info=file_info,
                        max_file_size_mb=max_file_size_mb,
                        full_sync=full_sync,
                    )
                    if result == "new":
                        stats["items_new"] += 1
                    elif result == "updated":
                        stats["items_updated"] += 1
                except Exception as e:
                    stats["items_failed"] += 1
                    stats["errors"].append({
                        "file_id": file_info.get("id"),
                        "file_name": file_info.get("name"),
                        "error": str(e),
                    })
                    logger.exception(f"Error processing file {file_info.get('id')}: {e}")

            # TODO: Handle deleted files (mark as deleted in channel_documents)

        except Exception as e:
            logger.exception(f"Error syncing Google Drive channel {channel.id}: {e}")
            raise

        return stats

    async def _list_folder_files(
        self,
        service: Any,
        folder_id: str,
        include_subfolders: bool,
        file_types: List[str],
    ) -> List[Dict[str, Any]]:
        """
        List all files in a folder (and optionally subfolders).

        Args:
            service: Google Drive API service
            folder_id: Root folder ID
            include_subfolders: Whether to recurse into subfolders
            file_types: List of file extensions to include

        Returns:
            List of file metadata dicts
        """
        files = []
        folders_to_process = [folder_id]

        while folders_to_process:
            current_folder = folders_to_process.pop(0)

            # Build MIME type filter
            mime_filters = []
            for ext in file_types:
                for mime, file_ext in SUPPORTED_MIME_TYPES.items():
                    if file_ext == ext:
                        mime_filters.append(f"mimeType='{mime}'")

            # Add folder MIME type if recursing
            if include_subfolders:
                mime_filters.append("mimeType='application/vnd.google-apps.folder'")

            query = f"'{current_folder}' in parents and trashed=false"
            if mime_filters:
                query += f" and ({' or '.join(mime_filters)})"

            page_token = None
            while True:
                response = (
                    service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)",
                        pageToken=page_token,
                        pageSize=100,
                    )
                    .execute()
                )

                for item in response.get("files", []):
                    if item["mimeType"] == "application/vnd.google-apps.folder":
                        if include_subfolders:
                            folders_to_process.append(item["id"])
                    else:
                        files.append(item)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        return files

    async def _process_file(
        self,
        service: Any,
        channel: InformationChannel,
        file_info: Dict[str, Any],
        max_file_size_mb: int,
        full_sync: bool,
    ) -> Optional[str]:
        """
        Process a single file from Google Drive.

        Args:
            service: Google Drive API service
            channel: The channel being synced
            file_info: File metadata from Drive API
            max_file_size_mb: Maximum file size to process
            full_sync: Force reprocessing

        Returns:
            "new", "updated", or None if skipped
        """
        file_id = file_info["id"]
        file_name = file_info["name"]
        mime_type = file_info["mimeType"]
        modified_time_str = file_info.get("modifiedTime")
        file_size = int(file_info.get("size", 0))
        web_link = file_info.get("webViewLink")

        # Check file size
        if file_size > max_file_size_mb * 1024 * 1024:
            logger.info(f"Skipping {file_name}: exceeds max size ({file_size} bytes)")
            return None

        # Parse modified time
        modified_time = None
        if modified_time_str:
            modified_time = datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))

        # Calculate content hash from file_id + modified_time (quick check without downloading)
        hash_input = f"{file_id}:{modified_time_str or ''}"
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        # Check if document exists and has changed
        doc, is_new = await self.channel_service.upsert_document(
            channel_id=channel.id,
            external_id=file_id,
            content_hash=content_hash,
            title=file_name,
            external_url=web_link,
            source_metadata={
                "mime_type": mime_type,
                "size": file_size,
                "parents": file_info.get("parents", []),
            },
            source_modified_at=modified_time,
        )

        # If not new and hash matches, skip unless full_sync
        if not is_new and doc.status == "indexed" and not full_sync:
            logger.debug(f"Skipping unchanged file: {file_name}")
            return None

        # Download file content
        try:
            file_content = await self._download_file(service, file_id, mime_type)

            if not file_content:
                logger.warning(f"Empty content for file: {file_name}")
                await self.channel_service.mark_document_failed(
                    doc.id, "Empty file content"
                )
                return None

            # Send to text extraction service
            extracted_text = await self._extract_text(
                file_content=file_content,
                file_name=file_name,
                mime_type=mime_type,
            )

            if not extracted_text:
                logger.warning(f"No text extracted from: {file_name}")
                await self.channel_service.mark_document_failed(
                    doc.id, "Text extraction returned empty"
                )
                return None

            # Index in Weaviate
            weaviate_id = await self._index_in_weaviate(
                channel=channel,
                document=doc,
                content=extracted_text,
                file_name=file_name,
            )

            if weaviate_id:
                await self.channel_service.mark_document_indexed(doc.id, weaviate_id)
                return "new" if is_new else "updated"
            else:
                await self.channel_service.mark_document_failed(
                    doc.id, "Weaviate indexing failed"
                )
                return None

        except Exception as e:
            await self.channel_service.mark_document_failed(doc.id, str(e))
            raise

    async def _download_file(
        self,
        service: Any,
        file_id: str,
        mime_type: str,
    ) -> Optional[bytes]:
        """
        Download file content from Google Drive.

        Handles Google Docs/Sheets/Slides by exporting to standard formats.

        Args:
            service: Google Drive API service
            file_id: Drive file ID
            mime_type: File MIME type

        Returns:
            File content as bytes, or None if failed
        """
        try:
            if mime_type in GOOGLE_EXPORT_TYPES:
                # Export Google Workspace file
                export_mime = GOOGLE_EXPORT_TYPES[mime_type]
                request = service.files().export_media(
                    fileId=file_id, mimeType=export_mime
                )
            else:
                # Download regular file
                request = service.files().get_media(fileId=file_id)

            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            return buffer.getvalue()

        except Exception as e:
            logger.exception(f"Error downloading file {file_id}: {e}")
            return None

    async def _extract_text(
        self,
        file_content: bytes,
        file_name: str,
        mime_type: str,
    ) -> Optional[str]:
        """
        Extract text from file using intelligence-docs-service.

        Args:
            file_content: File bytes
            file_name: Original file name
            mime_type: File MIME type

        Returns:
            Extracted text, or None if failed
        """
        try:
            # Determine actual MIME type for exported files
            if mime_type in GOOGLE_EXPORT_TYPES:
                mime_type = GOOGLE_EXPORT_TYPES[mime_type]

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://intelligence-docs-service:8000/extract",
                    files={"file": (file_name, file_content, mime_type)},
                    timeout=60.0,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("text", "")

        except Exception as e:
            logger.exception(f"Error extracting text from {file_name}: {e}")
            return None

    async def _index_in_weaviate(
        self,
        channel: InformationChannel,
        document: ChannelDocument,
        content: str,
        file_name: str,
    ) -> Optional[str]:
        """
        Index document in Weaviate with channel access control properties.

        Args:
            channel: The channel
            document: ChannelDocument record
            content: Extracted text content
            file_name: File name for title

        Returns:
            Weaviate object UUID, or None if failed
        """
        try:
            # Single-tenant: use the unified Nouxcube_documents collection.
            collection_name = "Nouxcube_documents"
            weaviate_url = f"http://weaviate-service:8007/weaviate/collections/{collection_name}/documents"

            # Service-to-service auth uses X-API-Key
            from app.core.config import settings
            headers = {}
            if hasattr(settings, "MICROSERVICES_API_KEY") and settings.MICROSERVICES_API_KEY:
                headers["X-API-Key"] = settings.MICROSERVICES_API_KEY

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    weaviate_url,
                    headers=headers,
                    json={
                        "title": file_name,
                        "content": content,
                        "document_type": "google_drive",
                        "metadata": {
                            "external_id": document.external_id,
                            "external_url": document.external_url,
                            "channel_name": channel.name,
                            **(document.source_metadata or {}),
                        },
                        "tags": ["google_drive", f"channel:{channel.id}"],
                        # Channel access control properties
                        "channel_id": str(channel.id),
                        "channel_visibility": channel.visibility,
                        "owner_user_id": str(channel.created_by),
                        "source_type": "google_drive",
                        "external_id": document.external_id,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
                return result.get("id")

        except Exception as e:
            logger.exception(f"Error indexing in Weaviate: {e}")
            return None

    async def validate_folder_access(
        self,
        channel_id: UUID,
        folder_id: str,
    ) -> Tuple[bool, str]:
        """
        Validate that we have access to the specified folder.

        Args:
            channel_id: Channel UUID
            folder_id: Google Drive folder ID to validate

        Returns:
            Tuple of (success, message)
        """
        try:
            credentials = await self.credential_service.get_oauth_credentials(channel_id)
            if not credentials:
                return False, "No valid credentials"

            service = build("drive", "v3", credentials=credentials)

            # Try to get folder metadata
            folder = (
                service.files()
                .get(fileId=folder_id, fields="id, name, mimeType")
                .execute()
            )

            if folder.get("mimeType") != "application/vnd.google-apps.folder":
                return False, "Specified ID is not a folder"

            return True, f"Access validated: {folder.get('name')}"

        except Exception as e:
            logger.exception(f"Error validating folder access: {e}")
            return False, str(e)
