"""Celery tasks for sending emails."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.core.config import settings as backend_settings
from app.db.async_database import AsyncSessionLocal
from app.db.models import User
from app.services.email_service import EmailService

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


async def _send_email(
    to_email: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any],
    retry_count: int = 0,
) -> Dict[str, Any]:
    try:
        email_service = EmailService()
        result = await email_service.send_email(
            to=to_email,
            subject=subject,
            template=template_name,
            **template_data,
        )
        if result:
            logger.info("Email sent successfully to %s", to_email)
            return {
                "success": True,
                "recipient": to_email,
                "subject": subject,
                "template": template_name,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }
        return {"success": False, "recipient": to_email, "error": "Failed to send email"}
    except Exception as exc:
        logger.error("Error sending email to %s: %s", to_email, exc)
        return {
            "success": False,
            "recipient": to_email,
            "error": str(exc),
            "retry_count": retry_count,
        }


@celery_app.task(name="email.send_email")
def send_email_task(
    to_email: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any],
    retry_count: int = 0,
) -> Dict[str, Any]:
    return _run_async(_send_email(to_email, subject, template_name, template_data, retry_count))


@celery_app.task(name="email.send_user_invitation")
def send_user_invitation_task(
    user_email: str,
    invited_by_name: str,
    tenant_name: str,
    invitation_link: str,
) -> Dict[str, Any]:
    return _run_async(
        _send_email(
            user_email,
            f"You've been invited to join {tenant_name}",
            "user_invitation",
            {
                "invited_by": invited_by_name,
                "tenant_name": tenant_name,
                "invitation_link": invitation_link,
            },
        )
    )


# TeamInvitation and DocumentShare models were removed when multi-tenancy
# was dropped. The corresponding email tasks are retained as no-ops so that
# Celery's registered-task set stays stable for legacy producers.


@celery_app.task(name="email.send_team_invitation")
def send_team_invitation_task(invitation_id: str) -> Dict[str, Any]:
    logger.warning(
        "send_team_invitation_task called for %s but the TeamInvitation "
        "feature was removed in the multi-tenancy refactor.", invitation_id,
    )
    return {"success": False, "error": "team_invitation_feature_removed"}


@celery_app.task(name="email.send_document_share_notification")
def send_document_share_notification_task(share_id: str) -> Dict[str, Any]:
    logger.warning(
        "send_document_share_notification_task called for %s but the "
        "DocumentShare feature was removed in the multi-tenancy refactor.",
        share_id,
    )
    return {"success": False, "error": "document_share_feature_removed"}


@celery_app.task(name="email.send_password_reset")
def send_password_reset_task(
    user_email: str,
    reset_token: str,
    user_name: Optional[str] = None,
) -> Dict[str, Any]:
    return _run_async(
        _send_email(
            user_email,
            "Reset your password",
            "password_reset",
            {
                "user_name": user_name or user_email,
                "reset_link": f"{backend_settings.FRONTEND_URL}/reset-password?token={reset_token}",
                "expires_in": "24 hours",
            },
        )
    )


async def _send_bulk_emails(email_batch: List[Dict[str, Any]], batch_size: int = 10) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for i in range(0, len(email_batch), batch_size):
        batch = email_batch[i : i + batch_size]
        tasks = [
            _send_email(
                email_data["to_email"],
                email_data["subject"],
                email_data["template_name"],
                email_data["template_data"],
            )
            for email_data in batch
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for email_data, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results.append(
                    {"recipient": email_data["to_email"], "success": False, "error": str(result)}
                )
            else:
                results.append(result)
        if i + batch_size < len(email_batch):
            await asyncio.sleep(1)

    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    return {"total": len(email_batch), "successful": successful, "failed": failed, "results": results}


@celery_app.task(name="email.send_bulk_emails")
def send_bulk_emails_task(email_batch: List[Dict[str, Any]], batch_size: int = 10) -> Dict[str, Any]:
    return _run_async(_send_bulk_emails(email_batch, batch_size))


async def _process_pending_notifications() -> Dict[str, Any]:
    logger.info("Processing pending email notifications")
    return {"success": True, "message": "Pending notifications processed"}


@celery_app.task(name="email.process_pending_notifications")
def process_pending_notifications_task() -> Dict[str, Any]:
    return _run_async(_process_pending_notifications())
