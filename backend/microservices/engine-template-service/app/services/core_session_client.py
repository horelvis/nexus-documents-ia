"""
HTTP client for interacting with the core API template edit session endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

import httpx

from app.core.config import settings


class CoreTemplateSessionClient:
    def __init__(self):
        base = settings.main_api_url.rstrip("/")
        prefix = getattr(settings, "api_prefix", "/api/v1").rstrip("/")
        self.base_url = f"{base}{prefix}/internal/template-edit-sessions"
        self.headers = {
            "Authorization": f"Bearer {settings.microservices_api_key}",
            "Content-Type": "application/json",
        }
        self.timeout = httpx.Timeout(20.0, read=20.0)

    async def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, url, headers=self.headers, **kwargs)
            if response.status_code == 404:
                raise SessionNotFoundError(response.text or "Session not found")
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}

    async def get_active_session(self, template_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/active"
        params = {"template_id": template_id, "user_id": user_id}
        try:
            return await self._request("GET", url, params=params)
        except SessionNotFoundError:
            return None

    async def get_session(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{session_id}"
        params = {"user_id": user_id} if user_id else None
        return await self._request("GET", url, params=params)

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        include_completed: bool = False,
        include_expired: bool = False,
    ) -> Dict[str, Any]:
        params = {
            "include_completed": str(include_completed).lower(),
            "include_expired": str(include_expired).lower(),
        }
        if user_id:
            params["user_id"] = user_id
        if tenant_id:
            params["tenant_id"] = tenant_id
        url = f"{self.base_url}/"
        return await self._request("GET", url, params=params)

    async def create_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/"
        return await self._request("POST", url, json=payload)

    async def extend_session(self, session_id: str, user_id: str, hours: int = 1) -> Dict[str, Any]:
        url = f"{self.base_url}/{session_id}/extend"
        json = {"user_id": user_id, "hours": hours}
        return await self._request("POST", url, json=json)

    async def complete_session(
        self,
        session_id: str,
        user_id: str,
        *,
        changes_detected: bool,
        final_content_hash: Optional[str],
        content_size_bytes: Optional[int],
        cleanup_completed: bool,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{session_id}/complete"
        json = {
            "user_id": user_id,
            "changes_detected": changes_detected,
            "final_content_hash": final_content_hash,
            "content_size_bytes": content_size_bytes,
            "cleanup_completed": cleanup_completed,
            "error_message": error_message,
        }
        return await self._request("POST", url, json=json)

    async def cancel_session(
        self, session_id: str, user_id: str, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/{session_id}"
        json = {"user_id": user_id, "reason": reason}
        return await self._request("DELETE", url, json=json)


class SessionNotFoundError(Exception):
    pass


core_session_client = CoreTemplateSessionClient()
