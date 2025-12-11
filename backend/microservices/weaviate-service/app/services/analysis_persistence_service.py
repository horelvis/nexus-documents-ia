"""
Analysis Persistence Service

Persists document analysis results to the main PostgreSQL database.
Also handles uploading annotated PDFs to GCS via the storage service.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
import asyncpg
import httpx
import base64

from app.core.config import settings

logger = logging.getLogger(__name__)


class AnalysisPersistenceService:
    """
    Service for persisting analysis results to the DocumentAnalysis table.

    This runs in the weaviate-service microservice and connects directly
    to the shared PostgreSQL database to update analysis job status and results.
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._db_url = self._get_db_url()

    def _get_db_url(self) -> str:
        """Convert SQLAlchemy URL to asyncpg format."""
        db_url = settings.database_url
        if "postgresql+asyncpg://" in db_url:
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        return db_url

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._db_url,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
        return self._pool

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # =========================================================================
    # Job State Management
    # =========================================================================

    async def create_job(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        analysis_type: str = "legal"
    ) -> Optional[str]:
        """
        Create a new analysis job in pending state.

        Returns the job ID if created, or existing job ID if one already exists.
        """
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                # Check for existing pending/processing job
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM document_analyses
                    WHERE document_id = $1 AND status IN ('pending', 'processing')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    UUID(document_id)
                )

                if existing:
                    logger.info(f"Existing job found for document {document_id}: {existing['id']}")
                    return str(existing['id'])

                # Create new job
                import uuid
                job_id = uuid.uuid4()

                await conn.execute(
                    """
                    INSERT INTO document_analyses (
                        id, document_id, tenant_id, created_by,
                        status, progress, analysis_type, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
                    """,
                    job_id,
                    UUID(document_id),
                    UUID(tenant_id),
                    UUID(user_id) if user_id else None,
                    'pending',
                    0,
                    analysis_type,
                    datetime.now(timezone.utc)
                )

                logger.info(f"Created analysis job {job_id} for document {document_id}")
                return str(job_id)

        except Exception as e:
            logger.error(f"Failed to create analysis job: {e}")
            return None

    async def mark_started(self, job_id: str) -> bool:
        """Mark job as started (processing)."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE document_analyses
                    SET status = 'processing',
                        started_at = $2,
                        updated_at = $2
                    WHERE id = $1
                    """,
                    UUID(job_id),
                    datetime.now(timezone.utc)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to mark job started: {e}")
            return False

    async def update_progress(
        self,
        job_id: str,
        progress: int,
        current_step: Optional[str] = None,
        plan_title: Optional[str] = None,
        total_steps: Optional[int] = None,
        steps_completed: Optional[int] = None
    ) -> bool:
        """Update job progress during execution."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                # Build dynamic update
                fields = ["progress = $2", "updated_at = $3"]
                values = [UUID(job_id), progress, datetime.now(timezone.utc)]
                param_idx = 4

                if current_step is not None:
                    fields.append(f"current_step = ${param_idx}")
                    values.append(current_step)
                    param_idx += 1

                if plan_title is not None:
                    fields.append(f"plan_title = ${param_idx}")
                    values.append(plan_title)
                    param_idx += 1

                if total_steps is not None:
                    fields.append(f"total_steps = ${param_idx}")
                    values.append(total_steps)
                    param_idx += 1

                if steps_completed is not None:
                    fields.append(f"steps_completed = ${param_idx}")
                    values.append(steps_completed)
                    param_idx += 1

                query = f"UPDATE document_analyses SET {', '.join(fields)} WHERE id = $1"
                await conn.execute(query, *values)

            return True
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
            return False

    async def update_detection(
        self,
        job_id: str,
        document_type: str,
        document_type_display: str,
        confidence: float
    ) -> bool:
        """Update document type detection results."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE document_analyses
                    SET detected_document_type = $2,
                        detected_document_type_display = $3,
                        detection_confidence = $4,
                        updated_at = $5
                    WHERE id = $1
                    """,
                    UUID(job_id),
                    document_type,
                    document_type_display,
                    confidence,
                    datetime.now(timezone.utc)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update detection: {e}")
            return False

    async def mark_completed(
        self,
        job_id: str,
        summary: str,
        risks: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        annotations: List[Dict[str, Any]],
        confidence_score: float,
        execution_time_ms: int,
        annotated_pdf_path: Optional[str] = None,
        annotated_pdf_url: Optional[str] = None,
        execution_log: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Mark job as completed with full results."""
        try:
            import json
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                now = datetime.now(timezone.utc)
                await conn.execute(
                    """
                    UPDATE document_analyses
                    SET status = 'completed',
                        progress = 100,
                        completed_at = $2,
                        summary = $3,
                        risks = $4,
                        recommendations = $5,
                        findings = $6,
                        annotations = $7,
                        confidence_score = $8,
                        execution_time_ms = $9,
                        annotated_pdf_path = $10,
                        annotated_pdf_url = $11,
                        execution_log = $12,
                        updated_at = $2
                    WHERE id = $1
                    """,
                    UUID(job_id),
                    now,
                    summary,
                    json.dumps(risks),
                    json.dumps(recommendations),
                    json.dumps(findings),
                    json.dumps(annotations),
                    confidence_score,
                    execution_time_ms,
                    annotated_pdf_path,
                    annotated_pdf_url,
                    json.dumps(execution_log or [])
                )

            logger.info(
                f"Job {job_id} completed: {len(risks)} risks, "
                f"{len(recommendations)} recommendations, {execution_time_ms}ms"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to mark job completed: {e}")
            return False

    async def mark_failed(self, job_id: str, error_message: str) -> bool:
        """Mark job as failed with error message."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE document_analyses
                    SET status = 'failed',
                        error_message = $2,
                        completed_at = $3,
                        updated_at = $3
                    WHERE id = $1
                    """,
                    UUID(job_id),
                    error_message,
                    datetime.now(timezone.utc)
                )

            logger.warning(f"Job {job_id} failed: {error_message}")
            return True

        except Exception as e:
            logger.error(f"Failed to mark job failed: {e}")
            return False

    async def get_analysis(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analysis results by job ID.

        Returns the full analysis data including summary, risks, recommendations,
        findings, annotations, etc.
        """
        try:
            import json
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id, document_id, tenant_id, created_by,
                        status, progress, current_step, error_message,
                        analysis_type, detected_document_type, detected_document_type_display,
                        detection_confidence, plan_id, plan_title, total_steps, steps_completed,
                        summary, risks, recommendations, findings, annotations,
                        execution_log, annotated_pdf_path, annotated_pdf_url,
                        confidence_score, execution_time_ms,
                        started_at, completed_at, created_at, updated_at
                    FROM document_analyses
                    WHERE id = $1
                    """,
                    UUID(job_id)
                )

                if not row:
                    logger.warning(f"Analysis job {job_id} not found")
                    return None

                # Convert row to dict with proper JSON parsing
                result = {
                    "id": str(row['id']),
                    "document_id": str(row['document_id']),
                    "tenant_id": str(row['tenant_id']),
                    "created_by": str(row['created_by']) if row['created_by'] else None,
                    "status": row['status'],
                    "progress": row['progress'],
                    "current_step": row['current_step'],
                    "error_message": row['error_message'],
                    "analysis_type": row['analysis_type'],
                    "detected_document_type": row['detected_document_type'],
                    "detected_document_type_display": row['detected_document_type_display'],
                    "detection_confidence": row['detection_confidence'],
                    "plan_id": row['plan_id'],
                    "plan_title": row['plan_title'],
                    "total_steps": row['total_steps'],
                    "steps_completed": row['steps_completed'],
                    "summary": row['summary'],
                    "risks": json.loads(row['risks']) if row['risks'] else [],
                    "recommendations": json.loads(row['recommendations']) if row['recommendations'] else [],
                    "findings": json.loads(row['findings']) if row['findings'] else [],
                    "annotations": json.loads(row['annotations']) if row['annotations'] else [],
                    "execution_log": json.loads(row['execution_log']) if row['execution_log'] else [],
                    "annotated_pdf_path": row['annotated_pdf_path'],
                    "annotated_pdf_url": row['annotated_pdf_url'],
                    "confidence_score": row['confidence_score'],
                    "execution_time_ms": row['execution_time_ms'],
                    "started_at": row['started_at'].isoformat() if row['started_at'] else None,
                    "completed_at": row['completed_at'].isoformat() if row['completed_at'] else None,
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None,
                }

                logger.info(f"Retrieved analysis job {job_id}: status={result['status']}")
                return result

        except Exception as e:
            logger.error(f"Failed to get analysis: {e}")
            return None

    # =========================================================================
    # PDF Upload to GCS
    # =========================================================================

    async def upload_annotated_pdf(
        self,
        job_id: str,
        document_id: str,
        tenant_id: str,
        pdf_bytes: bytes
    ) -> Optional[str]:
        """
        Upload annotated PDF to GCS via storage service.

        Returns the GCS path if successful.
        """
        try:
            # Construct filename
            filename = f"analysis_{job_id}_annotated.pdf"

            # Get user_id from original document
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT created_by FROM documents WHERE id = $1",
                    UUID(document_id)
                )
                user_id = str(row['created_by']) if row else 'system'

            # Upload via storage service
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Use the upload endpoint
                response = await client.post(
                    f"{settings.storage_service_url}/api/v1/storage/upload-bytes",
                    headers={
                        "X-API-Key": settings.MICROSERVICES_API_KEY,
                        "X-Tenant-ID": tenant_id,
                        "X-User-ID": user_id,
                    },
                    json={
                        "filename": filename,
                        "content_type": "application/pdf",
                        "content_base64": base64.b64encode(pdf_bytes).decode('utf-8'),
                        "subfolder": "analysis"
                    }
                )

                if response.status_code == 200:
                    result = response.json()
                    gcs_path = result.get("path") or f"analysis/{filename}"
                    logger.info(f"Uploaded annotated PDF to GCS: {gcs_path}")
                    return gcs_path
                else:
                    logger.warning(
                        f"Failed to upload annotated PDF: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error uploading annotated PDF: {e}")
            return None


# Singleton instance
_persistence_service: Optional[AnalysisPersistenceService] = None


def get_persistence_service() -> AnalysisPersistenceService:
    """Get or create the persistence service singleton."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = AnalysisPersistenceService()
    return _persistence_service
