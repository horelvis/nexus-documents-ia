"""Notification activities for Temporalio workflows"""
from typing import Dict, Any, List
import logging
from datetime import datetime

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def send_email_notification(notification_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send email notification
    
    Args:
        notification_data: Email notification details
        
    Returns:
        Email sending confirmation
    """
    recipient = notification_data.get("recipient")
    subject = notification_data.get("subject")
    
    activity.logger.info(f"Sending email to {recipient}: {subject}")
    
    try:
        # Simulate email sending (in real implementation, call email service)
        
        return {
            "success": True,
            "recipient": recipient,
            "subject": subject,
            "message_id": f"email_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "sent_at": datetime.utcnow().isoformat(),
            "delivery_status": "sent"
        }
        
    except Exception as e:
        activity.logger.error(f"Error sending email: {e}")
        return {
            "success": False,
            "error": str(e),
            "recipient": recipient
        }


@activity.defn
async def send_system_notification(notification_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send system/in-app notification
    
    Args:
        notification_data: System notification details
        
    Returns:
        System notification confirmation
    """
    user_id = notification_data.get("user_id")
    notification_type = notification_data.get("notification_type")
    message = notification_data.get("message")
    
    activity.logger.info(f"Sending system notification to user {user_id}: {notification_type}")
    
    try:
        # Simulate system notification (in real implementation, call notification service)
        
        return {
            "success": True,
            "user_id": user_id,
            "notification_type": notification_type,
            "message": message,
            "notification_id": f"notif_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "sent_at": datetime.utcnow().isoformat(),
            "delivery_channel": "system"
        }
        
    except Exception as e:
        activity.logger.error(f"Error sending system notification: {e}")
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id
        }


@activity.defn
async def notify_stakeholders(notification_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Notify multiple stakeholders about workflow progress
    
    Args:
        notification_data: Stakeholder notification information
        
    Returns:
        Multi-stakeholder notification results
    """
    contract_id = notification_data.get("contract_id")
    decision = notification_data.get("decision")
    employee_name = notification_data.get("employee_name")
    
    activity.logger.info(f"Notifying stakeholders for contract {contract_id}: {decision}")
    
    try:
        notifications_sent = []
        
        # Notify HR
        hr_notification = {
            "stakeholder": "HR",
            "user_id": notification_data.get("user_id"),
            "message": f"Contract renewal decision for {employee_name}: {decision}",
            "notification_type": "workflow_completion",
            "sent_at": datetime.utcnow().isoformat(),
            "success": True
        }
        notifications_sent.append(hr_notification)
        
        # Notify Manager (if different from user)
        if notification_data.get("manager_id") and notification_data.get("manager_id") != notification_data.get("user_id"):
            manager_notification = {
                "stakeholder": "Manager",
                "user_id": notification_data.get("manager_id"),
                "message": f"Team member {employee_name} contract decision: {decision}",
                "notification_type": "team_update",
                "sent_at": datetime.utcnow().isoformat(),
                "success": True
            }
            notifications_sent.append(manager_notification)
        
        # Notify Employee (if renewal)
        if decision == "RENEW":
            employee_notification = {
                "stakeholder": "Employee",
                "user_id": notification_data.get("employee_id"),
                "message": f"Great news! Your contract has been renewed. New contract documents are available.",
                "notification_type": "contract_renewal",
                "sent_at": datetime.utcnow().isoformat(),
                "success": True
            }
            notifications_sent.append(employee_notification)
        
        # Notify Legal (if termination)
        elif decision == "TERMINATE":
            legal_notification = {
                "stakeholder": "Legal",
                "user_id": "legal_team",
                "message": f"Contract termination processed for {employee_name}. Review termination documents.",
                "notification_type": "legal_review",
                "sent_at": datetime.utcnow().isoformat(),
                "success": True
            }
            notifications_sent.append(legal_notification)
        
        return {
            "success": True,
            "contract_id": contract_id,
            "decision": decision,
            "notifications_sent": len(notifications_sent),
            "sent_to": [n["stakeholder"] for n in notifications_sent],
            "details": notifications_sent,
            "completed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        activity.logger.error(f"Error notifying stakeholders: {e}")
        return {
            "success": False,
            "error": str(e),
            "contract_id": contract_id,
            "decision": decision
        }