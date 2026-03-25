from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from celery.result import AsyncResult

from worker_app.core.config import settings
from worker_app.tasks.preview_tasks import (
    generate_document_preview_task,
    generate_preview_batch_task,
)
from worker_app.tasks.email_tasks import (
    send_email_task,
    send_bulk_emails_task,
    send_user_invitation_task,
    send_team_invitation_task,
    send_document_share_notification_task,
    send_password_reset_task,
)
from worker_app.tasks.indexing_tasks import retry_document_indexing_task
from worker_app.tasks.verification_tasks import verify_claim_task, batch_verify_claims_task
from worker_app.tasks.connector_tasks import sync_and_index_connector_task, index_pending_documents_task
from worker_app.celery_app import celery_app

app = FastAPI(title="Background Worker", version="1.0.0")


def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.microservices_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")


class PreviewRequest(BaseModel):
    document_id: str
    tenant_id: str
    user_id: str
    preview_type: str = "all"
    force_regenerate: bool = False
    priority: str = "default"


class PreviewBatchRequest(BaseModel):
    document_ids: List[str]
    tenant_id: str
    user_id: str
    preview_type: str = "all"
    batch_size: int = 5
    priority: str = "default"


class EmailRequest(BaseModel):
    to_email: str
    subject: str
    template_name: str
    template_data: Dict[str, Any]
    priority: str = "default"


class BulkEmailRequest(BaseModel):
    email_batch: List[Dict[str, Any]]
    batch_size: int = 10
    priority: str = "low"


class UserInvitationRequest(BaseModel):
    user_email: str
    invited_by_name: str
    tenant_name: str
    invitation_link: str


class TeamInvitationRequest(BaseModel):
    invitation_id: str
    tenant_id: str


class ShareNotificationRequest(BaseModel):
    share_id: str
    tenant_id: str


class PasswordResetRequest(BaseModel):
    user_email: str
    reset_token: str
    user_name: Optional[str] = None


class IndexRetryRequest(BaseModel):
    document_id: str
    tenant_id: str
    user_id: Optional[str] = None
    priority: str = "default"


class VerifyClaimRequest(BaseModel):
    """Request to verify a single claim."""
    claim_id: str
    claim_text: str
    tenant_id: str
    context_document_ids: Optional[List[str]] = None
    collections: Optional[List[str]] = None
    confidence_threshold: float = 0.7
    session_id: Optional[str] = None


class BatchVerifyClaimsRequest(BaseModel):
    """Request to verify multiple claims."""
    claims: List[Dict[str, str]]  # [{"id": "...", "text": "..."}]
    tenant_id: str
    context_document_ids: Optional[List[str]] = None
    collections: Optional[List[str]] = None
    confidence_threshold: float = 0.7


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/tasks/preview")
async def enqueue_preview(request: PreviewRequest, _: None = Depends(verify_api_key)):
    job = generate_document_preview_task.delay(
        request.document_id,
        request.tenant_id,
        request.user_id,
        request.preview_type,
        request.force_regenerate,
    )
    return {"job_id": job.id}


@app.post("/tasks/preview/batch")
async def enqueue_preview_batch(request: PreviewBatchRequest, _: None = Depends(verify_api_key)):
    job = generate_preview_batch_task.delay(
        request.document_ids,
        request.tenant_id,
        request.user_id,
        request.preview_type,
        request.batch_size,
    )
    return {"job_id": job.id}


@app.post("/tasks/email/send")
async def enqueue_email(request: EmailRequest, _: None = Depends(verify_api_key)):
    job = send_email_task.delay(
        request.to_email,
        request.subject,
        request.template_name,
        request.template_data,
    )
    return {"job_id": job.id}


@app.post("/tasks/email/bulk")
async def enqueue_bulk_email(request: BulkEmailRequest, _: None = Depends(verify_api_key)):
    job = send_bulk_emails_task.delay(request.email_batch, request.batch_size)
    return {"job_id": job.id}


@app.post("/tasks/email/user-invitation")
async def enqueue_user_invitation(request: UserInvitationRequest, _: None = Depends(verify_api_key)):
    job = send_user_invitation_task.delay(
        request.user_email,
        request.invited_by_name,
        request.tenant_name,
        request.invitation_link,
    )
    return {"job_id": job.id}


@app.post("/tasks/email/team-invitation")
async def enqueue_team_invitation(request: TeamInvitationRequest, _: None = Depends(verify_api_key)):
    job = send_team_invitation_task.delay(request.invitation_id, request.tenant_id)
    return {"job_id": job.id}


@app.post("/tasks/email/share-notification")
async def enqueue_share_notification(request: ShareNotificationRequest, _: None = Depends(verify_api_key)):
    job = send_document_share_notification_task.delay(request.share_id, request.tenant_id)
    return {"job_id": job.id}


@app.post("/tasks/email/password-reset")
async def enqueue_password_reset(request: PasswordResetRequest, _: None = Depends(verify_api_key)):
    job = send_password_reset_task.delay(request.user_email, request.reset_token, request.user_name)
    return {"job_id": job.id}


@app.post("/tasks/indexing/retry")
async def enqueue_index_retry(request: IndexRetryRequest, _: None = Depends(verify_api_key)):
    job = retry_document_indexing_task.delay(
        request.document_id,
        request.tenant_id,
        request.user_id,
    )
    return {"job_id": job.id}


# =============================================================================
# Connector Sync Tasks
# =============================================================================

class ConnectorSyncRequest(BaseModel):
    connector_id: str
    full_sync: bool = False
    batch_size: int = 10


class ConnectorIndexPendingRequest(BaseModel):
    connector_id: str
    batch_size: int = 10
    max_documents: Optional[int] = None


@app.post("/tasks/connector/sync")
async def enqueue_connector_sync(request: ConnectorSyncRequest, _: None = Depends(verify_api_key)):
    """Trigger connector sync (metadata fetch from Alfresco + indexing to Weaviate)"""
    job = sync_and_index_connector_task.delay(
        request.connector_id,
        full_sync=request.full_sync,
        batch_size=request.batch_size,
    )
    return {"job_id": job.id, "status": "queued", "connector_id": request.connector_id}


@app.post("/tasks/connector/index-pending")
async def enqueue_connector_index_pending(request: ConnectorIndexPendingRequest, _: None = Depends(verify_api_key)):
    """Index pending documents from a connector to Weaviate"""
    job = index_pending_documents_task.delay(
        request.connector_id,
        batch_size=request.batch_size,
        max_documents=request.max_documents,
    )
    return {"job_id": job.id, "status": "queued", "connector_id": request.connector_id}


@app.get("/tasks/status/{job_id}")
async def get_task_status(job_id: str, _: None = Depends(verify_api_key)):
    result = AsyncResult(job_id, app=celery_app)
    response = {
        "job_id": job_id,
        "status": result.status,
    }
    if result.ready():
        response["result"] = result.result
    return response


@app.get("/tasks/stats")
async def get_stats(_: None = Depends(verify_api_key)):
    return {"status": "ok"}


# =============================================================================
# Verification Tasks (Agent Self-Verifies pattern)
# =============================================================================


@app.post("/tasks/verification/verify-claim")
async def enqueue_verify_claim(request: VerifyClaimRequest, _: None = Depends(verify_api_key)):
    """
    Enqueue a claim verification task.

    The task searches Weaviate for evidence and uses SGLang to evaluate
    whether the evidence supports the claim.
    """
    job = verify_claim_task.delay(
        claim_id=request.claim_id,
        claim_text=request.claim_text,
        tenant_id=request.tenant_id,
        context_document_ids=request.context_document_ids,
        collections=request.collections,
        confidence_threshold=request.confidence_threshold,
        session_id=request.session_id,
    )
    return {"job_id": job.id}


@app.post("/tasks/verification/batch-verify")
async def enqueue_batch_verify(request: BatchVerifyClaimsRequest, _: None = Depends(verify_api_key)):
    """
    Enqueue a batch claim verification task.

    Verifies multiple claims sequentially (not parallel) to ensure
    each claim is verified against the most recent context.
    """
    job = batch_verify_claims_task.delay(
        claims=request.claims,
        tenant_id=request.tenant_id,
        context_document_ids=request.context_document_ids,
        collections=request.collections,
        confidence_threshold=request.confidence_threshold,
    )
    return {"job_id": job.id}
