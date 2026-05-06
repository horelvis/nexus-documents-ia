"""
Analysis Queue API Endpoints

REST API for document analysis queue operations.
Allows queuing documents for background analysis, checking status,
retrieving results, and listing historical analyses.
"""

from typing import List, Optional
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from app.api.async_dependencies import (
    get_current_user_async,
    get_async_db
)
from app.core.auth.base import UserProfile
from app.db.models import Document as DBDocument, IndexedDocument, DocumentAnalysis
from app.schemas.analysis import (
    AnalysisStatus, AnalysisType,
    AnalysisQueueRequest, AnalysisBatchRequest,
    AnalysisJobCreate, AnalysisJobProgress, AnalysisJobResult, AnalysisJobListItem,
    AnalysisQueueStats, AnalysisQueueResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


# =====================================
# Queue Operations
# =====================================

@router.post("", response_model=AnalysisJobCreate)
async def queue_analysis(
    request: AnalysisQueueRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Queue a document for analysis.

    Creates a new analysis job in pending state.
    The analysis will be processed asynchronously.
    """
    # Look up document (all authenticated users can see all documents)
    doc_result = await db.execute(
        select(DBDocument).where(DBDocument.id == request.document_id)
    )
    document = doc_result.scalar_one_or_none()

    # If not found, try IndexedDocument table (connector documents)
    if not document:
        indexed_result = await db.execute(
            select(IndexedDocument).where(IndexedDocument.id == request.document_id)
        )
        indexed_doc = indexed_result.scalar_one_or_none()
        if indexed_doc:
            document = indexed_doc  # Use IndexedDocument

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"Document {request.document_id} not found in either table"
        )

    # Check if there's already a pending/processing analysis for this document
    existing_result = await db.execute(
        select(DocumentAnalysis).where(
            and_(
                DocumentAnalysis.document_id == request.document_id,
                DocumentAnalysis.status.in_(["pending", "processing"])
            )
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Return the existing job instead of creating a new one
        return AnalysisJobCreate(
            id=existing.id,
            document_id=existing.document_id,
            status=AnalysisStatus(existing.status),
            created_at=existing.created_at
        )

    # Create new analysis job
    analysis = DocumentAnalysis(
        document_id=request.document_id,
        created_by=UUID(current_user.sub),
        analysis_type=request.analysis_type.value,
        status="pending",
        progress=0
    )

    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    logger.info(f"Analysis job {analysis.id} queued for document {request.document_id}")

    # TODO: Trigger Celery task for background processing
    # from app.tasks.analysis_tasks import process_analysis
    # process_analysis.delay(str(analysis.id))

    return AnalysisJobCreate(
        id=analysis.id,
        document_id=analysis.document_id,
        status=AnalysisStatus(analysis.status),
        created_at=analysis.created_at
    )


@router.post("/batch", response_model=List[AnalysisJobCreate])
async def queue_batch_analysis(
    request: AnalysisBatchRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Queue multiple documents for analysis.

    Creates analysis jobs for each document in the batch.
    Returns list of created jobs (skips documents that already have pending analyses).
    """
    # Look up all documents (all authenticated users can see all documents)
    docs_result = await db.execute(
        select(DBDocument).where(DBDocument.id.in_(request.document_ids))
    )
    documents = docs_result.scalars().all()
    found_ids = {doc.id for doc in documents}

    # Check which documents already have pending/processing analyses
    existing_result = await db.execute(
        select(DocumentAnalysis.document_id).where(
            and_(
                DocumentAnalysis.document_id.in_(request.document_ids),
                DocumentAnalysis.status.in_(["pending", "processing"])
            )
        )
    )
    existing_ids = {row[0] for row in existing_result.fetchall()}

    created_jobs = []
    for doc_id in request.document_ids:
        if doc_id not in found_ids:
            logger.warning(f"Document {doc_id} not found, skipping")
            continue

        if doc_id in existing_ids:
            logger.info(f"Document {doc_id} already has pending analysis, skipping")
            continue

        analysis = DocumentAnalysis(
            document_id=doc_id,
            created_by=UUID(current_user.sub),
            analysis_type=request.analysis_type.value,
            status="pending",
            progress=0
        )
        db.add(analysis)
        created_jobs.append(analysis)

    if created_jobs:
        await db.commit()
        for job in created_jobs:
            await db.refresh(job)

    logger.info(f"Batch queued {len(created_jobs)} analysis jobs")

    return [
        AnalysisJobCreate(
            id=job.id,
            document_id=job.document_id,
            status=AnalysisStatus(job.status),
            created_at=job.created_at
        )
        for job in created_jobs
    ]


# =====================================
# Job Status & Results
# =====================================

@router.get("/{job_id}", response_model=AnalysisJobProgress)
async def get_analysis_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Get the current status and progress of an analysis job.
    """
    result = await db.execute(
        select(DocumentAnalysis).where(DocumentAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis job {job_id} not found"
        )

    return AnalysisJobProgress(
        id=analysis.id,
        document_id=analysis.document_id,
        status=AnalysisStatus(analysis.status),
        progress=analysis.progress,
        analysis_type=analysis.analysis_type,
        current_step=analysis.current_step,
        plan_title=analysis.plan_title,
        total_steps=analysis.total_steps or 0,
        steps_completed=analysis.steps_completed or 0,
        detected_document_type=analysis.detected_document_type,
        detected_document_type_display=analysis.detected_document_type_display,
        detection_confidence=analysis.detection_confidence,
        started_at=analysis.started_at,
        error_message=analysis.error_message
    )


@router.get("/{job_id}/result", response_model=AnalysisJobResult)
async def get_analysis_result(
    job_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Get the complete result of a completed analysis job.

    Returns full analysis including summary, risks, recommendations,
    annotations, and annotated PDF URL.
    """
    result = await db.execute(
        select(DocumentAnalysis).where(DocumentAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis job {job_id} not found"
        )

    if analysis.status not in ["completed", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Analysis is still in progress (status: {analysis.status})"
        )

    return AnalysisJobResult(
        id=analysis.id,
        document_id=analysis.document_id,
        status=AnalysisStatus(analysis.status),
        progress=analysis.progress,
        analysis_type=analysis.analysis_type,
        current_step=analysis.current_step,
        plan_title=analysis.plan_title,
        total_steps=analysis.total_steps or 0,
        steps_completed=analysis.steps_completed or 0,
        detected_document_type=analysis.detected_document_type,
        detected_document_type_display=analysis.detected_document_type_display,
        detection_confidence=analysis.detection_confidence,
        started_at=analysis.started_at,
        error_message=analysis.error_message,
        summary=analysis.summary,
        risks=analysis.risks or [],
        recommendations=analysis.recommendations or [],
        findings=analysis.findings or [],
        annotations=analysis.annotations or [],
        annotated_pdf_url=analysis.annotated_pdf_url,
        confidence_score=analysis.confidence_score,
        execution_time_ms=analysis.execution_time_ms,
        completed_at=analysis.completed_at,
        created_at=analysis.created_at
    )


@router.delete("/{job_id}")
async def cancel_analysis(
    job_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Cancel a pending or processing analysis job.

    Only pending or processing jobs can be cancelled.
    Completed or failed jobs cannot be cancelled.
    """
    result = await db.execute(
        select(DocumentAnalysis).where(DocumentAnalysis.id == job_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis job {job_id} not found"
        )

    if analysis.status not in ["pending", "processing"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel analysis in status: {analysis.status}"
        )

    # Mark as failed with cancellation message
    analysis.status = "failed"
    analysis.error_message = "Cancelled by user"
    await db.commit()

    logger.info(f"Analysis job {job_id} cancelled by user {current_user.sub}")

    return {"message": "Analysis cancelled", "job_id": str(job_id)}


# =====================================
# Queue Listing
# =====================================

@router.get("", response_model=AnalysisQueueResponse)
async def list_analyses(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    status: Optional[AnalysisStatus] = Query(None),
    document_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List analysis jobs.

    Supports filtering by status and document.
    Returns paginated results with queue statistics.
    """
    # Build query
    query = select(DocumentAnalysis)

    if status:
        query = query.where(DocumentAnalysis.status == status.value)

    if document_id:
        query = query.where(DocumentAnalysis.document_id == document_id)

    # Count total
    count_query = select(func.count(DocumentAnalysis.id))
    if status:
        count_query = count_query.where(DocumentAnalysis.status == status.value)
    if document_id:
        count_query = count_query.where(DocumentAnalysis.document_id == document_id)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get paginated results
    query = query.order_by(desc(DocumentAnalysis.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    analyses = result.scalars().all()

    # Get document filenames for display
    doc_ids = [a.document_id for a in analyses]
    if doc_ids:
        docs_result = await db.execute(
            select(DBDocument.id, DBDocument.filename).where(
                DBDocument.id.in_(doc_ids)
            )
        )
        doc_names = {row[0]: row[1] for row in docs_result.fetchall()}
    else:
        doc_names = {}

    # Calculate stats
    stats_query = select(
        DocumentAnalysis.status,
        func.count(DocumentAnalysis.id)
    ).group_by(DocumentAnalysis.status)

    stats_result = await db.execute(stats_query)
    status_counts = {row[0]: row[1] for row in stats_result.fetchall()}

    # Calculate average execution time for completed analyses
    avg_time_query = select(
        func.avg(DocumentAnalysis.execution_time_ms)
    ).where(
        and_(
            DocumentAnalysis.status == "completed",
            DocumentAnalysis.execution_time_ms.isnot(None)
        )
    )
    avg_time_result = await db.execute(avg_time_query)
    avg_time = avg_time_result.scalar()

    stats = AnalysisQueueStats(
        pending_count=status_counts.get("pending", 0),
        processing_count=status_counts.get("processing", 0),
        completed_count=status_counts.get("completed", 0),
        failed_count=status_counts.get("failed", 0),
        total_count=sum(status_counts.values()),
        avg_execution_time_ms=avg_time
    )

    jobs = [
        AnalysisJobListItem(
            id=a.id,
            document_id=a.document_id,
            document_filename=doc_names.get(a.document_id),
            status=AnalysisStatus(a.status),
            progress=a.progress,
            analysis_type=a.analysis_type,
            current_step=a.current_step,
            started_at=a.started_at,
            completed_at=a.completed_at,
            created_at=a.created_at,
            error_message=a.error_message
        )
        for a in analyses
    ]

    return AnalysisQueueResponse(
        jobs=jobs,
        stats=stats,
        total=total,
        page=page,
        page_size=page_size
    )


# =====================================
# Document History
# =====================================

@router.get("/document/{document_id}/history", response_model=List[AnalysisJobListItem])
async def get_document_analysis_history(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Get analysis history for a specific document.

    Returns the most recent analyses for the document.
    """
    doc_result = await db.execute(
        select(DBDocument).where(DBDocument.id == document_id)
    )
    document = doc_result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found"
        )

    result = await db.execute(
        select(DocumentAnalysis)
        .where(DocumentAnalysis.document_id == document_id)
        .order_by(desc(DocumentAnalysis.created_at)).limit(limit)
    )
    analyses = result.scalars().all()

    return [
        AnalysisJobListItem(
            id=a.id,
            document_id=a.document_id,
            document_filename=document.filename,
            status=AnalysisStatus(a.status),
            progress=a.progress,
            analysis_type=a.analysis_type,
            current_step=a.current_step,
            started_at=a.started_at,
            completed_at=a.completed_at,
            created_at=a.created_at,
            error_message=a.error_message
        )
        for a in analyses
    ]
