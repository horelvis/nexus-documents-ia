"""
Signature Worker for Camunda External Tasks

Handles signature request creation and sending via the main API.
Topic: send-signature-request

Expected variables:
- document_id: UUID of the document to sign
- tenant_id: UUID of the tenant
- signers: JSON array of signers [{name, email, role}]
- provider_id: (optional) UUID of signature provider, uses default if not provided
- requester_id: UUID of user requesting signature
- message: (optional) Message for signers

Output variables:
- signature_request_id: UUID of created signature request
- signature_external_id: External ID from provider
- signature_status: Current status of request
"""

import logging
import httpx
from typing import Optional

from app.workers.base_worker import BaseWorker, ExternalTask, TaskResult
from app.core.config import get_settings


logger = logging.getLogger(__name__)


class SignatureWorker(BaseWorker):
    """
    External task worker for sending signature requests.

    Integrates with the main API's signature endpoints which handle:
    - Secure credential management
    - Multi-tenant isolation
    - Audit trail creation
    """

    TOPIC = "send-signature-request"

    def __init__(self):
        super().__init__(
            topic_name=self.TOPIC,
            lock_duration=120000,  # 2 minutes - signature creation can take time
            max_tasks=3,
            variables=[
                "document_id",
                "tenant_id",
                "signers",
                "provider_id",
                "requester_id",
                "message"
            ]
        )
        self.settings = get_settings()
        self._api_client: Optional[httpx.AsyncClient] = None

    async def _get_api_client(self) -> httpx.AsyncClient:
        """Get HTTP client for main API."""
        if self._api_client is None or self._api_client.is_closed:
            self._api_client = httpx.AsyncClient(
                base_url=self.settings.SIGNATURE_SERVICE_URL,
                timeout=60.0,
                headers={
                    "X-API-Key": self.settings.MICROSERVICES_API_KEY,
                    "Content-Type": "application/json"
                }
            )
        return self._api_client

    async def handle(self, task: ExternalTask) -> TaskResult:
        """
        Handle signature request task.

        Creates a signature request and sends it to the provider.
        """
        self.logger.info(f"Processing signature request task {task.id}")

        # Extract variables
        document_id = task.get_variable("document_id")
        tenant_id = task.get_variable("tenant_id")
        signers = task.get_variable("signers")
        provider_id = task.get_variable("provider_id")
        requester_id = task.get_variable("requester_id")
        message = task.get_variable("message")

        # Validate required variables
        if not document_id:
            return TaskResult.fail("Missing required variable: document_id")
        if not tenant_id:
            return TaskResult.fail("Missing required variable: tenant_id")
        if not signers:
            return TaskResult.fail("Missing required variable: signers")

        # Parse signers if string
        if isinstance(signers, str):
            import json
            try:
                signers = json.loads(signers)
            except json.JSONDecodeError as e:
                return TaskResult.fail(f"Invalid signers JSON: {e}")

        # Validate signers structure
        if not isinstance(signers, list) or len(signers) == 0:
            return TaskResult.fail("signers must be a non-empty array")

        for signer in signers:
            if not isinstance(signer, dict):
                return TaskResult.fail("Each signer must be an object")
            if "email" not in signer or "name" not in signer:
                return TaskResult.fail("Each signer must have 'email' and 'name'")

        try:
            client = await self._get_api_client()

            # Step 1: Create signature request
            create_payload = {
                "document_id": document_id,
                "signers": [
                    {
                        "name": s["name"],
                        "email": s["email"],
                        "role": s.get("role", "signer"),
                        "order": s.get("order", i + 1)
                    }
                    for i, s in enumerate(signers)
                ]
            }

            if provider_id:
                create_payload["provider_id"] = provider_id

            self.logger.info(f"Creating signature request for document {document_id}")

            # Call main API to create signature request
            # Note: The main API handles authentication via internal API key
            response = await client.post(
                f"/api/v1/signatures/requests",
                json=create_payload,
                headers={
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": requester_id or "system"
                }
            )

            if response.status_code not in (200, 201):
                error_detail = response.text
                self.logger.error(f"Failed to create signature request: {response.status_code} - {error_detail}")
                return TaskResult.fail(
                    f"Failed to create signature request: {response.status_code}",
                    error_details=error_detail,
                    retries=2
                )

            create_result = response.json()
            signature_request_id = create_result.get("id")

            if not signature_request_id:
                return TaskResult.fail("No signature request ID returned")

            self.logger.info(f"Created signature request {signature_request_id}")

            # Step 2: Send the signature request
            send_response = await client.post(
                f"/api/v1/signatures/requests/{signature_request_id}/send",
                headers={
                    "X-Tenant-ID": tenant_id,
                    "X-User-ID": requester_id or "system"
                }
            )

            if send_response.status_code not in (200, 201):
                error_detail = send_response.text
                self.logger.error(f"Failed to send signature request: {send_response.status_code} - {error_detail}")
                # Return partial success - request created but not sent
                return TaskResult.bpmn_error(
                    "SIGNATURE_SEND_FAILED",
                    f"Signature request created but sending failed: {send_response.status_code}",
                    variables={
                        "signature_request_id": signature_request_id,
                        "signature_status": "draft",
                        "error_message": error_detail
                    }
                )

            send_result = send_response.json()

            # Success - return result variables
            return TaskResult.complete({
                "signature_request_id": signature_request_id,
                "signature_external_id": send_result.get("external_id", ""),
                "signature_status": send_result.get("status", "sent"),
                "signature_sent_at": send_result.get("sent_at", "")
            })

        except httpx.TimeoutException as e:
            self.logger.error(f"Timeout calling signature service: {e}")
            return TaskResult.fail(
                "Signature service timeout",
                error_details=str(e),
                retries=3,
                retry_timeout=30000
            )
        except httpx.HTTPError as e:
            self.logger.error(f"HTTP error calling signature service: {e}")
            return TaskResult.fail(
                f"Signature service error: {e}",
                retries=2
            )
        except Exception as e:
            self.logger.exception(f"Unexpected error in signature worker: {e}")
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
def create_signature_worker() -> SignatureWorker:
    """Create a new signature worker instance."""
    return SignatureWorker()
