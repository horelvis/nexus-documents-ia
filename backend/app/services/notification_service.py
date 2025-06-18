"""
Alternative notification service for document sharing
Provides multiple notification methods beyond email
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID
import json

from sqlalchemy.orm import Session
from app.db.models import User, Document, Notification
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for handling various notification methods"""
    
    def __init__(self, tenant_id: str, user_id: str):
        self.tenant_id = UUID(tenant_id)
        self.user_id = UUID(user_id)
    
    async def create_in_app_notification(
        self,
        db: Session,
        recipient_id: UUID,
        title: str,
        message: str,
        notification_type: str = "share",
        data: Optional[Dict[str, Any]] = None,
        action_url: Optional[str] = None
    ) -> Notification:
        """Create an in-app notification"""
        try:
            notification = Notification(
                tenant_id=self.tenant_id,
                user_id=recipient_id,
                title=title,
                message=message,
                notification_type=notification_type,
                data=data or {},
                action_url=action_url,
                is_read=False,
                created_by=self.user_id
            )
            
            db.add(notification)
            db.commit()
            db.refresh(notification)
            
            logger.info(f"In-app notification created for user {recipient_id}")
            return notification
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create in-app notification: {str(e)}")
            raise
    
    async def send_webhook_notification(
        self,
        webhook_url: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> bool:
        """Send notification via webhook (Slack, Discord, Teams, etc.)"""
        try:
            import httpx
            
            payload = {
                "event": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Webhook notification sent successfully to {webhook_url}")
                    return True
                else:
                    logger.error(f"Webhook notification failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {str(e)}")
            return False
    
    async def send_slack_notification(
        self,
        webhook_url: str,
        document_name: str,
        share_url: str,
        sender_name: str,
        recipient_name: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """Send notification to Slack channel"""
        try:
            import httpx
            
            # Slack message format
            slack_message = {
                "text": f"📄 Document shared: {document_name}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "📄 New Document Share"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Document:*\n{document_name}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Shared by:*\n{sender_name}"
                            }
                        ]
                    }
                ]
            }
            
            if recipient_name:
                slack_message["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Shared with:* {recipient_name}"
                    }
                })
            
            if message:
                slack_message["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Message:* {message}"
                    }
                })
            
            # Add action button
            slack_message["blocks"].append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Document"
                        },
                        "url": share_url,
                        "style": "primary"
                    }
                ]
            })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=slack_message)
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {str(e)}")
            return False
    
    async def send_teams_notification(
        self,
        webhook_url: str,
        document_name: str,
        share_url: str,
        sender_name: str,
        recipient_name: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """Send notification to Microsoft Teams channel"""
        try:
            import httpx
            
            # Teams message format
            teams_message = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "themeColor": "4f46e5",
                "summary": f"Document shared: {document_name}",
                "sections": [
                    {
                        "activityTitle": "📄 New Document Share",
                        "facts": [
                            {
                                "name": "Document:",
                                "value": document_name
                            },
                            {
                                "name": "Shared by:",
                                "value": sender_name
                            }
                        ]
                    }
                ]
            }
            
            if recipient_name:
                teams_message["sections"][0]["facts"].append({
                    "name": "Shared with:",
                    "value": recipient_name
                })
            
            if message:
                teams_message["sections"].append({
                    "text": f"**Message:** {message}"
                })
            
            # Add action button
            teams_message["potentialAction"] = [
                {
                    "@type": "OpenUri",
                    "name": "View Document",
                    "targets": [
                        {
                            "os": "default",
                            "uri": share_url
                        }
                    ]
                }
            ]
            
            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=teams_message)
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Failed to send Teams notification: {str(e)}")
            return False
    
    async def send_sms_notification(
        self,
        phone_number: str,
        document_name: str,
        share_url: str,
        sender_name: str
    ) -> bool:
        """Send SMS notification using Twilio"""
        try:
            # Only if Twilio is configured
            if not all([settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_PHONE_NUMBER]):
                logger.warning("Twilio not configured, skipping SMS notification")
                return False
            
            from twilio.rest import Client
            
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            message_body = f"{sender_name} shared '{document_name}' with you. View it here: {share_url}"
            
            message = client.messages.create(
                body=message_body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=phone_number
            )
            
            logger.info(f"SMS notification sent: {message.sid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS notification: {str(e)}")
            return False
    
    async def send_push_notification(
        self,
        user_token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send push notification using Firebase Cloud Messaging"""
        try:
            # Only if Firebase is configured
            if not settings.FIREBASE_CREDENTIALS:
                logger.warning("Firebase not configured, skipping push notification")
                return False
            
            import firebase_admin
            from firebase_admin import credentials, messaging
            
            # Initialize Firebase if not already done
            if not firebase_admin._apps:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
                firebase_admin.initialize_app(cred)
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=user_token,
            )
            
            response = messaging.send(message)
            logger.info(f"Push notification sent: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send push notification: {str(e)}")
            return False
    
    async def create_share_notification(
        self,
        db: Session,
        recipient_id: Optional[UUID],
        document: Document,
        share_url: str,
        sender_name: str,
        recipient_email: Optional[str] = None,
        message: Optional[str] = None
    ) -> Dict[str, bool]:
        """Create notifications through multiple channels"""
        results = {
            "in_app": False,
            "email": False,
            "slack": False,
            "teams": False,
            "sms": False,
            "push": False
        }
        
        # Always create in-app notification if recipient is a user
        if recipient_id:
            try:
                await self.create_in_app_notification(
                    db=db,
                    recipient_id=recipient_id,
                    title=f"Document shared: {document.title or document.filename}",
                    message=f"{sender_name} shared a document with you",
                    notification_type="document_share",
                    data={
                        "document_id": str(document.id),
                        "share_url": share_url,
                        "sender_name": sender_name
                    },
                    action_url=share_url
                )
                results["in_app"] = True
            except Exception as e:
                logger.error(f"Failed to create in-app notification: {str(e)}")
        
        # Send to configured channels
        if settings.SLACK_WEBHOOK_URL:
            results["slack"] = await self.send_slack_notification(
                webhook_url=settings.SLACK_WEBHOOK_URL,
                document_name=document.title or document.filename,
                share_url=share_url,
                sender_name=sender_name,
                recipient_name=recipient_email,
                message=message
            )
        
        if settings.TEAMS_WEBHOOK_URL:
            results["teams"] = await self.send_teams_notification(
                webhook_url=settings.TEAMS_WEBHOOK_URL,
                document_name=document.title or document.filename,
                share_url=share_url,
                sender_name=sender_name,
                recipient_name=recipient_email,
                message=message
            )
        
        return results


# Singleton instance
notification_service = NotificationService