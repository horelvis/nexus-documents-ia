"""
Utilities for storing workflow template files (ODT) per tenant.
"""
from __future__ import annotations

import base64
import binascii
import io
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import HTTPException

from app.db.models import Document
from app.services.storage_factory import StorageServiceFactory

logger = logging.getLogger(__name__)

ODT_MIME_TYPE = "application/vnd.oasis.opendocument.text"
CURRENT_TEMPLATE_FILENAME = "current.odt"


class TemplateStorageService:
    """Handles upload/download/delete of tenant template files (ODT)."""

    def __init__(self, tenant_id: str, user_id: Optional[str], db_session):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.db_session = db_session
        self.storage = StorageServiceFactory.create_storage_service(
            tenant_id, user_id, db_session
        )

    def save_base64_file(
        self,
        template_id: str,
        original_name: str,
        file_base64: str,
        mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads a base64 ODT file for the given template."""
        self._require_odt_extension(original_name)

        try:
            file_bytes = base64.b64decode(file_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=400, detail="Invalid base64 payload for template file"
            )

        if not file_bytes:
            raise HTTPException(status_code=400, detail="Template file is empty")

        return self._upload_bytes(
            template_id=template_id,
            original_name=original_name,
            file_bytes=file_bytes,
            source_document_id=None,
            mime_type=mime_type or ODT_MIME_TYPE
        )

    def copy_from_document(
        self, template_id: str, document: Document
    ) -> Dict[str, Any]:
        """Copies an existing ODT document into the template storage."""
        if (document.file_type or "").lower() != "odt":
            raise HTTPException(
                status_code=400,
                detail="Only ODT documents can be converted into templates.",
            )

        file_bytes = self.storage.download_file(document.file_path)
        if not file_bytes:
            raise HTTPException(
                status_code=404,
                detail="Source document file not found in tenant storage.",
            )

        original_name = document.filename or f"{document.id}.odt"
        self._require_odt_extension(original_name)

        return self._upload_bytes(
            template_id=template_id,
            original_name=original_name,
            file_bytes=file_bytes,
            source_document_id=str(document.id),
            mime_type=document.mime_type or ODT_MIME_TYPE
        )

    def delete_template_file(self, template_file_path: Optional[str]) -> None:
        """Deletes the template file if present (best effort)."""
        if not template_file_path:
            return

        try:
            deleted = self.storage.delete_file(template_file_path)
            if deleted:
                logger.info("Deleted template file %s", template_file_path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Failed to delete template file %s: %s", template_file_path, exc
            )

    def download_template_file(self, template_file_path: str) -> bytes:
        if not template_file_path:
            raise HTTPException(status_code=400, detail="Template file path not configured")
        content = self.storage.download_file(template_file_path)
        if not content:
            raise HTTPException(status_code=404, detail="Template file not found in storage")
        return content

    def _upload_bytes(
        self,
        template_id: str,
        original_name: str,
        file_bytes: bytes,
        source_document_id: Optional[str],
        mime_type: str
    ) -> Dict[str, Any]:
        """Internal helper to upload bytes to storage."""
        storage_path = self._build_storage_path(template_id)
        metadata = {
            "resource_type": "template",
            "template_id": template_id,
            "uploaded_by": self.user_id or "system",
            "original_filename": original_name,
            "mime_type": mime_type,
        }
        if source_document_id:
            metadata["source_document_id"] = source_document_id

        success = self.storage.upload_file(
            io.BytesIO(file_bytes), storage_path, metadata=metadata
        )
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to store template file in storage"
            )

        logger.info(
            "Stored template file for template %s (path=%s, size=%s)",
            template_id,
            storage_path,
            len(file_bytes),
        )

        return {
            "path": storage_path,
            "original_name": original_name,
            "mime_type": mime_type,
            "size": len(file_bytes),
            "updated_at": datetime.utcnow(),
            "source_document_id": source_document_id,
        }

    def _build_storage_path(self, template_id: str) -> str:
        return f"templates/{template_id}/{CURRENT_TEMPLATE_FILENAME}"

    @staticmethod
    def _require_odt_extension(filename: str) -> None:
        if not filename.lower().endswith(".odt"):
            raise HTTPException(
                status_code=400, detail="Template files must be in .odt format."
            )
