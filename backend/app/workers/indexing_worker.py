"""
Indexing Worker
Handles retry operations for search indexing in Elasticsearch and Weaviate
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.database import SessionLocal
from app.db.models import Document
from app.schemas.enums import IndexingStatus
from app.services.reindex_service import ReindexService

logger = logging.getLogger(__name__)


async def retry_document_indexing(
    ctx: Dict[str, Any],
    document_id: str,
    tenant_id: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retry full indexing pipeline (Weaviate + Elasticsearch) for a document.
    Uses the ReindexService to execute the same ingest flow used at upload time.
    """
    try:
        with SessionLocal() as db:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            ).first()

            if not document:
                msg = f"Document {document_id} not found for tenant {tenant_id}"
                logger.warning(msg)
                return {"success": False, "error": msg}

            reindex_service = ReindexService(tenant_id=tenant_id, user_id=user_id)
            success = await reindex_service.reindex_document(db, document)

            if success:
                document.indexing_error = None
                document.indexed = IndexingStatus.INDEXED
                db.commit()
                logger.info(f"✅ Indexing retry succeeded for document {document_id}")
            else:
                document.indexing_error = (
                    document.indexing_error or "Indexing retry failed; see logs for details."
                )
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                logger.error(f"❌ Indexing retry failed for document {document_id}")

            return {"success": success}

    except Exception as exc:
        logger.exception(f"Unexpected error retrying indexing for {document_id}: {exc}")
        return {"success": False, "error": str(exc)}


async def auto_retry_failed_indexing(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Periodic cron job to automatically retry documents stuck in INDEXING_ERROR.
    Processes a limited batch to avoid overwhelming the system.
    """
    max_batch = 10
    processed = 0
    successes = 0

    with SessionLocal() as db:
        documents = db.query(Document).filter(
            Document.indexed == IndexingStatus.INDEXING_ERROR
        ).order_by(Document.updated_at.asc()).limit(max_batch).all()

        if not documents:
            logger.debug("No documents pending indexing retry")
            return {"processed": 0, "successes": 0}

        logger.info(f"Auto retrying indexing for {len(documents)} documents")

        for document in documents:
            processed += 1
            result = await retry_document_indexing(
                ctx,
                str(document.id),
                str(document.tenant_id),
                user_id=str(document.created_by),
            )

            if result.get("success"):
                successes += 1

            await asyncio.sleep(0.1)  # small pause to avoid spikes

        return {
            "processed": processed,
            "successes": successes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
