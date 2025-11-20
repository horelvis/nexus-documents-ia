"""
HTTP client for fetching Google Drive access tokens from the core API.
"""
from __future__ import annotations

from typing import Any, Dict

import httpx

from app.core.config import settings


class CoreGoogleTokenClient:
    def __init__(self):
        base = settings.main_api_url.rstrip("/")
        prefix = getattr(settings, "api_prefix", "/api/v1").rstrip("/")
        self.base_url = f"{base}{prefix}/internal/google-drive-tokens"
        self.headers = {
            "Authorization": f"Bearer {settings.microservices_api_key}",
        }
        self.timeout = httpx.Timeout(20.0, read=20.0)

    async def get_access_token(self, user_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/{user_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 404:
                raise GoogleTokenNotConnectedError("User has not connected Google Drive")
            response.raise_for_status()
            return response.json()


class GoogleTokenNotConnectedError(Exception):
    """Raised when the user has not connected Google Drive."""


google_token_client = CoreGoogleTokenClient()
