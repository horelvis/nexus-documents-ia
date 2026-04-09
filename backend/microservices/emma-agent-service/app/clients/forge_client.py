"""HTTP client for document-forge-service."""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ForgeClient:
    """Thin HTTP client to document-forge-service for the ReAct agent."""

    def __init__(self):
        self.base_url = getattr(
            settings, "document_forge_service_url",
            "http://document-forge-service:8013",
        )
        self.api_key = settings.MICROSERVICES_API_KEY

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    async def analyze(
        self,
        user_id: str,
        document_id: str | None = None,
        user_intent: str = "modification",
        max_fields: int = 30,
        file_bytes: bytes | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Call POST /analyze on forge-service."""
        data = {
            "user_id": user_id,
            "user_intent": user_intent,
            "max_fields": str(max_fields),
        }
        if document_id:
            data["document_id"] = document_id

        files = {}
        if file_bytes and file_name:
            files["file"] = (file_name, file_bytes, "application/octet-stream")

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/analyze",
                data=data,
                files=files if files else None,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def prepare(
        self,
        session_id: str,
        fields_to_mark: list[str] | None = None,
        custom_fields: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Call POST /prepare on forge-service."""
        payload: dict[str, Any] = {"session_id": session_id}
        if fields_to_mark:
            payload["fields_to_mark"] = fields_to_mark
        if custom_fields:
            payload["custom_fields"] = custom_fields

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/prepare",
                json=payload,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def render(
        self,
        session_id: str,
        field_values: dict[str, str],
        output_formats: list[str] | None = None,
        document_title: str | None = None,
    ) -> dict[str, Any]:
        """Call POST /render on forge-service."""
        payload: dict[str, Any] = {
            "session_id": session_id,
            "field_values": field_values,
        }
        if output_formats:
            payload["output_formats"] = output_formats
        if document_title:
            payload["document_title"] = document_title

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/render",
                json=payload,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def persist(
        self,
        session_id: str,
        user_id: str,
        persist_formats: list[str] | None = None,
        index_in_weaviate: bool = True,
        folder_path: str = "",
    ) -> dict[str, Any]:
        """Call POST /persist on forge-service."""
        payload: dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "index_in_weaviate": index_in_weaviate,
        }
        if persist_formats:
            payload["persist_formats"] = persist_formats
        if folder_path:
            payload["folder_path"] = folder_path

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/persist",
                json=payload,
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False


_client = None


def get_forge_client() -> ForgeClient:
    global _client
    if _client is None:
        _client = ForgeClient()
    return _client
