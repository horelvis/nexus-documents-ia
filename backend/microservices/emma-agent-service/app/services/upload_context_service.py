"""Temporary upload storage and text extraction for non-indexed files."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.clients.text_extraction_client import get_text_extraction_client

logger = logging.getLogger(__name__)


class UploadContextService:
    def __init__(self) -> None:
        self._tmp_dir = settings.upload_tmp_dir
        self._ttl_seconds = settings.upload_ttl_seconds
        self._max_chars_per_doc = settings.upload_max_chars_per_doc

        os.makedirs(self._tmp_dir, exist_ok=True)

    def _path_for_id(self, upload_id: str) -> str:
        return os.path.join(self._tmp_dir, f"{upload_id}.json")

    def _is_expired(self, created_at: float) -> bool:
        return (time.time() - created_at) > self._ttl_seconds

    async def save_upload(
        self,
        *,
        tenant_id: str,
        user_id: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> Dict[str, Any]:
        upload_id = str(uuid.uuid4())

        client = get_text_extraction_client()
        extraction = await client.extract_text(
            file_bytes=file_bytes,
            filename=filename,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        text = extraction.get("text", "") if isinstance(extraction, dict) else ""
        if text and len(text) > self._max_chars_per_doc:
            logger.warning(
                f"Upload rejected: {filename} has {len(text)} chars, "
                f"exceeds limit of {self._max_chars_per_doc} chars"
            )
            raise ValueError(
                f"El documento '{filename}' excede el límite de "
                f"{self._max_chars_per_doc // 1000}K caracteres "
                f"({len(text):,} chars). Reduzca el tamaño del archivo."
            )
        if text:
            logger.info(f"Upload text extracted: {len(text)} chars from {filename}")

        payload = {
            "id": upload_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
            "text": text,
            "characters": len(text),
            "created_at": time.time(),
        }

        with open(self._path_for_id(upload_id), "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        return payload

    def get_upload(self, upload_id: str) -> Optional[Dict[str, Any]]:
        path = self._path_for_id(upload_id)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.warning("Failed to read upload context %s: %s", upload_id, exc)
            return None

        created_at = payload.get("created_at", 0)
        if created_at and self._is_expired(created_at):
            try:
                os.remove(path)
            except OSError:
                pass
            return None

        return payload

    def get_texts(self, upload_ids: List[str]) -> List[Dict[str, Any]]:
        """Return full text for each upload — no truncation.

        The downstream pipeline (stop-and-go graph) handles large documents
        via section chunking and RLM processing. Truncating here caused
        hallucinations because the WriterAgent couldn't see the full source.
        """
        texts: List[Dict[str, Any]] = []

        for upload_id in upload_ids:
            payload = self.get_upload(upload_id)
            if not payload:
                continue

            text = payload.get("text", "")
            if not text:
                continue

            texts.append(
                {
                    "id": payload.get("id"),
                    "filename": payload.get("filename"),
                    "content_type": payload.get("content_type"),
                    "text": text,
                }
            )

        return texts

    def hydrate_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not context:
            return context

        if context.get("uploaded_texts"):
            return context

        upload_ids = context.get("uploaded_file_ids") or []
        if not upload_ids:
            return context

        context = dict(context)
        context["uploaded_texts"] = self.get_texts(upload_ids)
        return context


upload_context_service = UploadContextService()
