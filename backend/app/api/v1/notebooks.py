"""
NexusLM Notebook API Endpoints

API endpoints for the NexusLM feature - an on-premise NotebookLM alternative
using Qwen3-4B-Thinking for LLM and VibeVoice for TTS.

Features:
- Notebook CRUD operations
- Source management (add/remove documents)
- Q&A chat with RAG pipeline
- Podcast audio generation
"""

import logging
import math
import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks, Header
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import (
    User, Document, IndexedDocument,
    Notebook, NotebookSource, NotebookAudio, NotebookChat, NotebookPresentation
)
from app.schemas.notebook import (
    NotebookCreate, NotebookUpdate, NotebookResponse, NotebookListResponse,
    NotebookDetailResponse, NotebookStatsResponse,
    NotebookSourceAdd, NotebookSourceResponse,
    AudioGenerateRequest, NotebookAudioResponse, AudioStatusResponse, AudioStatus,
    PresentationGenerateRequest, NotebookPresentationResponse, PresentationStatusResponse, PresentationStatus,
    NotebookChatCreate, NotebookChatResponse, NotebookChatMessage, ChatCompletionResponse,
    ChatMessage, Citation
)
from app.schemas.general import SuccessResponse

logger = logging.getLogger(__name__)

# Configuration
PODCAST_SERVICE_URL = os.getenv("PODCAST_SERVICE_URL", "http://podcast-service:8000")
PRESENTATION_SERVICE_URL = os.getenv("PRESENTATION_SERVICE_URL", "http://presentation-service:8000")
WEAVIATE_SERVICE_URL = os.getenv("WEAVIATE_SERVICE_URL", "http://weaviate-service:8000")
MICROSERVICES_API_KEY = os.getenv("MICROSERVICES_API_KEY", "")
LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", "/app/storage")

router = APIRouter()


# =====================================
# INTERNAL SCHEMAS FOR MICROSERVICES
# =====================================

class AudioStatusUpdate(BaseModel):
    """Schema for internal audio status updates from podcast service."""
    status: str
    status_message: Optional[str] = None
    progress_percent: int = 0
    error_message: Optional[str] = None
    script: Optional[List[dict]] = None
    audio_url: Optional[str] = None
    duration_ms: Optional[int] = None
    file_size_bytes: Optional[int] = None
    transcript: Optional[List[dict]] = None


class PresentationStatusUpdate(BaseModel):
    """Schema for internal presentation status updates from presentation service."""
    status: str
    status_message: Optional[str] = None
    progress_percent: int = 0
    error_message: Optional[str] = None
    outline: Optional[List[dict]] = None
    pptx_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    slide_count: Optional[int] = None
    file_size_bytes: Optional[int] = None


# =====================================
# HELPER FUNCTIONS
# =====================================

def _presentation_to_response(presentation: NotebookPresentation) -> NotebookPresentationResponse:
    """Convert NotebookPresentation model to response schema.

    This helper avoids lazy-loading issues with async SQLAlchemy sessions
    by accessing attributes through __dict__ to prevent triggering lazy loads.
    """
    # Access through __dict__ to avoid lazy loading
    d = presentation.__dict__

    return NotebookPresentationResponse(
        id=d.get("id"),
        notebook_id=d.get("notebook_id"),
        config=d.get("config") or {},
        status=d.get("status"),
        status_message=d.get("status_message"),
        progress_percent=d.get("progress_percent") or 0,
        outline=d.get("outline"),
        pptx_url=d.get("pptx_url"),
        thumbnail_url=d.get("thumbnail_url"),
        slide_count=d.get("slide_count"),
        file_size_bytes=d.get("file_size_bytes"),
        error_message=d.get("error_message"),
        generation_started_at=d.get("generation_started_at"),
        generation_completed_at=d.get("generation_completed_at"),
        created_at=d.get("created_at"),
        updated_at=d.get("updated_at"),
    )


async def verify_microservice_api_key(
    x_api_key: str = Header(..., alias="X-API-Key")
) -> bool:
    """Verify the microservice API key for internal endpoints."""
    if not MICROSERVICES_API_KEY:
        logger.warning("MICROSERVICES_API_KEY not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal authentication not configured"
        )
    if x_api_key != MICROSERVICES_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return True


async def get_source_content_from_weaviate(
    tenant_id: str,
    document_id: str,
) -> Optional[dict]:
    """
    Get the full content of a document from Weaviate.

    Calls the weaviate-service endpoint to retrieve all chunks and concatenate them.

    Args:
        tenant_id: Tenant identifier
        document_id: Document ID (indexed_document_id or document_id)

    Returns:
        Dict with title, content, word_count or None if not found
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{WEAVIATE_SERVICE_URL}/weaviate/documents/{tenant_id}/{document_id}/content",
                headers={"X-API-Key": MICROSERVICES_API_KEY},
            )

            if response.status_code == 404:
                logger.warning(f"Document {document_id} not found in Weaviate")
                return None

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"Weaviate service error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Failed to get document content: {e}")
        return None


async def trigger_podcast_generation(
    audio_id: UUID,
    notebook_id: UUID,
    tenant_id: UUID,
    sources: List[dict],
    config: dict,
):
    """Trigger podcast generation in the podcast service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PODCAST_SERVICE_URL}/api/v1/podcast/generate",
                json={
                    "audio_id": str(audio_id),
                    "notebook_id": str(notebook_id),
                    "tenant_id": str(tenant_id),
                    "sources": sources,
                    "config": config,
                },
                headers={"X-API-Key": MICROSERVICES_API_KEY},
            )
            response.raise_for_status()
            logger.info(f"Podcast generation triggered for audio {audio_id}")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Podcast service returned error: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to trigger podcast generation: {e}")
        return False


async def trigger_presentation_generation(
    presentation_id: UUID,
    notebook_id: UUID,
    tenant_id: UUID,
    sources: List[dict],
    config: dict,
):
    """Trigger presentation generation in the presentation service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PRESENTATION_SERVICE_URL}/api/v1/presentation/generate",
                json={
                    "presentation_id": str(presentation_id),
                    "notebook_id": str(notebook_id),
                    "tenant_id": str(tenant_id),
                    "sources": sources,
                    "config": config,
                },
                headers={"X-API-Key": MICROSERVICES_API_KEY},
            )
            response.raise_for_status()
            logger.info(f"Presentation generation triggered for presentation {presentation_id}")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(f"Presentation service returned error: {e.response.status_code} - {e.response.text}")
        return False
    except Exception as e:
        logger.error(f"Failed to trigger presentation generation: {e}")
        return False


# =====================================
# INTERNAL ENDPOINTS (Microservices)
# =====================================

@router.put("/internal/audio/{audio_id}/status", response_model=SuccessResponse, include_in_schema=False)
async def update_audio_status_internal(
    audio_id: UUID,
    update: AudioStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: bool = Depends(verify_microservice_api_key),
):
    """
    Internal endpoint for podcast service to update audio generation status.

    This endpoint is authenticated with MICROSERVICES_API_KEY and should only
    be called by the podcast-service microservice.
    """
    # Get audio record
    audio_query = select(NotebookAudio).where(NotebookAudio.id == audio_id)
    audio_result = await db.execute(audio_query)
    audio = audio_result.scalar_one_or_none()

    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found"
        )

    # Update fields
    audio.status = update.status
    audio.status_message = update.status_message
    audio.progress_percent = update.progress_percent

    if update.error_message:
        audio.error_message = update.error_message

    if update.script:
        audio.script = update.script

    if update.audio_url:
        audio.audio_url = update.audio_url

    if update.duration_ms:
        audio.duration_ms = update.duration_ms

    if update.file_size_bytes:
        audio.file_size_bytes = update.file_size_bytes

    if update.transcript:
        audio.transcript = update.transcript

    # Update timestamps based on status
    if update.status == "generating_script" and not audio.generation_started_at:
        audio.generation_started_at = datetime.now(timezone.utc)

    if update.status == "completed":
        audio.generation_completed_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(f"Audio {audio_id} status updated to {update.status}")

    return SuccessResponse(message="Status updated successfully")


@router.put("/internal/presentation/{presentation_id}/status", response_model=SuccessResponse, include_in_schema=False)
async def update_presentation_status_internal(
    presentation_id: UUID,
    update: PresentationStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    _: bool = Depends(verify_microservice_api_key),
):
    """
    Internal endpoint for presentation service to update presentation generation status.

    This endpoint is authenticated with MICROSERVICES_API_KEY and should only
    be called by the presentation-service microservice.
    """
    # Get presentation record
    presentation_query = select(NotebookPresentation).where(NotebookPresentation.id == presentation_id)
    presentation_result = await db.execute(presentation_query)
    presentation = presentation_result.scalar_one_or_none()

    if not presentation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found"
        )

    # Update fields
    presentation.status = update.status
    presentation.status_message = update.status_message
    presentation.progress_percent = update.progress_percent

    if update.error_message:
        presentation.error_message = update.error_message

    if update.outline:
        presentation.outline = update.outline

    if update.pptx_url:
        presentation.pptx_url = update.pptx_url

    if update.thumbnail_url:
        presentation.thumbnail_url = update.thumbnail_url

    if update.slide_count:
        presentation.slide_count = update.slide_count

    if update.file_size_bytes:
        presentation.file_size_bytes = update.file_size_bytes

    # Update timestamps based on status
    if update.status == "analyzing" and not presentation.generation_started_at:
        presentation.generation_started_at = datetime.now(timezone.utc)

    if update.status == "completed":
        presentation.generation_completed_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(f"Presentation {presentation_id} status updated to {update.status}")

    return SuccessResponse(message="Status updated successfully")


# =====================================
# NOTEBOOK CRUD ENDPOINTS
# =====================================

@router.post("", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    notebook_data: NotebookCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Create a new notebook.

    Creates an empty notebook that can have documents added as sources.
    """
    notebook = Notebook(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        title=notebook_data.title,
        description=notebook_data.description,
        emoji=notebook_data.emoji or "📓",
        settings=notebook_data.settings.model_dump() if notebook_data.settings else {},
    )

    db.add(notebook)
    await db.commit()
    await db.refresh(notebook)

    logger.info(f"Notebook created: {notebook.id} by user {current_user.id}")

    return NotebookResponse.model_validate(notebook)


@router.get("", response_model=NotebookListResponse)
async def list_notebooks(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    include_archived: bool = Query(False, description="Include archived notebooks"),
):
    """
    List user's notebooks with pagination.

    Returns notebooks sorted by last activity (most recent first).
    """
    # Base query - user's notebooks only
    query = select(Notebook).where(
        and_(
            Notebook.user_id == current_user.id,
            Notebook.tenant_id == current_user.tenant_id,
        )
    )

    # Filter archived
    if not include_archived:
        query = query.where(Notebook.is_archived == False)

    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                Notebook.title.ilike(search_term),
                Notebook.description.ilike(search_term),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Order and paginate
    query = query.order_by(Notebook.last_activity_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    notebooks = result.scalars().all()

    return NotebookListResponse(
        notebooks=[NotebookResponse.model_validate(n) for n in notebooks],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=math.ceil(total / per_page) if total > 0 else 1,
    )


@router.get("/stats", response_model=NotebookStatsResponse)
async def get_notebook_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get statistics for user's notebooks.

    Returns aggregated stats across all notebooks.
    """
    # Count notebooks
    notebooks_query = select(func.count()).select_from(Notebook).where(
        and_(
            Notebook.user_id == current_user.id,
            Notebook.is_archived == False,
        )
    )
    total_notebooks = (await db.execute(notebooks_query)).scalar() or 0

    # Sum sources and words
    stats_query = select(
        func.sum(Notebook.source_count).label("total_sources"),
        func.sum(Notebook.total_words).label("total_words"),
        func.sum(Notebook.audio_count).label("total_audios"),
        func.sum(Notebook.presentation_count).label("total_presentations"),
        func.sum(Notebook.chat_count).label("total_chats"),
    ).where(
        and_(
            Notebook.user_id == current_user.id,
            Notebook.is_archived == False,
        )
    )
    stats_result = await db.execute(stats_query)
    stats = stats_result.one()

    # Get recent activity
    recent_query = select(Notebook).where(
        and_(
            Notebook.user_id == current_user.id,
            Notebook.is_archived == False,
        )
    ).order_by(Notebook.last_activity_at.desc()).limit(5)
    recent_result = await db.execute(recent_query)
    recent_notebooks = recent_result.scalars().all()

    return NotebookStatsResponse(
        total_notebooks=total_notebooks,
        total_sources=stats.total_sources or 0,
        total_words=stats.total_words or 0,
        total_audios=stats.total_audios or 0,
        total_presentations=stats.total_presentations or 0,
        total_chats=stats.total_chats or 0,
        recent_activity=[NotebookResponse.model_validate(n) for n in recent_notebooks],
    )


@router.get("/{notebook_id}", response_model=NotebookDetailResponse)
async def get_notebook(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get notebook details with sources and recent activity.

    Returns full notebook data including all sources and recent audios/chats.
    """
    # Query notebook with relationships
    query = select(Notebook).options(
        selectinload(Notebook.sources),
        selectinload(Notebook.audios),
        selectinload(Notebook.presentations),
        selectinload(Notebook.chats),
    ).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )

    result = await db.execute(query)
    notebook = result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Build response with nested data
    response_data = NotebookResponse.model_validate(notebook).model_dump()
    response_data["sources"] = [
        NotebookSourceResponse.model_validate(s) for s in notebook.sources
    ]
    response_data["recent_audios"] = [
        NotebookAudioResponse.model_validate(a)
        for a in sorted(notebook.audios, key=lambda x: x.created_at, reverse=True)[:5]
    ]
    response_data["recent_presentations"] = [
        _presentation_to_response(p)
        for p in sorted(notebook.presentations, key=lambda x: x.created_at, reverse=True)[:5]
    ]
    response_data["recent_chats"] = [
        NotebookChatResponse.model_validate(c)
        for c in sorted(notebook.chats, key=lambda x: x.last_message_at, reverse=True)[:5]
    ]

    return NotebookDetailResponse(**response_data)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: UUID,
    update_data: NotebookUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Update notebook properties.

    Allows updating title, description, emoji, settings, and archive status.
    """
    query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    notebook = result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    if "settings" in update_dict and update_dict["settings"]:
        update_dict["settings"] = update_dict["settings"].model_dump()

    for field, value in update_dict.items():
        setattr(notebook, field, value)

    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(notebook)

    logger.info(f"Notebook updated: {notebook_id}")

    return NotebookResponse.model_validate(notebook)


@router.delete("/{notebook_id}", response_model=SuccessResponse)
async def delete_notebook(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Delete a notebook and all its contents.

    Permanently deletes the notebook, all sources, audios, and chats.
    """
    query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    notebook = result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    await db.delete(notebook)
    await db.commit()

    logger.info(f"Notebook deleted: {notebook_id}")

    return SuccessResponse(message="Notebook deleted successfully")


# =====================================
# SOURCE MANAGEMENT ENDPOINTS
# =====================================

@router.post("/{notebook_id}/sources", response_model=NotebookSourceResponse, status_code=status.HTTP_201_CREATED)
async def add_source(
    notebook_id: UUID,
    source_data: NotebookSourceAdd,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Add a document as a source to the notebook.

    The document will be processed asynchronously to extract key points and summary.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get document info
    title = ""
    source_type = ""
    word_count = 0

    if source_data.document_id:
        doc_query = select(Document).where(
            and_(
                Document.id == source_data.document_id,
                Document.tenant_id == current_user.tenant_id,
            )
        )
        doc_result = await db.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )

        title = document.title
        source_type = document.file_type
        # Word count will be updated during processing

    elif source_data.indexed_document_id:
        idx_query = select(IndexedDocument).where(
            and_(
                IndexedDocument.id == source_data.indexed_document_id,
                IndexedDocument.tenant_id == current_user.tenant_id,
            )
        )
        idx_result = await db.execute(idx_query)
        indexed_doc = idx_result.scalar_one_or_none()

        if not indexed_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indexed document not found"
            )

        title = indexed_doc.title
        source_type = indexed_doc.file_extension or "unknown"

    # Check if source already exists
    existing_query = select(NotebookSource).where(
        and_(
            NotebookSource.notebook_id == notebook_id,
            or_(
                NotebookSource.document_id == source_data.document_id,
                NotebookSource.indexed_document_id == source_data.indexed_document_id,
            )
        )
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source already added to this notebook"
        )

    # Create source
    source = NotebookSource(
        notebook_id=notebook_id,
        document_id=source_data.document_id,
        indexed_document_id=source_data.indexed_document_id,
        title=title,
        source_type=source_type,
        word_count=word_count,
        is_processed=False,
    )

    db.add(source)

    # Update notebook stats
    notebook.source_count += 1
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(source)

    logger.info(f"Source added to notebook {notebook_id}: {source.id}")

    # Queue background processing for source analysis
    # TODO: Implement background task to analyze source with Qwen3-4B
    # background_tasks.add_task(process_notebook_source, source.id)

    return NotebookSourceResponse.model_validate(source)


@router.get("/{notebook_id}/sources", response_model=List[NotebookSourceResponse])
async def list_sources(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    List all sources in a notebook.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get sources
    sources_query = select(NotebookSource).where(
        NotebookSource.notebook_id == notebook_id
    ).order_by(NotebookSource.added_at.desc())

    sources_result = await db.execute(sources_query)
    sources = sources_result.scalars().all()

    return [NotebookSourceResponse.model_validate(s) for s in sources]


@router.delete("/{notebook_id}/sources/{source_id}", response_model=SuccessResponse)
async def remove_source(
    notebook_id: UUID,
    source_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Remove a source from the notebook.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get and delete source
    source_query = select(NotebookSource).where(
        and_(
            NotebookSource.id == source_id,
            NotebookSource.notebook_id == notebook_id,
        )
    )
    source_result = await db.execute(source_query)
    source = source_result.scalar_one_or_none()

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )

    # Update notebook stats
    notebook.source_count = max(0, notebook.source_count - 1)
    notebook.total_words = max(0, notebook.total_words - source.word_count)
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.delete(source)
    await db.commit()

    logger.info(f"Source removed from notebook {notebook_id}: {source_id}")

    return SuccessResponse(message="Source removed successfully")


# =====================================
# AUDIO GENERATION ENDPOINTS
# =====================================

@router.post("/{notebook_id}/audio", response_model=NotebookAudioResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_audio(
    notebook_id: UUID,
    request: AudioGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Start podcast audio generation for the notebook.

    Generates a two-host podcast discussing the notebook's sources.
    The generation happens asynchronously - poll the status endpoint for progress.
    """
    # Verify notebook ownership and get sources
    notebook_query = select(Notebook).options(
        selectinload(Notebook.sources)
    ).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if not notebook.sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notebook has no sources. Add at least one document before generating audio."
        )

    # Create audio record
    audio = NotebookAudio(
        notebook_id=notebook_id,
        config=request.config.model_dump(),
        status="pending",
        status_message="Fetching source content from Weaviate...",
        progress_percent=0,
    )

    db.add(audio)

    # Update notebook stats
    notebook.audio_count += 1
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(audio)

    logger.info(f"Audio generation queued for notebook {notebook_id}: {audio.id}")

    # Fetch content from Weaviate for each source
    sources_data = []
    tenant_id = str(current_user.tenant_id)

    for source in notebook.sources:
        # Determine which document ID to use
        doc_id = str(source.indexed_document_id) if source.indexed_document_id else (
            str(source.document_id) if source.document_id else None
        )

        if not doc_id:
            logger.warning(f"Source {source.id} has no document ID, skipping")
            continue

        # Fetch full content from Weaviate
        weaviate_content = await get_source_content_from_weaviate(tenant_id, doc_id)

        if weaviate_content:
            sources_data.append({
                "id": str(source.id),
                "title": weaviate_content.get("title") or source.title,
                "document_id": str(source.document_id) if source.document_id else None,
                "indexed_document_id": str(source.indexed_document_id) if source.indexed_document_id else None,
                "content": weaviate_content.get("content", ""),
                "word_count": weaviate_content.get("word_count", 0),
                "source_type": weaviate_content.get("source_type", source.source_type),
            })
            logger.info(f"Fetched content for source {source.id}: {weaviate_content.get('word_count', 0)} words")
        else:
            logger.warning(f"Could not fetch content for source {source.id} (doc_id: {doc_id})")

    if not sources_data:
        # Update status to failed if no content could be fetched
        audio.status = "failed"
        audio.error_message = "Could not fetch content from any source. Ensure documents are indexed in Weaviate."
        await db.commit()
        await db.refresh(audio)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not fetch content from any source. Ensure documents are indexed in Weaviate."
        )

    # Update audio status
    audio.status_message = f"Retrieved content from {len(sources_data)} source(s). Starting generation..."
    audio.progress_percent = 10
    await db.commit()

    # Trigger podcast generation in the podcast service
    success = await trigger_podcast_generation(
        audio_id=audio.id,
        notebook_id=notebook_id,
        tenant_id=current_user.tenant_id,
        sources=sources_data,
        config=request.config.model_dump(),
    )

    if not success:
        # Update status to failed if we couldn't reach the podcast service
        audio.status = "failed"
        audio.error_message = "Failed to connect to podcast generation service"
        await db.commit()

    # Refresh to get the latest state before returning
    await db.refresh(audio)

    return NotebookAudioResponse.model_validate(audio)


@router.get("/{notebook_id}/audio", response_model=List[NotebookAudioResponse])
async def list_audios(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    List all generated audios for a notebook.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get audios
    audios_query = select(NotebookAudio).where(
        NotebookAudio.notebook_id == notebook_id
    ).order_by(NotebookAudio.created_at.desc())

    audios_result = await db.execute(audios_query)
    audios = audios_result.scalars().all()

    return [NotebookAudioResponse.model_validate(a) for a in audios]


@router.get("/{notebook_id}/audio/{audio_id}", response_model=NotebookAudioResponse)
async def get_audio(
    notebook_id: UUID,
    audio_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get details of a specific audio generation.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get audio
    audio_query = select(NotebookAudio).where(
        and_(
            NotebookAudio.id == audio_id,
            NotebookAudio.notebook_id == notebook_id,
        )
    )
    audio_result = await db.execute(audio_query)
    audio = audio_result.scalar_one_or_none()

    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found"
        )

    return NotebookAudioResponse.model_validate(audio)


@router.get("/{notebook_id}/audio/{audio_id}/status", response_model=AudioStatusResponse)
async def get_audio_status(
    notebook_id: UUID,
    audio_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get the status of an audio generation.

    Use this for polling during generation.
    """
    # Simplified query - just get status fields
    audio_query = select(
        NotebookAudio.id,
        NotebookAudio.status,
        NotebookAudio.status_message,
        NotebookAudio.progress_percent,
        NotebookAudio.error_message,
    ).where(
        NotebookAudio.id == audio_id
    )
    audio_result = await db.execute(audio_query)
    audio = audio_result.one_or_none()

    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found"
        )

    return AudioStatusResponse(
        id=audio.id,
        status=AudioStatus(audio.status),
        status_message=audio.status_message,
        progress_percent=audio.progress_percent,
        error_message=audio.error_message,
    )


@router.delete("/{notebook_id}/audio/{audio_id}", response_model=SuccessResponse)
async def delete_audio(
    notebook_id: UUID,
    audio_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Delete a generated audio.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get and delete audio
    audio_query = select(NotebookAudio).where(
        and_(
            NotebookAudio.id == audio_id,
            NotebookAudio.notebook_id == notebook_id,
        )
    )
    audio_result = await db.execute(audio_query)
    audio = audio_result.scalar_one_or_none()

    if not audio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found"
        )

    # TODO: Delete audio file from GCS if exists

    # Update notebook stats
    notebook.audio_count = max(0, notebook.audio_count - 1)

    await db.delete(audio)
    await db.commit()

    logger.info(f"Audio deleted from notebook {notebook_id}: {audio_id}")

    return SuccessResponse(message="Audio deleted successfully")


# =====================================
# PRESENTATION GENERATION ENDPOINTS
# =====================================

@router.post("/{notebook_id}/presentations", response_model=NotebookPresentationResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_presentation(
    notebook_id: UUID,
    request: PresentationGenerateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Start PowerPoint presentation generation for the notebook.

    Generates a PPTX presentation summarizing the notebook's sources.
    The generation happens asynchronously - poll the status endpoint for progress.
    """
    # Verify notebook ownership and get sources
    notebook_query = select(Notebook).options(
        selectinload(Notebook.sources)
    ).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if not notebook.sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notebook has no sources. Add at least one document before generating a presentation."
        )

    # Create presentation record
    presentation = NotebookPresentation(
        notebook_id=notebook_id,
        config=request.config.model_dump(),
        status="pending",
        status_message="Fetching source content from Weaviate...",
        progress_percent=0,
    )

    db.add(presentation)

    # Update notebook stats
    notebook.presentation_count += 1
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(presentation)

    logger.info(f"Presentation generation queued for notebook {notebook_id}: {presentation.id}")

    # Fetch content from Weaviate for each source
    sources_data = []
    tenant_id = str(current_user.tenant_id)

    for source in notebook.sources:
        # Determine which document ID to use
        doc_id = str(source.indexed_document_id) if source.indexed_document_id else (
            str(source.document_id) if source.document_id else None
        )

        if not doc_id:
            logger.warning(f"Source {source.id} has no document ID, skipping")
            continue

        # Fetch full content from Weaviate
        weaviate_content = await get_source_content_from_weaviate(tenant_id, doc_id)

        if weaviate_content:
            sources_data.append({
                "id": str(source.id),
                "title": weaviate_content.get("title") or source.title,
                "document_id": str(source.document_id) if source.document_id else None,
                "indexed_document_id": str(source.indexed_document_id) if source.indexed_document_id else None,
                "content": weaviate_content.get("content", ""),
                "word_count": weaviate_content.get("word_count", 0),
                "source_type": weaviate_content.get("source_type", source.source_type),
            })
            logger.info(f"Fetched content for source {source.id}: {weaviate_content.get('word_count', 0)} words")
        else:
            logger.warning(f"Could not fetch content for source {source.id} (doc_id: {doc_id})")

    if not sources_data:
        # Update status to failed if no content could be fetched
        presentation.status = "failed"
        presentation.error_message = "Could not fetch content from any source. Ensure documents are indexed in Weaviate."
        await db.commit()
        await db.refresh(presentation)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not fetch content from any source. Ensure documents are indexed in Weaviate."
        )

    # Update presentation status
    presentation.status_message = f"Retrieved content from {len(sources_data)} source(s). Starting generation..."
    presentation.progress_percent = 10
    await db.commit()

    # Trigger presentation generation in the presentation service
    success = await trigger_presentation_generation(
        presentation_id=presentation.id,
        notebook_id=notebook_id,
        tenant_id=current_user.tenant_id,
        sources=sources_data,
        config=request.config.model_dump(),
    )

    if not success:
        # Update status to failed if we couldn't reach the presentation service
        presentation.status = "failed"
        presentation.error_message = "Failed to connect to presentation generation service"
        await db.commit()
        await db.refresh(presentation)

    # Use helper to avoid lazy-loading issues with async session
    return _presentation_to_response(presentation)


@router.get("/{notebook_id}/presentations", response_model=List[NotebookPresentationResponse])
async def list_presentations(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    List all generated presentations for a notebook.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get presentations
    presentations_query = select(NotebookPresentation).where(
        NotebookPresentation.notebook_id == notebook_id
    ).order_by(NotebookPresentation.created_at.desc())

    presentations_result = await db.execute(presentations_query)
    presentations = presentations_result.scalars().all()

    # Use helper to avoid lazy-loading issues with async session
    return [_presentation_to_response(p) for p in presentations]


@router.get("/{notebook_id}/presentations/{presentation_id}", response_model=NotebookPresentationResponse)
async def get_presentation(
    notebook_id: UUID,
    presentation_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get details of a specific presentation generation.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get presentation
    presentation_query = select(NotebookPresentation).where(
        and_(
            NotebookPresentation.id == presentation_id,
            NotebookPresentation.notebook_id == notebook_id,
        )
    )
    presentation_result = await db.execute(presentation_query)
    presentation = presentation_result.scalar_one_or_none()

    if not presentation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found"
        )

    # Use helper to avoid lazy-loading issues with async session
    return _presentation_to_response(presentation)


@router.get("/{notebook_id}/presentations/{presentation_id}/status", response_model=PresentationStatusResponse)
async def get_presentation_status(
    notebook_id: UUID,
    presentation_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get the status of a presentation generation.

    Use this for polling during generation.
    """
    # Simplified query - just get status fields
    presentation_query = select(
        NotebookPresentation.id,
        NotebookPresentation.status,
        NotebookPresentation.status_message,
        NotebookPresentation.progress_percent,
        NotebookPresentation.error_message,
    ).where(
        NotebookPresentation.id == presentation_id
    )
    presentation_result = await db.execute(presentation_query)
    presentation = presentation_result.one_or_none()

    if not presentation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found"
        )

    return PresentationStatusResponse(
        id=presentation.id,
        status=PresentationStatus(presentation.status),
        status_message=presentation.status_message,
        progress_percent=presentation.progress_percent,
        error_message=presentation.error_message,
    )


@router.delete("/{notebook_id}/presentations/{presentation_id}", response_model=SuccessResponse)
async def delete_presentation(
    notebook_id: UUID,
    presentation_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Delete a generated presentation.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get and delete presentation
    presentation_query = select(NotebookPresentation).where(
        and_(
            NotebookPresentation.id == presentation_id,
            NotebookPresentation.notebook_id == notebook_id,
        )
    )
    presentation_result = await db.execute(presentation_query)
    presentation = presentation_result.scalar_one_or_none()

    if not presentation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found"
        )

    # TODO: Delete PPTX file from storage if exists

    # Update notebook stats
    notebook.presentation_count = max(0, notebook.presentation_count - 1)

    await db.delete(presentation)
    await db.commit()

    logger.info(f"Presentation deleted from notebook {notebook_id}: {presentation_id}")

    return SuccessResponse(message="Presentation deleted successfully")


@router.get("/{notebook_id}/presentations/{presentation_id}/download")
async def download_presentation(
    notebook_id: UUID,
    presentation_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    current_tenant_id: UUID = Depends(get_current_tenant_id_async),
):
    """
    Download a generated PPTX presentation file.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get presentation
    presentation_query = select(NotebookPresentation).where(
        and_(
            NotebookPresentation.id == presentation_id,
            NotebookPresentation.notebook_id == notebook_id,
        )
    )
    presentation_result = await db.execute(presentation_query)
    presentation = presentation_result.scalar_one_or_none()

    if not presentation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found"
        )

    if presentation.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Presentation is not ready for download"
        )

    # Build file path
    filename = f"presentation_{presentation_id}.pptx"
    file_path = Path(LOCAL_STORAGE_PATH) / f"tenant-{current_tenant_id}" / "presentations" / str(presentation_id) / filename

    if not file_path.exists():
        logger.error(f"Presentation file not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation file not found"
        )

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


# =====================================
# CHAT Q&A ENDPOINTS
# =====================================

@router.post("/{notebook_id}/chats", response_model=NotebookChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    notebook_id: UUID,
    chat_data: NotebookChatCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Create a new chat session for Q&A with notebook sources.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Create chat
    chat = NotebookChat(
        notebook_id=notebook_id,
        user_id=current_user.id,
        title=chat_data.title,
        messages=[],
        message_count=0,
    )

    db.add(chat)

    # Update notebook stats
    notebook.chat_count += 1
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(chat)

    logger.info(f"Chat created for notebook {notebook_id}: {chat.id}")

    return NotebookChatResponse.model_validate(chat)


@router.get("/{notebook_id}/chats", response_model=List[NotebookChatResponse])
async def list_chats(
    notebook_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    include_archived: bool = Query(False),
):
    """
    List all chat sessions for a notebook.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get chats
    chats_query = select(NotebookChat).where(
        NotebookChat.notebook_id == notebook_id
    )

    if not include_archived:
        chats_query = chats_query.where(NotebookChat.is_archived == False)

    chats_query = chats_query.order_by(NotebookChat.last_message_at.desc())

    chats_result = await db.execute(chats_query)
    chats = chats_result.scalars().all()

    return [NotebookChatResponse.model_validate(c) for c in chats]


@router.get("/{notebook_id}/chats/{chat_id}", response_model=NotebookChatResponse)
async def get_chat(
    notebook_id: UUID,
    chat_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get a specific chat session with all messages.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    if not notebook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get chat
    chat_query = select(NotebookChat).where(
        and_(
            NotebookChat.id == chat_id,
            NotebookChat.notebook_id == notebook_id,
        )
    )
    chat_result = await db.execute(chat_query)
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    return NotebookChatResponse.model_validate(chat)


@router.post("/{notebook_id}/chats/{chat_id}/messages", response_model=ChatCompletionResponse)
async def send_message(
    notebook_id: UUID,
    chat_id: UUID,
    message: NotebookChatMessage,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Send a message to the chat and get an AI response.

    The AI uses the notebook's sources as context for RAG-based Q&A.
    Responses include citations from the sources.
    """
    # Verify notebook ownership and get sources
    notebook_query = select(Notebook).options(
        selectinload(Notebook.sources)
    ).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get chat
    chat_query = select(NotebookChat).where(
        and_(
            NotebookChat.id == chat_id,
            NotebookChat.notebook_id == notebook_id,
        )
    )
    chat_result = await db.execute(chat_query)
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Add user message
    now = datetime.now(timezone.utc)
    user_message = ChatMessage(
        role="user",
        content=message.content,
        timestamp=now,
        citations=None,
    )

    # Get current messages
    current_messages = chat.messages or []
    current_messages.append(user_message.model_dump())

    # Auto-generate title from first message
    if not chat.title and len(current_messages) == 1:
        chat.title = message.content[:100] + ("..." if len(message.content) > 100 else "")

    # TODO: Implement actual RAG-based response using Emma Service
    # For now, return a placeholder response
    assistant_response = ChatMessage(
        role="assistant",
        content="[RAG response pending implementation] I'll analyze your sources and provide an answer with citations.",
        timestamp=datetime.now(timezone.utc),
        citations=[],
    )

    current_messages.append(assistant_response.model_dump())

    # Update chat
    chat.messages = current_messages
    chat.message_count = len(current_messages)
    chat.last_message_at = datetime.now(timezone.utc)

    # Update notebook activity
    notebook.last_activity_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(f"Message sent to chat {chat_id} in notebook {notebook_id}")

    return ChatCompletionResponse(
        message=assistant_response,
        sources_used=len(notebook.sources),
    )


@router.delete("/{notebook_id}/chats/{chat_id}", response_model=SuccessResponse)
async def delete_chat(
    notebook_id: UUID,
    chat_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Delete a chat session.
    """
    # Verify notebook ownership
    notebook_query = select(Notebook).where(
        and_(
            Notebook.id == notebook_id,
            Notebook.user_id == current_user.id,
        )
    )
    notebook_result = await db.execute(notebook_query)
    notebook = notebook_result.scalar_one_or_none()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    # Get and delete chat
    chat_query = select(NotebookChat).where(
        and_(
            NotebookChat.id == chat_id,
            NotebookChat.notebook_id == notebook_id,
        )
    )
    chat_result = await db.execute(chat_query)
    chat = chat_result.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found"
        )

    # Update notebook stats
    notebook.chat_count = max(0, notebook.chat_count - 1)

    await db.delete(chat)
    await db.commit()

    logger.info(f"Chat deleted from notebook {notebook_id}: {chat_id}")

    return SuccessResponse(message="Chat deleted successfully")
