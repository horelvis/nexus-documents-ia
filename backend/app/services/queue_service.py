"""HTTP client for the background worker microservice."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueueService:
    """Thin wrapper around the background-worker API."""

    def __init__(self) -> None:
        self.base_url = settings.BACKGROUND_TASKS_URL.rstrip("/")
        self.api_key = settings.MICROSERVICES_API_KEY
        self.timeout = httpx.Timeout(30.0, connect=5.0)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Optional[str]:
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error("Background worker call failed (%s %s): %s", path, response.status_code, response.text)
            return None
        data = response.json()
        return data.get("job_id")

    async def _post_with_result(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def enqueue_preview_generation(
        self,
        document_id: str,
        user_id: str,
        preview_type: str = "all",
        force_regenerate: bool = False,
        priority: str = "default",
    ) -> Optional[str]:
        payload = {
            "document_id": document_id,
            "user_id": user_id,
            "preview_type": preview_type,
            "force_regenerate": force_regenerate,
            "priority": priority,
        }
        return await self._post("/tasks/preview", payload)

    async def enqueue_preview_batch(
        self,
        document_ids: List[str],
        user_id: str,
        preview_type: str = "all",
        batch_size: int = 5,
        priority: str = "default",
    ) -> Optional[str]:
        payload = {
            "document_ids": document_ids,
            "user_id": user_id,
            "preview_type": preview_type,
            "batch_size": batch_size,
            "priority": priority,
        }
        return await self._post("/tasks/preview/batch", payload)

    async def enqueue_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        template_data: Dict[str, Any],
        priority: str = "default",
    ) -> Optional[str]:
        payload = {
            "to_email": to_email,
            "subject": subject,
            "template_name": template_name,
            "template_data": template_data,
            "priority": priority,
        }
        return await self._post("/tasks/email/send", payload)

    async def enqueue_bulk_emails(
        self,
        email_batch: List[Dict[str, Any]],
        batch_size: int = 10,
        priority: str = "low",
    ) -> Optional[str]:
        payload = {
            "email_batch": email_batch,
            "batch_size": batch_size,
            "priority": priority,
        }
        return await self._post("/tasks/email/bulk", payload)

    async def enqueue_user_invitation(
        self,
        user_email: str,
        invited_by_name: str,
        tenant_name: str,
        invitation_link: str,
    ) -> Optional[str]:
        payload = {
            "user_email": user_email,
            "invited_by_name": invited_by_name,
            "tenant_name": tenant_name,
            "invitation_link": invitation_link,
        }
        return await self._post("/tasks/email/user-invitation", payload)

    async def enqueue_team_invitation(
        self,
        invitation_id: str,
    ) -> Optional[str]:
        payload = {"invitation_id": invitation_id}
        return await self._post("/tasks/email/team-invitation", payload)

    async def enqueue_document_share_notification(
        self,
        share_id: str,
    ) -> Optional[str]:
        payload = {"share_id": share_id}
        return await self._post("/tasks/email/share-notification", payload)

    async def enqueue_password_reset(
        self,
        user_email: str,
        reset_token: str,
        user_name: Optional[str] = None,
    ) -> Optional[str]:
        payload = {"user_email": user_email, "reset_token": reset_token, "user_name": user_name}
        return await self._post("/tasks/email/password-reset", payload)

    async def enqueue_index_retry(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        priority: str = "default",
    ) -> Optional[str]:
        payload = {
            "document_id": document_id,
            "user_id": user_id,
            "priority": priority,
        }
        return await self._post("/tasks/indexing/retry", payload)

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/tasks/status/{job_id}"
        headers = {"X-API-Key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def get_queue_stats(self) -> Dict[str, Any]:
        url = f"{self.base_url}/tasks/stats"
        headers = {"X-API-Key": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning("Failed to get background worker stats: %s", response.text)
            return {}
        return response.json()


queue_service = QueueService()


async def get_queue_service() -> QueueService:
    return queue_service
