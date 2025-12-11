"""
Approval Worker for Camunda External Tasks

Handles checking signature/approval status and storing signed documents.

Topics:
- check-approval-status: Check signature request status
- store-signed-document: Download and store signed document

Expected variables for check-approval-status:
- tenant_id: UUID of the tenant
- signature_request_id: UUID of the signature request to check

Expected variables for store-signed-document:
- tenant_id: UUID of the tenant
- signature_request_id: UUID of the signature request
- document_id: Original document ID

Output variables:
- approval_status: current status (pending, completed, declined, expired)
- completion_percentage: 0-100
- signed_document_id: (optional) ID of stored signed document
"""

import logging
import httpx
from typing import Optional

from app.workers.base_worker import BaseWorker, ExternalTask, TaskResult
from app.core.config import get_settings


logger = logging.getLogger(__name__)


class ApprovalStatusWorker(BaseWorker):
    """
    External task worker for checking approval/signature status.

    Polls the signature request status and returns when:
    - All signatures completed
    - Request declined
    - Request expired
    """

    TOPIC = "check-approval-status"

    # Status mappings
    COMPLETED_STATUSES = ["completed", "signed"]
    FAILED_STATUSES = ["declined", "expired", "cancelled"]
    PENDING_STATUSES = ["pending", "sent", "viewed", "draft"]

    def __init__(self):
        super().__init__(
            topic_name=self.TOPIC,
            lock_duration=30000,  # 30 seconds - quick check
            max_tasks=10,  # Can check many at once
            variables=[
                "tenant_id",
                "signature_request_id",
                "signature_external_id"
            ]
        )
        self.settings = get_settings()
        self._api_client: Optional[httpx.AsyncClient] = None

    async def _get_api_client(self) -> httpx.AsyncClient:
        """Get HTTP client for main API."""
        if self._api_client is None or self._api_client.is_closed:
            self._api_client = httpx.AsyncClient(
                base_url=self.settings.SIGNATURE_SERVICE_URL,
                timeout=30.0,
                headers={
                    "X-API-Key": self.settings.MICROSERVICES_API_KEY,
                    "Content-Type": "application/json"
                }
            )
        return self._api_client

    async def handle(self, task: ExternalTask) -> TaskResult:
        """
        Check signature request status.

        Returns immediately with current status.
        The BPMN process should use a timer or message event
        to wait and re-check if still pending.
        """
        self.logger.info(f"Checking approval status for task {task.id}")

        # Extract variables
        tenant_id = task.get_variable("tenant_id")
        signature_request_id = task.get_variable("signature_request_id")

        # Validate required variables
        if not tenant_id:
            return TaskResult.fail("Missing required variable: tenant_id")
        if not signature_request_id:
            return TaskResult.fail("Missing required variable: signature_request_id")

        try:
            client = await self._get_api_client()

            # Get signature request status
            response = await client.get(
                f"/api/v1/signatures/requests/{signature_request_id}",
                headers={
                    "X-Tenant-ID": tenant_id
                }
            )

            if response.status_code == 404:
                return TaskResult.bpmn_error(
                    "SIGNATURE_NOT_FOUND",
                    f"Signature request {signature_request_id} not found"
                )

            if response.status_code != 200:
                return TaskResult.fail(
                    f"Failed to get signature status: {response.status_code}",
                    error_details=response.text,
                    retries=3,
                    retry_timeout=30000
                )

            data = response.json()
            status = data.get("status", "unknown").lower()

            # Calculate completion percentage from signers
            signers = data.get("signers", [])
            signed_count = sum(1 for s in signers if s.get("status") in ["signed", "completed"])
            total_signers = len(signers) if signers else 1
            completion_percentage = int((signed_count / total_signers) * 100)

            self.logger.info(
                f"Signature {signature_request_id} status: {status} ({completion_percentage}% complete)"
            )

            result_vars = {
                "approval_status": status,
                "completion_percentage": completion_percentage,
                "signers_completed": signed_count,
                "signers_total": total_signers
            }

            # Check final status
            if status in self.COMPLETED_STATUSES or completion_percentage == 100:
                result_vars["approval_completed"] = True
                result_vars["approval_success"] = True
                return TaskResult.complete(result_vars)

            if status in self.FAILED_STATUSES:
                result_vars["approval_completed"] = True
                result_vars["approval_success"] = False
                # Use BPMN error to trigger error boundary event
                return TaskResult.bpmn_error(
                    f"SIGNATURE_{status.upper()}",
                    f"Signature request {status}",
                    variables=result_vars
                )

            # Still pending - complete with current status
            # The BPMN process decides whether to wait and re-check
            result_vars["approval_completed"] = False
            result_vars["approval_success"] = False
            return TaskResult.complete(result_vars)

        except httpx.TimeoutException as e:
            self.logger.error(f"Timeout checking status: {e}")
            return TaskResult.fail(
                "Status check timeout",
                retries=3,
                retry_timeout=15000
            )
        except Exception as e:
            self.logger.exception(f"Error checking approval status: {e}")
            return TaskResult.fail(str(e), retries=2)

    async def stop(self) -> None:
        """Clean up resources."""
        if self._api_client:
            await self._api_client.aclose()
            self._api_client = None
        await super().stop()


class StoreSignedDocumentWorker(BaseWorker):
    """
    External task worker for storing signed documents.

    Downloads the signed document from the provider and stores it.
    """

    TOPIC = "store-signed-document"

    def __init__(self):
        super().__init__(
            topic_name=self.TOPIC,
            lock_duration=120000,  # 2 minutes for download/upload
            max_tasks=3,
            variables=[
                "tenant_id",
                "signature_request_id",
                "document_id"
            ]
        )
        self.settings = get_settings()
        self._api_client: Optional[httpx.AsyncClient] = None

    async def _get_api_client(self) -> httpx.AsyncClient:
        """Get HTTP client for main API."""
        if self._api_client is None or self._api_client.is_closed:
            self._api_client = httpx.AsyncClient(
                base_url=self.settings.SIGNATURE_SERVICE_URL,
                timeout=120.0,  # Long timeout for file operations
                headers={
                    "X-API-Key": self.settings.MICROSERVICES_API_KEY,
                    "Content-Type": "application/json"
                }
            )
        return self._api_client

    async def handle(self, task: ExternalTask) -> TaskResult:
        """
        Download and store signed document.
        """
        self.logger.info(f"Storing signed document for task {task.id}")

        # Extract variables
        tenant_id = task.get_variable("tenant_id")
        signature_request_id = task.get_variable("signature_request_id")
        document_id = task.get_variable("document_id")

        # Validate
        if not tenant_id:
            return TaskResult.fail("Missing required variable: tenant_id")
        if not signature_request_id:
            return TaskResult.fail("Missing required variable: signature_request_id")

        try:
            client = await self._get_api_client()

            # Download signed document
            self.logger.info(f"Downloading signed document for request {signature_request_id}")

            response = await client.get(
                f"/api/v1/signatures/requests/{signature_request_id}/download",
                headers={
                    "X-Tenant-ID": tenant_id
                }
            )

            if response.status_code != 200:
                return TaskResult.fail(
                    f"Failed to download signed document: {response.status_code}",
                    error_details=response.text,
                    retries=2
                )

            download_data = response.json()
            document_content = download_data.get("document")  # Base64
            filename = download_data.get("filename", f"signed_{signature_request_id}.pdf")

            if not document_content:
                return TaskResult.fail("No document content received")

            self.logger.info(f"Downloaded signed document: {filename}")

            # Store the signed document as a new version or separate file
            # This calls the storage service through the main API
            store_response = await client.post(
                "/api/v1/documents/upload-signed",
                json={
                    "original_document_id": document_id,
                    "signature_request_id": signature_request_id,
                    "content_base64": document_content,
                    "filename": filename
                },
                headers={
                    "X-Tenant-ID": tenant_id
                }
            )

            if store_response.status_code not in (200, 201):
                self.logger.warning(f"Failed to store signed document: {store_response.status_code}")
                # Still return success with the download info
                return TaskResult.complete({
                    "signed_document_stored": False,
                    "signed_document_filename": filename,
                    "store_error": store_response.text
                })

            store_data = store_response.json()

            return TaskResult.complete({
                "signed_document_stored": True,
                "signed_document_id": store_data.get("id"),
                "signed_document_filename": filename,
                "signed_document_path": store_data.get("storage_path")
            })

        except httpx.TimeoutException as e:
            self.logger.error(f"Timeout storing document: {e}")
            return TaskResult.fail(
                "Document storage timeout",
                retries=2,
                retry_timeout=60000
            )
        except Exception as e:
            self.logger.exception(f"Error storing signed document: {e}")
            return TaskResult.fail(str(e), retries=1)

    async def stop(self) -> None:
        """Clean up resources."""
        if self._api_client:
            await self._api_client.aclose()
            self._api_client = None
        await super().stop()


# Worker instance factories
def create_approval_status_worker() -> ApprovalStatusWorker:
    """Create a new approval status worker instance."""
    return ApprovalStatusWorker()


def create_store_signed_document_worker() -> StoreSignedDocumentWorker:
    """Create a new store signed document worker instance."""
    return StoreSignedDocumentWorker()
