"""Celery tasks for indexing retries."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.database import SessionLocal
from app.db.models import Document
from app.schemas.enums import IndexingStatus
from app.services.reindex_service import ReindexService

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


async def _retry_document_indexing(
    document_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        with SessionLocal() as db:
            document = (
                db.query(Document)
                .filter(Document.id == document_id)
                .first()
            )
            if not document:
                msg = (
                    f"Document {document_id} not found; "
                    "skipping indexing retry."
                )
                logger.info(msg)
                return {"success": True, "skipped": True, "message": msg}

            reindex_service = ReindexService(user_id=user_id)
            success = await reindex_service.reindex_document(db, document)

            if success:
                document.indexing_error = None
                document.indexed = IndexingStatus.INDEXED
                db.commit()
                logger.info("✅ Indexing retry succeeded for document %s", document_id)
            else:
                document.indexing_error = (
                    document.indexing_error or "Indexing retry failed; see logs for details."
                )
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                logger.error("❌ Indexing retry failed for document %s", document_id)

            return {"success": success}
    except Exception as exc:
        logger.exception("Unexpected error retrying indexing for %s: %s", document_id, exc)
        return {"success": False, "error": str(exc)}


@celery_app.task(name="indexing.retry_document_indexing")
def retry_document_indexing_task(
    document_id: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _run_async(_retry_document_indexing(document_id, user_id))


async def _auto_retry_failed_indexing() -> Dict[str, Any]:
    max_batch = 10
    processed = 0
    successes = 0

    with SessionLocal() as db:
        documents = (
            db.query(Document)
            .filter(Document.indexed == IndexingStatus.INDEXING_ERROR)
            .order_by(Document.updated_at.asc())
            .limit(max_batch)
            .all()
        )

        if not documents:
            logger.debug("No documents pending indexing retry")
            return {"processed": 0, "successes": 0}

        logger.info("Auto retrying indexing for %s documents", len(documents))
        for document in documents:
            processed += 1
            result = await _retry_document_indexing(
                str(document.id), user_id=str(document.created_by)
            )
            if result.get("success"):
                successes += 1
            await asyncio.sleep(0.1)

    return {
        "processed": processed,
        "successes": successes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@celery_app.task(name="indexing.auto_retry_failed_indexing")
def auto_retry_failed_indexing_task() -> Dict[str, Any]:
    return _run_async(_auto_retry_failed_indexing())
