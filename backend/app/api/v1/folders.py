"""
Folders API - Document Folder Organization

Endpoints for managing document folders derived from folder_path in documents table.
No separate folders table - folders are physical paths in GCS.

Key Design Decisions:
- Folder tree is DERIVED from DISTINCT folder_path values
- Moving documents = GCS move + DB update + learning opportunity
- Classification status shows readiness for auto-classification activation
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import (
    get_current_user_async,
    get_current_tenant_id_async,
    get_async_db,
)
from app.db.models import User, FolderMarker
from app.services.folder_service import (
    FolderService,
    FolderNode,
    get_folder_tree,
    get_classification_stats,
)
from app.services.async_storage_client import AsyncStorageClient
from app.core.config import settings
from sqlalchemy import select
from uuid import UUID

logger = logging.getLogger(__name__)


async def get_storage_client(tenant_id: str, user_id: str) -> AsyncStorageClient:
    """Create storage client for the tenant."""
    return AsyncStorageClient(tenant_id=tenant_id, user_id=user_id)


router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class FolderNodeResponse(BaseModel):
    """Folder node in the tree structure."""
    name: str
    path: str
    document_count: int
    children: List["FolderNodeResponse"] = []

    class Config:
        from_attributes = True


class FolderListItem(BaseModel):
    """Flat folder list item."""
    path: str
    name: str
    document_count: int


class FolderTreeResponse(BaseModel):
    """Response for folder tree endpoint."""
    root: FolderNodeResponse


class FoldersListResponse(BaseModel):
    """Response for flat folders list endpoint."""
    folders: List[FolderListItem]
    total: int


class MoveDocumentRequest(BaseModel):
    """Request to move a document to a new folder."""
    new_folder_path: str = Field(..., description="Target folder path")


class MoveDocumentResponse(BaseModel):
    """Response after moving a document."""
    success: bool
    message: str
    old_folder: Optional[str] = None
    new_folder: str


class BulkMoveRequest(BaseModel):
    """Request to move multiple documents."""
    document_ids: List[str] = Field(..., description="List of document UUIDs to move")
    new_folder_path: str = Field(..., description="Target folder path")


class BulkMoveResponse(BaseModel):
    """Response after bulk move."""
    success: bool
    moved: int
    failed: int
    errors: List[str] = []


class ClassificationStatsResponse(BaseModel):
    """Statistics about document classification status."""
    total_documents: int
    classified_documents: int
    unclassified_documents: int
    auto_classified_documents: int
    distinct_folders: int
    ready_for_activation: bool
    message: str


class DocumentInFolderResponse(BaseModel):
    """Document metadata for folder listing."""
    id: str
    filename: str
    title: Optional[str]
    created_at: str
    auto_classified: bool
    classification_confidence: Optional[float]


class FolderDocumentsResponse(BaseModel):
    """Response for documents in folder endpoint."""
    folder_path: str
    documents: List[DocumentInFolderResponse]
    total: int
    page: int
    per_page: int


class CreateFolderRequest(BaseModel):
    """Request to create a new folder."""
    path: str = Field(..., description="Folder path to create")


class CreateFolderResponse(BaseModel):
    """Response after creating a folder."""
    success: bool
    message: str
    path: str


# Allow self-referencing model
FolderNodeResponse.model_rebuild()


# =============================================================================
# Helper Functions
# =============================================================================

def folder_node_to_dict(node: FolderNode) -> dict:
    """Convert FolderNode dataclass to dict recursively."""
    return {
        "name": node.name,
        "path": node.path,
        "document_count": node.document_count,
        "children": [folder_node_to_dict(child) for child in node.children]
    }


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/tree", response_model=FolderTreeResponse)
async def get_folders_tree(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get hierarchical folder tree for the tenant.

    Returns a tree structure built from DISTINCT folder_path values in documents table.
    Each node includes document count and children.

    Use this for rendering a folder navigation tree in the UI.
    """
    try:
        root = await get_folder_tree(db, tenant_id)

        return FolderTreeResponse(
            root=FolderNodeResponse(**folder_node_to_dict(root))
        )
    except Exception as e:
        logger.error(f"Error getting folder tree: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving folder tree: {str(e)}")


@router.get("", response_model=FoldersListResponse)
async def list_folders(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get flat list of all folders with document counts.

    Returns list of {path, name, document_count} for all folders.
    Sorted alphabetically by path.

    Use this for folder selection dropdowns or simple listings.
    """
    try:
        service = FolderService(db, tenant_id)
        folders = await service.get_folders_flat()

        return FoldersListResponse(
            folders=[FolderListItem(**f) for f in folders],
            total=len(folders)
        )
    except Exception as e:
        logger.error(f"Error listing folders: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing folders: {str(e)}")


@router.get("/stats", response_model=ClassificationStatsResponse)
async def get_folder_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get classification statistics for the tenant.

    Returns counts of:
    - Total documents
    - Classified documents (not in /Sin Clasificar)
    - Unclassified documents (in /Sin Clasificar)
    - Auto-classified documents (by RAG+LLM)
    - Distinct folders
    - ready_for_activation: True if enough data to suggest auto-classification

    Criteria for activation suggestion:
    - At least 20 classified documents
    - At least 3 different folders
    """
    try:
        stats = await get_classification_stats(db, tenant_id)

        # Build helpful message
        if stats.ready_for_activation:
            message = (
                f"¡Listo para activar! Tienes {stats.classified_documents} documentos "
                f"organizados en {stats.distinct_folders} carpetas."
            )
        elif stats.classified_documents < 20:
            remaining = 20 - stats.classified_documents
            message = (
                f"Organiza {remaining} documentos más para activar la auto-clasificación. "
                f"Actualmente: {stats.classified_documents}/20"
            )
        else:
            remaining = 3 - stats.distinct_folders
            message = (
                f"Crea {remaining} carpeta(s) más para activar. "
                f"Actualmente: {stats.distinct_folders}/3 carpetas"
            )

        return ClassificationStatsResponse(
            total_documents=stats.total_documents,
            classified_documents=stats.classified_documents,
            unclassified_documents=stats.unclassified_documents,
            auto_classified_documents=stats.auto_classified_documents,
            distinct_folders=stats.distinct_folders,
            ready_for_activation=stats.ready_for_activation,
            message=message
        )
    except Exception as e:
        logger.error(f"Error getting classification stats: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")


@router.get("/{folder_path:path}/documents", response_model=FolderDocumentsResponse)
async def get_documents_in_folder(
    folder_path: str = Path(..., description="Folder path (URL encoded)"),
    include_subfolders: bool = Query(False, description="Include documents in subfolders"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get documents in a specific folder.

    Args:
        folder_path: The folder path (e.g., /Proveedores/Acme)
        include_subfolders: If True, includes documents in all subfolders
        page: Page number (1-indexed)
        per_page: Documents per page (max 100)

    Returns paginated list of documents with metadata.
    """
    # Normalize path
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    try:
        service = FolderService(db, tenant_id)

        offset = (page - 1) * per_page
        documents = await service.get_documents_in_folder(
            folder_path=folder_path,
            include_subfolders=include_subfolders,
            limit=per_page,
            offset=offset
        )

        # Convert to response format
        doc_responses = [
            DocumentInFolderResponse(
                id=str(doc.id),
                filename=doc.filename,
                title=doc.title,
                created_at=doc.created_at.isoformat() if doc.created_at else "",
                auto_classified=doc.auto_classified or False,
                classification_confidence=doc.classification_confidence
            )
            for doc in documents
        ]

        return FolderDocumentsResponse(
            folder_path=folder_path,
            documents=doc_responses,
            total=len(doc_responses),  # Note: For proper pagination, we'd need a count query
            page=page,
            per_page=per_page
        )
    except Exception as e:
        logger.error(f"Error getting documents in folder {folder_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving documents: {str(e)}")


@router.put("/{document_id}/move", response_model=MoveDocumentResponse)
async def move_document_to_folder(
    document_id: str,
    request: MoveDocumentRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Move a document to a new folder.

    This operation:
    1. Updates folder_path in the database
    2. Moves the file in GCS to the new path (if storage service available)
    3. Marks the document as NOT auto_classified (manual move = user decision)
    4. Updates classification_reasoning to track the move

    Learn-First: When user moves a document, it becomes an example for future
    RAG queries. The system learns from user organization patterns.
    """
    try:
        # Create storage client for GCS operations
        storage_client = await get_storage_client(tenant_id, str(current_user.id))
        service = FolderService(db, tenant_id, storage_service=storage_client)

        # Get document's current folder before moving
        from sqlalchemy import select
        from app.db.models import Document
        from uuid import UUID

        result = await db.execute(
            select(Document.folder_path)
            .where(Document.id == UUID(document_id))
            .where(Document.tenant_id == tenant_id)
        )
        row = result.first()
        old_folder = row[0] if row else None

        if not old_folder:
            raise HTTPException(status_code=404, detail="Document not found")

        # Perform the move
        success = await service.move_document(document_id, request.new_folder_path)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to move document")

        return MoveDocumentResponse(
            success=True,
            message=f"Documento movido a {request.new_folder_path}",
            old_folder=old_folder,
            new_folder=request.new_folder_path
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error moving document: {str(e)}")


@router.post("/bulk-move", response_model=BulkMoveResponse)
async def bulk_move_documents(
    request: BulkMoveRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Move multiple documents to a new folder.

    Useful for bulk organization. Each document is processed individually,
    and failures don't stop other moves.

    Returns count of successful and failed moves with error details.
    """
    # Create storage client for GCS operations
    storage_client = await get_storage_client(tenant_id, str(current_user.id))
    service = FolderService(db, tenant_id, storage_service=storage_client)

    moved = 0
    failed = 0
    errors = []

    for doc_id in request.document_ids:
        try:
            success = await service.move_document(doc_id, request.new_folder_path)
            if success:
                moved += 1
            else:
                failed += 1
                errors.append(f"Document {doc_id}: Move failed")
        except Exception as e:
            failed += 1
            errors.append(f"Document {doc_id}: {str(e)}")

    return BulkMoveResponse(
        success=failed == 0,
        moved=moved,
        failed=failed,
        errors=errors
    )


@router.post("", response_model=CreateFolderResponse, status_code=201)
async def create_folder(
    request: CreateFolderRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Create an empty folder.

    Creates a FolderMarker in the database so the folder appears in navigation
    even before documents are added. When a document is moved to this folder,
    the marker becomes redundant (folder is derived from document paths).
    """
    folder_path = request.path

    # Normalize path
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    try:
        # Check if folder already exists (either as marker or with documents)
        existing_marker = await db.execute(
            select(FolderMarker)
            .where(FolderMarker.tenant_id == UUID(tenant_id))
            .where(FolderMarker.folder_path == folder_path)
        )
        if existing_marker.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"La carpeta {folder_path} ya existe"
            )

        # Check if folder has documents (already exists implicitly)
        service = FolderService(db, tenant_id)
        documents = await service.get_documents_in_folder(folder_path, include_subfolders=False, limit=1)
        if documents:
            raise HTTPException(
                status_code=409,
                detail=f"La carpeta {folder_path} ya existe con documentos"
            )

        # Create the folder marker
        folder_marker = FolderMarker(
            tenant_id=UUID(tenant_id),
            folder_path=folder_path,
            created_by=current_user.id
        )
        db.add(folder_marker)
        await db.commit()

        logger.info(f"Created folder marker: {folder_path} for tenant {tenant_id}")

        return CreateFolderResponse(
            success=True,
            message=f"Carpeta {folder_path} creada",
            path=folder_path
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating folder {folder_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating folder: {str(e)}")


@router.delete("/{folder_path:path}")
async def delete_folder(
    folder_path: str = Path(..., description="Folder path to delete"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Delete an empty folder.

    Only succeeds if the folder contains no documents.
    Use bulk-move to relocate documents before deleting.
    """
    if not folder_path.startswith("/"):
        folder_path = "/" + folder_path

    # Check if folder has documents
    service = FolderService(db, tenant_id)

    documents = await service.get_documents_in_folder(folder_path, include_subfolders=True, limit=1)

    if documents:
        raise HTTPException(
            status_code=400,
            detail=f"La carpeta {folder_path} contiene documentos. Muévelos primero."
        )

    # For now, just return success - empty folders don't have DB entries
    # If we had GCS marker files, we'd delete them here

    return {
        "success": True,
        "message": f"Carpeta {folder_path} eliminada",
        "path": folder_path
    }
