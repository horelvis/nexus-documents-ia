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
