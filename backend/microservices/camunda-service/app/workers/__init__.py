# Workers module - External task workers for Camunda

from app.workers.base_worker import (
    BaseWorker,
    ExternalTask,
    TaskResult,
    WorkerManager,
    get_worker_manager
)
from app.workers.signature_worker import SignatureWorker, create_signature_worker
from app.workers.email_worker import EmailWorker, create_email_worker
from app.workers.approval_worker import (
    ApprovalStatusWorker,
    StoreSignedDocumentWorker,
    create_approval_status_worker,
    create_store_signed_document_worker
)

__all__ = [
    # Base classes
    "BaseWorker",
    "ExternalTask",
    "TaskResult",
    "WorkerManager",
    "get_worker_manager",
    # Workers
    "SignatureWorker",
    "EmailWorker",
    "ApprovalStatusWorker",
    "StoreSignedDocumentWorker",
    # Factories
    "create_signature_worker",
    "create_email_worker",
    "create_approval_status_worker",
    "create_store_signed_document_worker",
]
