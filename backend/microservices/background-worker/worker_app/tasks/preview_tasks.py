"""Celery tasks for document preview generation."""
import asyncio
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.models import Document
from app.services.async_storage_factory import AsyncStorageServiceFactory
from app.services.document_preview_service import DocumentPreviewService
from app.core.config import settings

from worker_app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_async_database_url():
    """Convert postgresql:// to postgresql+asyncpg://"""
    url = settings.SQLALCHEMY_DATABASE_URI
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _create_task_session_factory():
    """Create a fresh async engine and session factory for task execution.

    This avoids event loop conflicts when running in Celery workers.
    """
    engine = create_async_engine(
        _get_async_database_url(),
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    ), engine


async def _generate_document_preview(
    document_id: str,
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    start_time = datetime.now(timezone.utc)
    temp_dir: Optional[Path] = None

    # Create fresh engine/session for this task to avoid event loop conflicts
    TaskSessionLocal, task_engine = _create_task_session_factory()

    try:
        async with TaskSessionLocal() as db:
            stmt = select(Document).filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
            result = await db.execute(stmt)
            doc = result.scalar_one_or_none()

            if not doc:
                return {"success": False, "error": f"Document {document_id} not found"}

            async with httpx.AsyncClient(timeout=60.0) as http_client:
                preview_service = DocumentPreviewService(
                    tenant_id=str(tenant_id),
                    user_id=str(user_id),
                    http_client=http_client,
                )

                try:
                    if not force_regenerate:
                        existing_preview = await preview_service.get_preview_info(str(document_id))
                        if existing_preview and existing_preview.get("pdf_available"):
                            logger.info("Preview already exists for document %s", document_id)
                            return {
                                "success": True,
                                "document_id": document_id,
                                "preview_exists": True,
                                "preview_info": existing_preview,
                            }

                    storage_service = await AsyncStorageServiceFactory.create_storage_service(
                        str(tenant_id),
                        str(user_id),
                        db,
                    )

                    source_path = doc.file_path or f"{tenant_id}/{document_id}/{doc.filename}"
                    file_data = await storage_service.download_file(source_path)
                    if not file_data:
                        return {"success": False, "error": "Could not download original file"}

                    temp_dir = Path(tempfile.mkdtemp(prefix=f"preview_{document_id}_"))
                    temp_filename = doc.filename or f"{document_id}.bin"
                    temp_path = temp_dir / temp_filename
                    temp_path.write_bytes(file_data)

                    preview_result = await preview_service.generate_preview(
                        document_id=str(document_id),
                        file_path=str(temp_path),
                        filename=temp_filename,
                        force_regenerate=force_regenerate,
                    )

                    if preview_result:
                        doc.document_metadata = doc.document_metadata or {}
                        preview_metadata = dict(preview_result)
                        preview_metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
                        preview_metadata["processing_time"] = (
                            datetime.now(timezone.utc) - start_time
                        ).total_seconds()
                        doc.document_metadata["preview"] = preview_metadata
                        await db.commit()

                        return {
                            "success": True,
                            "document_id": document_id,
                            "preview_type": preview_type,
                            "preview": preview_metadata,
                        }

                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "Preview generation failed",
                    }

                except Exception as exc:
                    logger.exception("Preview generation failed for %s: %s", document_id, exc)
                    return {"success": False, "document_id": document_id, "error": str(exc)}
                finally:
                    if temp_dir and temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    try:
                        await preview_service.cleanup()
                    except Exception as cleanup_exc:
                        logger.warning("Preview service cleanup failed: %s", cleanup_exc)
    finally:
        # Dispose of the engine to clean up connections
        await task_engine.dispose()


def _run_async(coro):
    return asyncio.run(coro)


@celery_app.task(name="preview.generate_document_preview")
def generate_document_preview_task(
    document_id: str,
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    return _run_async(
        _generate_document_preview(document_id, tenant_id, user_id, preview_type, force_regenerate)
    )


async def _generate_preview_batch(
    document_ids: List[str],
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",
    batch_size: int = 5,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for i in range(0, len(document_ids), batch_size):
        batch = document_ids[i : i + batch_size]
        tasks = [
            _generate_document_preview(doc_id, tenant_id, user_id, preview_type)
            for doc_id in batch
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for doc_id, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                results.append({"document_id": doc_id, "success": False, "error": str(result)})
            else:
                results.append(result)
        if i + batch_size < len(document_ids):
            await asyncio.sleep(2)

    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    return {"total": len(document_ids), "successful": successful, "failed": failed, "results": results}


@celery_app.task(name="preview.generate_preview_batch")
def generate_preview_batch_task(
    document_ids: List[str],
    tenant_id: str,
    user_id: str,
    preview_type: str = "all",
    batch_size: int = 5,
) -> Dict[str, Any]:
    return _run_async(
        _generate_preview_batch(document_ids, tenant_id, user_id, preview_type, batch_size)
    )


async def _auto_generate_missing_previews() -> Dict[str, Any]:
    # Create fresh engine/session for this task to avoid event loop conflicts
    TaskSessionLocal, task_engine = _create_task_session_factory()

    try:
        async with TaskSessionLocal() as db:
            stmt = (
                select(Document)
                .filter(
                    Document.file_type.notin_(["pdf"]),
                    Document.document_metadata["preview"].is_(None),
                )
                .limit(100)
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()
            if not documents:
                logger.info("No documents need preview generation")
                return {"success": True, "message": "No documents need preview generation"}

            tenant_docs: Dict[str, List[str]] = {}
            for doc in documents:
                tenant_id = str(doc.tenant_id)
                tenant_docs.setdefault(tenant_id, []).append(str(doc.id))

            total_queued = 0
            for tenant_id, doc_ids in tenant_docs.items():
                generate_preview_batch_task.delay(doc_ids, tenant_id, "system", "all", 5)
                total_queued += len(doc_ids)

            logger.info("Queued %s documents for preview generation", total_queued)
            return {
                "success": True,
                "tenants_processed": len(tenant_docs),
                "documents_queued": total_queued,
            }
    finally:
        await task_engine.dispose()


@celery_app.task(name="preview.auto_generate_missing_previews")
def auto_generate_missing_previews_task() -> Dict[str, Any]:
    return _run_async(_auto_generate_missing_previews())


async def _cleanup_old_previews() -> Dict[str, Any]:
    logger.info("Preview cleanup task placeholder")
    return {"success": True, "message": "Cleanup complete"}


@celery_app.task(name="preview.cleanup_old_previews")
def cleanup_old_previews_task() -> Dict[str, Any]:
    return _run_async(_cleanup_old_previews())
