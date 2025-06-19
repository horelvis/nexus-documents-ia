"""
Email Worker
Processes email sending tasks in the background using ARQ
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.services.email_service import EmailService
from app.db.async_database import AsyncSessionLocal
from app.db.models import User, TeamInvitation, DocumentShare
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis settings for ARQ
redis_settings = RedisSettings(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    database=0,
)


async def send_email(
    ctx: Dict[str, Any],
    to_email: str,
    subject: str,
    template_name: str,
    template_data: Dict[str, Any],
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    Send a single email
    
    Args:
        ctx: ARQ context
        to_email: Recipient email
        subject: Email subject
        template_name: Email template to use
        template_data: Data for the template
        retry_count: Current retry attempt
    """
    try:
        email_service = EmailService()
        
        # Send email
        result = await email_service.send_email(
            to=to_email,
            subject=subject,
            template=template_name,
            **template_data
        )
        
        if result:
            logger.info(f"Email sent successfully to {to_email}")
            return {
                "success": True,
                "recipient": to_email,
                "subject": subject,
                "template": template_name,
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "success": False,
                "recipient": to_email,
                "error": "Failed to send email"
            }
            
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return {
            "success": False,
            "recipient": to_email,
            "error": str(e),
            "retry_count": retry_count
        }


async def send_user_invitation(
    ctx: Dict[str, Any],
    user_email: str,
    invited_by_name: str,
    tenant_name: str,
    invitation_link: str
) -> Dict[str, Any]:
    """
    Send user invitation email
    """
    return await send_email(
        ctx,
        to_email=user_email,
        subject=f"You've been invited to join {tenant_name}",
        template_name="user_invitation",
        template_data={
            "invited_by": invited_by_name,
            "tenant_name": tenant_name,
            "invitation_link": invitation_link
        }
    )


async def send_team_invitation(
    ctx: Dict[str, Any],
    invitation_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Send team invitation email
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get invitation details
            stmt = select(TeamInvitation).filter(
                TeamInvitation.id == invitation_id,
                TeamInvitation.tenant_id == tenant_id
            )
            result = await db.execute(stmt)
            invitation = result.scalar_one_or_none()
            
            if not invitation:
                return {
                    "success": False,
                    "error": f"Invitation {invitation_id} not found"
                }
            
            # Get inviter details
            stmt = select(User).filter(User.id == invitation.invited_by)
            result = await db.execute(stmt)
            inviter = result.scalar_one_or_none()
            
            # Send email
            return await send_email(
                ctx,
                to_email=invitation.email,
                subject=f"You've been invited to join a team",
                template_name="team_invitation",
                template_data={
                    "invited_by": inviter.full_name if inviter else "A team member",
                    "team_name": invitation.team_name,
                    "role": invitation.role,
                    "invitation_link": f"{settings.FRONTEND_URL}/invitations/{invitation.token}"
                }
            )
            
    except Exception as e:
        logger.error(f"Error sending team invitation {invitation_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def send_document_share_notification(
    ctx: Dict[str, Any],
    share_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """
    Send document share notification email
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get share details
            stmt = select(DocumentShare).filter(
                DocumentShare.id == share_id,
                DocumentShare.document.has(tenant_id=tenant_id)
            )
            result = await db.execute(stmt)
            share = result.scalar_one_or_none()
            
            if not share:
                return {
                    "success": False,
                    "error": f"Share {share_id} not found"
                }
            
            # Get sharer details
            stmt = select(User).filter(User.id == share.shared_by)
            result = await db.execute(stmt)
            sharer = result.scalar_one_or_none()
            
            # Send email
            return await send_email(
                ctx,
                to_email=share.shared_with_email,
                subject=f"Document shared with you: {share.document.title}",
                template_name="document_share",
                template_data={
                    "shared_by": sharer.full_name if sharer else "Someone",
                    "document_title": share.document.title,
                    "permissions": share.permissions,
                    "message": share.message,
                    "access_link": f"{settings.FRONTEND_URL}/shared/{share.share_token}"
                }
            )
            
    except Exception as e:
        logger.error(f"Error sending document share notification {share_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


async def send_password_reset(
    ctx: Dict[str, Any],
    user_email: str,
    reset_token: str,
    user_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send password reset email
    """
    return await send_email(
        ctx,
        to_email=user_email,
        subject="Reset your password",
        template_name="password_reset",
        template_data={
            "user_name": user_name or user_email,
            "reset_link": f"{settings.FRONTEND_URL}/reset-password?token={reset_token}",
            "expires_in": "24 hours"
        }
    )


async def send_bulk_emails(
    ctx: Dict[str, Any],
    email_batch: List[Dict[str, Any]],
    batch_size: int = 10
) -> Dict[str, Any]:
    """
    Send multiple emails in a batch
    
    Args:
        ctx: ARQ context
        email_batch: List of email data dicts
        batch_size: Number of emails to send concurrently
    """
    results = []
    
    # Process in batches
    for i in range(0, len(email_batch), batch_size):
        batch = email_batch[i:i + batch_size]
        
        # Send batch concurrently
        tasks = [
            send_email(
                ctx,
                email_data["to_email"],
                email_data["subject"],
                email_data["template_name"],
                email_data["template_data"]
            )
            for email_data in batch
        ]
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for email_data, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results.append({
                    "recipient": email_data["to_email"],
                    "success": False,
                    "error": str(result)
                })
            else:
                results.append(result)
        
        # Small delay between batches to avoid rate limits
        if i + batch_size < len(email_batch):
            await asyncio.sleep(1)
    
    # Summary
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    
    return {
        "total": len(email_batch),
        "successful": successful,
        "failed": failed,
        "results": results
    }


async def process_pending_notifications(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process any pending email notifications
    This could be extended to check a notifications queue in the database
    """
    try:
        # This is a placeholder for processing pending notifications
        # In a real implementation, you would:
        # 1. Query for pending notifications in the database
        # 2. Process them in batches
        # 3. Mark them as sent
        
        logger.info("Processing pending email notifications")
        
        return {
            "success": True,
            "message": "Pending notifications processed"
        }
        
    except Exception as e:
        logger.error(f"Error processing pending notifications: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Worker configuration
class WorkerSettings:
    """Settings for ARQ worker"""
    redis_settings = redis_settings
    functions = [
        send_email,
        send_user_invitation,
        send_team_invitation,
        send_document_share_notification,
        send_password_reset,
        send_bulk_emails,
    ]
    cron_jobs = [
        cron(process_pending_notifications, minute={0, 30}),  # Every 30 minutes
    ]
    max_jobs = 20  # Can handle more concurrent email jobs
    job_timeout = 60  # 1 minute timeout for email sending