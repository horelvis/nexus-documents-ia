"""
Email Worker for Camunda External Tasks

Handles sending email notifications via the main API.
Topic: send-notification

Expected variables:
- tenant_id: UUID of the tenant
- notification_type: Type of notification (document_approved, document_rejected, signature_request, etc.)
- recipients: JSON array of recipients [{email, name}] or single email string
- subject: (optional) Email subject - will use template default if not provided
- template_data: JSON object with template variables
- document_id: (optional) Related document ID
- user_id: (optional) User who triggered the notification

Output variables:
- notification_sent: boolean
- notification_id: (optional) ID if stored in database
"""

import logging
import httpx
from typing import Optional, List, Dict, Any

from app.workers.base_worker import BaseWorker, ExternalTask, TaskResult
from app.core.config import get_settings


logger = logging.getLogger(__name__)


class EmailWorker(BaseWorker):
    """
    External task worker for sending email notifications.

    Supports various notification types:
    - document_approved: Document approved in workflow
    - document_rejected: Document rejected in workflow
    - signature_requested: Signature request sent
    - signature_completed: All signatures collected
    - task_assigned: User task assigned
    - workflow_completed: Workflow finished
    """

    TOPIC = "send-notification"

    # Notification type to template mapping
    TEMPLATES = {
        "document_approved": "document_approval",
        "document_rejected": "document_rejection",
        "signature_requested": "signature_request",
        "signature_completed": "signature_complete",
        "task_assigned": "task_assignment",
        "workflow_completed": "workflow_complete",
        "generic": "generic_notification"
    }

    def __init__(self):
        super().__init__(
            topic_name=self.TOPIC,
            lock_duration=60000,  # 1 minute
            max_tasks=5,  # Can process multiple notifications in parallel
            variables=[
                "tenant_id",
                "notification_type",
                "recipients",
                "subject",
                "template_data",
                "document_id",
                "user_id"
            ]
        )
        self.settings = get_settings()
        self._api_client: Optional[httpx.AsyncClient] = None

    async def _get_api_client(self) -> httpx.AsyncClient:
        """Get HTTP client for main API."""
        if self._api_client is None or self._api_client.is_closed:
            self._api_client = httpx.AsyncClient(
                base_url=self.settings.SIGNATURE_SERVICE_URL,  # Main API URL
                timeout=30.0,
                headers={
                    "X-API-Key": self.settings.MICROSERVICES_API_KEY,
                    "Content-Type": "application/json"
                }
            )
        return self._api_client

    def _parse_recipients(self, recipients: Any) -> List[Dict[str, str]]:
        """Parse recipients from various formats."""
        if isinstance(recipients, str):
            # Try to parse as JSON
            import json
            try:
                parsed = json.loads(recipients)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict):
                    return [parsed]
            except json.JSONDecodeError:
                # Assume single email address
                return [{"email": recipients, "name": recipients.split("@")[0]}]

        if isinstance(recipients, list):
            result = []
            for r in recipients:
                if isinstance(r, str):
                    result.append({"email": r, "name": r.split("@")[0]})
                elif isinstance(r, dict):
                    result.append(r)
            return result

        if isinstance(recipients, dict):
            return [recipients]

        return []

    async def handle(self, task: ExternalTask) -> TaskResult:
        """
        Handle notification sending task.

        Calls the main API to send email notifications.
        """
        self.logger.info(f"Processing notification task {task.id}")

        # Extract variables
        tenant_id = task.get_variable("tenant_id")
        notification_type = task.get_variable("notification_type", "generic")
        recipients_raw = task.get_variable("recipients")
        subject = task.get_variable("subject")
        template_data_raw = task.get_variable("template_data", {})
        document_id = task.get_variable("document_id")
        user_id = task.get_variable("user_id")

        # Validate required variables
        if not tenant_id:
            return TaskResult.fail("Missing required variable: tenant_id")
        if not recipients_raw:
            return TaskResult.fail("Missing required variable: recipients")

        # Parse recipients
        recipients = self._parse_recipients(recipients_raw)
        if not recipients:
            return TaskResult.fail("No valid recipients found")

        # Parse template_data if string
        template_data = template_data_raw
        if isinstance(template_data_raw, str):
            import json
            try:
                template_data = json.loads(template_data_raw)
            except json.JSONDecodeError:
                template_data = {}

        # Get template name
        template = self.TEMPLATES.get(notification_type, "generic_notification")

        try:
            client = await self._get_api_client()

            # Build notification payload
            notifications_sent = 0
            errors = []

            for recipient in recipients:
                email = recipient.get("email")
                name = recipient.get("name", "")

                if not email:
                    continue

                payload = {
                    "to_email": email,
                    "to_name": name,
                    "template": template,
                    "subject": subject,
                    "context": {
                        **template_data,
                        "recipient_name": name,
                        "recipient_email": email,
                        "notification_type": notification_type
                    }
                }

                if document_id:
                    payload["context"]["document_id"] = document_id

                self.logger.info(f"Sending {notification_type} notification to {email}")

                # Call main API notification endpoint
                response = await client.post(
                    "/api/v1/notifications/send",
                    json=payload,
                    headers={
                        "X-Tenant-ID": tenant_id,
                        "X-User-ID": user_id or "system"
                    }
                )

                if response.status_code in (200, 201, 202):
                    notifications_sent += 1
                else:
                    error_msg = f"Failed to send to {email}: {response.status_code}"
                    self.logger.warning(error_msg)
                    errors.append(error_msg)

            # Determine result
            if notifications_sent == 0:
                return TaskResult.fail(
                    f"Failed to send any notifications",
                    error_details="; ".join(errors) if errors else None,
                    retries=2
                )

            if errors:
                # Partial success
                self.logger.warning(f"Sent {notifications_sent}/{len(recipients)} notifications. Errors: {errors}")

            return TaskResult.complete({
                "notification_sent": True,
                "notifications_count": notifications_sent,
                "notification_type": notification_type,
                "recipients_count": len(recipients)
            })

        except httpx.TimeoutException as e:
            self.logger.error(f"Timeout sending notification: {e}")
            return TaskResult.fail(
                "Notification service timeout",
                error_details=str(e),
                retries=3,
                retry_timeout=15000
            )
        except httpx.HTTPError as e:
            self.logger.error(f"HTTP error sending notification: {e}")
            return TaskResult.fail(
                f"Notification service error: {e}",
                retries=2
            )
        except Exception as e:
            self.logger.exception(f"Unexpected error in email worker: {e}")
            return TaskResult.fail(
                f"Unexpected error: {e}",
                error_details=str(e),
                retries=1
            )

    async def stop(self) -> None:
        """Clean up resources."""
        if self._api_client:
            await self._api_client.aclose()
            self._api_client = None
        await super().stop()


# Worker instance factory
def create_email_worker() -> EmailWorker:
    """Create a new email worker instance."""
    return EmailWorker()
