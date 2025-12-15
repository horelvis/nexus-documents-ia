"""
HTTP client for the Template Editor microservice (Google Docs sessions).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError
from app.core.config import settings

logger = logging.getLogger(__name__)


class TemplateEditorClient(BaseHTTPClient):
    """Encapsulates interactions with the template-editor-service microservice."""

    def __init__(self):
        base_url = getattr(settings, "TEMPLATE_EDITOR_SERVICE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("TEMPLATE_EDITOR_SERVICE_URL is not configured")
        super().__init__(
            service_name="template-editor",
            base_url=base_url,
            timeout_type="default",
        )

    async def create_edit_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Google Docs editing session."""
        try:
            return await self.post_json("/edit-sessions/", json=payload)
        except HTTPClientError as exc:
            self._raise_http_exception(exc)

    async def finish_edit_session(
        self, session_id: str, user_id: str, force_sync: bool = False
    ) -> Dict[str, Any]:
        """Finalize an editing session and retrieve updated content."""
        payload = {"user_id": user_id, "force_sync": force_sync}
        try:
            return await self.post_json(f"/edit-sessions/{session_id}/finish", json=payload)
        except HTTPClientError as exc:
            self._raise_http_exception(exc)

    async def cancel_edit_session(
        self, session_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Cancel an active editing session."""
        params = {"user_id": user_id}
        try:
            response = await self.delete(f"/edit-sessions/{session_id}", params=params)
            return response.json()
        except HTTPClientError as exc:
            self._raise_http_exception(exc)

    def _raise_http_exception(self, exc: HTTPClientError) -> None:
        status_code = exc.status_code or 503
        detail: Optional[str] = None
        if exc.response_body:
            detail = exc.response_body
        logger.error(
            "Template Editor upstream error | status=%s detail=%s",
            status_code,
            (detail[:500] if detail else None),
        )
        raise HTTPException(
            status_code=status_code,
            detail=f"Template editor service error: {detail or exc.message}",
        ) from exc
