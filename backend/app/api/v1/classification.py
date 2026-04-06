"""
Classification API - RAG + LLM Auto-Classification System

Endpoints for managing the Learn-First document classification system:
1. Status: Check if auto-classification can be activated
2. Settings: Configure k (neighbors), min_confidence threshold
3. Activate/Deactivate: Enable or disable auto-classification
4. Preview: See where a document WOULD be classified (without moving)

Architecture:
- RAG: Weaviate vector search finds similar classified documents
- LLM: SGLang (Qwen3-4B) decides folder with reasoning
- Learn-First: System learns from user's manual organization
"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.api.async_dependencies import (
    get_current_user_async,
    get_current_tenant_id_async,
    get_async_db,
)
from app.db.models import User, Tenant
from app.services.folder_classification_service import (
    FolderClassificationService,
    ClassificationResult,
    classify_document,
)
from app.services.folder_service import get_classification_stats

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class ClassificationStatusResponse(BaseModel):
    """Status of the auto-classification system."""
    enabled: bool
    k: int
    min_confidence: float
    total_documents: int
    classified_documents: int
    unclassified_documents: int
    auto_classified_documents: int
    distinct_folders: int
    ready_for_activation: bool
    message: str


class ClassificationSettingsRequest(BaseModel):
    """Request to update classification settings."""
    k: Optional[int] = Field(None, ge=3, le=20, description="Number of similar docs to retrieve")
    min_confidence: Optional[float] = Field(None, ge=0.1, le=1.0, description="Minimum LLM confidence")


class ClassificationSettingsResponse(BaseModel):
    """Response with updated settings."""
    k: int
    min_confidence: float
    message: str


class ActivateResponse(BaseModel):
    """Response after activation/deactivation."""
    enabled: bool
    message: str


class ClassificationPreviewRequest(BaseModel):
    """Request to preview classification for a document."""
    doc_id: Optional[str] = Field(None, description="Document UUID (for existing docs)")
    filename: Optional[str] = Field(None, description="Filename (for new docs)")
    file_type: Optional[str] = Field(None, description="File type/extension")
    content: str = Field(..., description="Document content (text)")


class ClassificationPreviewResponse(BaseModel):
    """Preview of where a document would be classified."""
    carpeta: str
    confianza: float
    razonamiento: str
    carpetas_alternativas: list
    es_carpeta_nueva: bool
    would_auto_classify: bool
    message: str


# =============================================================================
# Helper Functions
# =============================================================================

async def get_tenant_settings(db: AsyncSession, tenant_id: str) -> Tenant:
    """Get tenant with classification settings."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=ClassificationStatusResponse)
async def get_classification_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get the status of the auto-classification system.

    Returns:
    - enabled: Whether auto-classification is active
    - k: Number of similar documents retrieved for RAG
    - min_confidence: Minimum LLM confidence to auto-classify
    - Classification statistics (total, classified, unclassified, etc.)
    - ready_for_activation: True if enough data to suggest activation

    Learn-First Approach:
    - Initially disabled (user organizes manually)
    - System shows readiness once enough examples exist
    - User activates when ready
    """
    tenant = await get_tenant_settings(db, tenant_id)

    # Get stats using sync session
    sync_db = db.sync_session
    stats = get_classification_stats(sync_db, tenant_id)

    # Build message based on status
    if tenant.auto_classification_enabled:
        message = (
            f"Auto-clasificación ACTIVA. "
            f"{stats.auto_classified_documents} documentos clasificados por IA."
        )
    elif stats.ready_for_activation:
        message = (
            f"¡Listo para activar! {stats.classified_documents} documentos en "
            f"{stats.distinct_folders} carpetas. Haz clic en 'Activar' para comenzar."
        )
    else:
        if stats.classified_documents < 20:
            remaining = 20 - stats.classified_documents
            message = f"Organiza {remaining} documentos más para activar."
        else:
            remaining = 3 - stats.distinct_folders
            message = f"Crea {remaining} carpeta(s) más para activar."

    return ClassificationStatusResponse(
        enabled=tenant.auto_classification_enabled,
        k=tenant.auto_classification_k,
        min_confidence=tenant.auto_classification_min_confidence,
        total_documents=stats.total_documents,
        classified_documents=stats.classified_documents,
        unclassified_documents=stats.unclassified_documents,
        auto_classified_documents=stats.auto_classified_documents,
        distinct_folders=stats.distinct_folders,
        ready_for_activation=stats.ready_for_activation,
        message=message
    )


@router.put("/settings", response_model=ClassificationSettingsResponse)
async def update_classification_settings(
    request: ClassificationSettingsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update classification settings for the tenant.

    Settings:
    - k: Number of similar documents to retrieve (3-20, default 7)
    - min_confidence: Minimum LLM confidence to auto-classify (0.1-1.0, default 0.6)

    Higher k = more context but slower
    Higher min_confidence = fewer auto-classifications but higher accuracy
    """
    tenant = await get_tenant_settings(db, tenant_id)

    # Update only provided fields
    updates = {}
    if request.k is not None:
        updates["auto_classification_k"] = request.k
    if request.min_confidence is not None:
        updates["auto_classification_min_confidence"] = request.min_confidence

    if updates:
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(**updates)
        )
        await db.commit()
        await db.refresh(tenant)

    return ClassificationSettingsResponse(
        k=tenant.auto_classification_k,
        min_confidence=tenant.auto_classification_min_confidence,
        message="Configuración actualizada"
    )


@router.post("/activate", response_model=ActivateResponse)
async def activate_classification(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Activate auto-classification for the tenant.

    Prerequisites (checked but not enforced):
    - At least 20 classified documents
    - At least 3 different folders

    After activation:
    - New documents will be auto-classified using RAG + LLM
    - System uses existing classified documents as examples
    - Classification happens during document upload
    """
    # Check if ready (but allow activation anyway for testing)
    sync_db = db.sync_session
    stats = get_classification_stats(sync_db, tenant_id)

    await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(auto_classification_enabled=True)
    )
    await db.commit()

    if not stats.ready_for_activation:
        message = (
            "Auto-clasificación ACTIVADA (con datos limitados). "
            "Recomendamos tener al menos 20 documentos en 3+ carpetas."
        )
    else:
        message = (
            f"Auto-clasificación ACTIVADA. El sistema aprenderá de tus "
            f"{stats.classified_documents} documentos organizados."
        )

    return ActivateResponse(enabled=True, message=message)


@router.post("/deactivate", response_model=ActivateResponse)
async def deactivate_classification(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Deactivate auto-classification for the tenant.

    After deactivation:
    - New documents go to "/Sin Clasificar"
    - User continues organizing manually
    - System continues to learn from manual organization
    - Can reactivate at any time
    """
    await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(auto_classification_enabled=False)
    )
    await db.commit()

    return ActivateResponse(
        enabled=False,
        message="Auto-clasificación DESACTIVADA. Los nuevos documentos irán a '/Sin Clasificar'."
    )


@router.post("/preview", response_model=ClassificationPreviewResponse)
async def preview_classification(
    request: ClassificationPreviewRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Preview where a document would be classified (without actually moving it).

    This is useful for:
    - Testing classification before activation
    - Seeing how the system would classify a document
    - Understanding the reasoning behind classifications

    The response includes:
    - carpeta: Suggested folder path
    - confianza: LLM confidence (0-1)
    - razonamiento: Why this folder was chosen
    - carpetas_alternativas: Other possible folders
    - es_carpeta_nueva: True if suggesting a new folder
    - would_auto_classify: True if confidence >= min_confidence
    """
    tenant = await get_tenant_settings(db, tenant_id)

    # Build document dict for classification
    documento = {
        "doc_id": request.doc_id or "",
        "filename": request.filename or "documento",
        "file_type": request.file_type or "unknown",
        "content": request.content,
    }

    # Run classification
    try:
        result = await classify_document(
            tenant_id=tenant_id,
            documento=documento,
            k=tenant.auto_classification_k,
            min_confidence=tenant.auto_classification_min_confidence,
        )
    except Exception as e:
        logger.error(f"Classification preview failed: {e}")
        raise HTTPException(status_code=500, detail=f"Error en clasificación: {str(e)}")

    # Would this be auto-classified?
    would_auto = result.confianza >= tenant.auto_classification_min_confidence

    # Build message
    if result.confianza == 0:
        message = "No hay documentos de referencia para clasificar."
    elif would_auto:
        message = f"Se clasificaría automáticamente en '{result.carpeta}' ({result.confianza:.0%} confianza)."
    else:
        message = (
            f"Confianza ({result.confianza:.0%}) menor al umbral ({tenant.auto_classification_min_confidence:.0%}). "
            f"Iría a '/Sin Clasificar'."
        )

    return ClassificationPreviewResponse(
        carpeta=result.carpeta,
        confianza=result.confianza,
        razonamiento=result.razonamiento,
        carpetas_alternativas=result.carpetas_alternativas,
        es_carpeta_nueva=result.es_carpeta_nueva,
        would_auto_classify=would_auto,
        message=message
    )


@router.post("/classify/{document_id}")
async def classify_existing_document(
    document_id: str,
    apply: bool = Query(False, description="If True, move document to suggested folder"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Classify an existing document and optionally move it.

    Use case: Re-classify documents that were uploaded before activation,
    or re-run classification on documents that were put in /Sin Clasificar.

    Args:
        document_id: UUID of the document
        apply: If True, move document to the suggested folder

    Returns classification result. If apply=True, also moves the document.
    """
    from uuid import UUID
    from app.db.models import Document
    from app.services.folder_service import FolderService

    # Get document
    result = await db.execute(
        select(Document)
        .where(Document.id == UUID(document_id))
        .where(Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    tenant = await get_tenant_settings(db, tenant_id)

    # Build document dict
    documento = {
        "doc_id": str(document.id),
        "filename": document.filename,
        "file_type": document.file_type,
        "content": document.content or "",  # Need to get content from somewhere
    }

    # Run classification
    classification = await classify_document(
        tenant_id=tenant_id,
        documento=documento,
        k=tenant.auto_classification_k,
        min_confidence=tenant.auto_classification_min_confidence,
    )

    response = {
        "document_id": str(document.id),
        "current_folder": document.folder_path,
        "suggested_folder": classification.carpeta,
        "confidence": classification.confianza,
        "reasoning": classification.razonamiento,
        "alternatives": classification.carpetas_alternativas,
        "is_new_folder": classification.es_carpeta_nueva,
        "applied": False,
    }

    # Apply if requested and confidence is high enough
    if apply and classification.confianza >= tenant.auto_classification_min_confidence:
        sync_db = db.sync_session
        service = FolderService(sync_db, tenant_id)
        success = await service.move_document(document_id, classification.carpeta)

        if success:
            # Update classification metadata
            document.auto_classified = True
            document.classification_confidence = classification.confianza
            document.classification_reasoning = classification.razonamiento
            await db.commit()

            response["applied"] = True
            response["message"] = f"Documento movido a '{classification.carpeta}'"
        else:
            response["message"] = "No se pudo mover el documento"
    elif apply:
        response["message"] = (
            f"Confianza ({classification.confianza:.0%}) menor al umbral. "
            f"No se movió el documento."
        )
    else:
        response["message"] = "Preview only (apply=False)"

    return response
