"""Persistence orchestration — GCS upload + Weaviate indexing."""

import logging
import os
from typing import Any

from app.clients.storage_client import get_storage_client
from app.clients.weaviate_client import get_weaviate_client

logger = logging.getLogger(__name__)

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_CONTENT_TYPE = "application/pdf"


class StorageService:
    """Orchestrates document persistence to GCS and Weaviate indexing."""

    async def persist(
        self,
        tenant_id: str,
        user_id: str,
        document_title: str,
        docx_bytes: bytes | None = None,
        pdf_bytes: bytes | None = None,
        folder_path: str = "",
        index_in_weaviate: bool = True,
    ) -> dict[str, Any]:
        """Upload document(s) to GCS and optionally index in Weaviate.

        Returns:
            Dict with gcs_paths, weaviate_indexed, document_id.
        """
        storage = get_storage_client()
        result: dict[str, Any] = {
            "gcs_paths": {},
            "weaviate_indexed": False,
            "document_id": None,
        }

        # Upload DOCX
        if docx_bytes:
            docx_name = f"{document_title}.docx"
            upload_result = await storage.upload_document(
                file_bytes=docx_bytes,
                file_name=docx_name,
                folder_path=folder_path,
                tenant_id=tenant_id,
                content_type=DOCX_CONTENT_TYPE,
            )
            if upload_result:
                result["gcs_paths"]["docx"] = upload_result.get("file_path", "")
                result["document_id"] = upload_result.get("document_id")

        # Upload PDF
        if pdf_bytes:
            pdf_name = f"{document_title}.pdf"
            upload_result = await storage.upload_document(
                file_bytes=pdf_bytes,
                file_name=pdf_name,
                folder_path=folder_path,
                tenant_id=tenant_id,
                content_type=PDF_CONTENT_TYPE,
            )
            if upload_result:
                result["gcs_paths"]["pdf"] = upload_result.get("file_path", "")

        # Index in Weaviate — accept either DOCX or PDF
        has_docx = docx_bytes and result.get("gcs_paths", {}).get("docx")
        has_pdf = pdf_bytes and result.get("gcs_paths", {}).get("pdf")

        if index_in_weaviate and (has_docx or has_pdf):
            # Prefer DOCX for indexing; fall back to PDF
            if has_docx:
                index_name = f"{document_title}.docx"
                index_path = result["gcs_paths"]["docx"]
                index_type = DOCX_CONTENT_TYPE
            else:
                index_name = f"{document_title}.pdf"
                index_path = result["gcs_paths"]["pdf"]
                index_type = PDF_CONTENT_TYPE

            weaviate = get_weaviate_client()
            index_result = await weaviate.index_document(
                tenant_id=tenant_id,
                document_data={
                    "document_id": result.get("document_id", ""),
                    "file_name": index_name,
                    "file_path": index_path,
                    "content_type": index_type,
                    "user_id": user_id,
                    "folder_path": folder_path,
                },
            )
            if index_result:
                result["weaviate_indexed"] = True
                result["indexed_document_id"] = index_result.get("document_id")

        return result


_service = None


def get_storage_service() -> StorageService:
    global _service
    if _service is None:
        _service = StorageService()
    return _service
