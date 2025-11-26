"""
HTTP client for the Template Editor microservice (Google Docs sessions).
"""
from __future__ import annotations

import httpx
import logging
from typing import Any, Dict, List

from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


class TemplateEditorClient:
    """Encapsulates interactions with the template-editor-service microservice."""

    def __init__(self):
        base_url = getattr(settings, "ENGINE_TEMPLATE_SERVICE_URL", "").rstrip("/")
        if not base_url:
            raise RuntimeError("ENGINE_TEMPLATE_SERVICE_URL is not configured")
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}",
            "Content-Type": "application/json",
        }
        self.timeout = httpx.Timeout(30.0, read=30.0)

    async def create_edit_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Google Docs editing session."""
        return await self._request("POST", "/edit-sessions/", json=payload)

    async def get_user_sessions(
        self, user_id: str, tenant_id: str, include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all edit sessions for a user."""
        params = {
            "tenant_id": tenant_id,
            "include_completed": str(include_completed).lower(),
        }
        return await self._request(
            "GET", f"/edit-sessions/user/{user_id}", params=params
        )

    async def finish_edit_session(
        self, session_id: str, user_id: str, force_sync: bool = False
    ) -> Dict[str, Any]:
        """Finalize an editing session and retrieve updated content."""
        payload = {"user_id": user_id, "force_sync": force_sync}
        return await self._request(
            "POST", f"/edit-sessions/{session_id}/finish", json=payload
        )

    async def extend_session(
        self, session_id: str, user_id: str, hours: int = 1
    ) -> Dict[str, Any]:
        """Extend an editing session."""
        payload = {"user_id": user_id, "hours": hours}
        return await self._request(
            "POST", f"/edit-sessions/{session_id}/extend", json=payload
        )

    async def cancel_edit_session(
        self, session_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Cancel an active editing session."""
        params = {"user_id": user_id}
        return await self._request(
            "DELETE", f"/edit-sessions/{session_id}", params=params
        )

    async def _request(
        self,
        method: str,
        path: str,
        json: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self.headers,
                    json=json,
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text or exc.response.reason_phrase
            logger.error(
                "Template Editor service error %s: %s", exc.response.status_code, detail
            )
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Template editor service error: {detail}",
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Template Editor service unreachable: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Template editor service unavailable",
            ) from exc
