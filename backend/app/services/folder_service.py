"""
Folder Service - Document Folder Organization

Manages physical folder structure in GCS and database.
Folders are derived from document paths (no separate folders table).

Features:
- List folder tree from DISTINCT folder_paths
- Move documents between folders (GCS + DB)
- Get documents in a folder
- Classification statistics
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, distinct, select, update, union_all, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, IndexedDocument, Tenant, FolderMarker

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FolderNode:
    """Node in the folder tree."""
    name: str
    path: str
    document_count: int = 0
    children: List["FolderNode"] = field(default_factory=list)


@dataclass
class FolderStats:
    """Statistics for classification system."""
    total_documents: int
    classified_documents: int  # Not in /Sin Clasificar
    unclassified_documents: int  # In /Sin Clasificar
    auto_classified_documents: int
    distinct_folders: int
    ready_for_activation: bool


# =============================================================================
# Async Folder Service
# =============================================================================

class FolderService:
    """
    Async service for managing document folders.

    Folders are physical paths in GCS, derived from document.folder_path.
    No separate folders table - we use DISTINCT folder_path queries.
    """

    def __init__(self, db: AsyncSession, tenant_id: str, storage_service=None):
        self.db = db
        self.tenant_id = tenant_id
        self.storage_service = storage_service

    async def get_folder_tree(self) -> FolderNode:
        """
        Build folder tree from DISTINCT folder_paths.

        Returns hierarchical tree structure for UI rendering.
        Includes:
        - Document table folders (direct uploads)
        - IndexedDocument table folders (connector documents)
        - Empty FolderMarkers
        """
        from collections import defaultdict
        path_to_count: Dict[str, int] = defaultdict(int)

        # Get folder paths from Document table (direct uploads)
        doc_stmt = (
            select(
                Document.folder_path,
                func.count(Document.id).label("count")
            )
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.folder_path.isnot(None))
            .group_by(Document.folder_path)
        )
        doc_result = await self.db.execute(doc_stmt)
        for path, count in doc_result.all():
            if path:
                path_to_count[path] += count

        # Get folder paths from IndexedDocument table (connector documents)
        idx_stmt = (
            select(
                IndexedDocument.external_path,
                func.count(IndexedDocument.id).label("count")
            )
            .where(IndexedDocument.tenant_id == UUID(self.tenant_id))
            .where(IndexedDocument.external_path.isnot(None))
            .group_by(IndexedDocument.external_path)
        )
        idx_result = await self.db.execute(idx_stmt)
        for path, count in idx_result.all():
            if path:
                path_to_count[path] += count

        # Get empty folder markers
        markers_stmt = (
            select(FolderMarker.folder_path)
            .where(FolderMarker.tenant_id == UUID(self.tenant_id))
        )
        markers_result = await self.db.execute(markers_stmt)
        marker_paths = {row[0] for row in markers_result.all() if row[0]}

        # Add empty folder markers (with 0 count)
        for marker_path in marker_paths:
            if marker_path not in path_to_count:
                path_to_count[marker_path] = 0

        # Build tree from paths
        root = FolderNode(name="root", path="/", document_count=0)

        for folder_path, count in path_to_count.items():
            self._add_path_to_tree(root, folder_path, count)

        return root

    def _add_path_to_tree(self, root: FolderNode, path: str, count: int):
        """Add a path to the folder tree."""
        if not path or path == "/":
            root.document_count += count
            return

        # Split path into parts
        parts = [p for p in path.split("/") if p]
        current = root

        for i, part in enumerate(parts):
            current_path = "/" + "/".join(parts[:i+1])

            # Find or create child node
            child = next((c for c in current.children if c.name == part), None)
            if not child:
                child = FolderNode(name=part, path=current_path, document_count=0)
                current.children.append(child)

            # If this is the final part, add count
            if i == len(parts) - 1:
                child.document_count = count

            current = child

    async def get_folders_flat(self) -> List[Dict[str, Any]]:
        """
        Get flat list of folders with counts.

        Returns list of {path, name, document_count} dicts.
        Includes:
        - Document table folders (direct uploads)
        - IndexedDocument table folders (connector documents)
        - Empty folders from FolderMarker table (with 0 count)
        """
        from collections import defaultdict
        all_folders: Dict[str, int] = defaultdict(int)

        # Get folders from Document table (direct uploads)
        doc_folders_stmt = (
            select(
                Document.folder_path,
                func.count(Document.id).label("count")
            )
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.folder_path.isnot(None))
            .group_by(Document.folder_path)
        )
        doc_result = await self.db.execute(doc_folders_stmt)
        for path, count in doc_result.all():
            if path:
                all_folders[path] += count

        # Get folders from IndexedDocument table (connector documents)
        idx_folders_stmt = (
            select(
                IndexedDocument.external_path,
                func.count(IndexedDocument.id).label("count")
            )
            .where(IndexedDocument.tenant_id == UUID(self.tenant_id))
            .where(IndexedDocument.external_path.isnot(None))
            .group_by(IndexedDocument.external_path)
        )
        idx_result = await self.db.execute(idx_folders_stmt)
        for path, count in idx_result.all():
            if path:
                all_folders[path] += count

        # Get empty folder markers
        markers_stmt = (
            select(FolderMarker.folder_path)
            .where(FolderMarker.tenant_id == UUID(self.tenant_id))
        )
        markers_result = await self.db.execute(markers_stmt)
        marker_paths = {row[0] for row in markers_result.all() if row[0]}

        # Add folder markers that don't have documents yet
        for marker_path in marker_paths:
            if marker_path not in all_folders:
                all_folders[marker_path] = 0

        # Sort by path and return
        sorted_folders = sorted(all_folders.items(), key=lambda x: x[0])

        return [
            {
                "path": path,
                "name": path.split("/")[-1] if path else "root",
                "document_count": count,
            }
            for path, count in sorted_folders
        ]

    async def get_documents_in_folder(
        self,
        folder_path: str,
        include_subfolders: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Document]:
        """
        Get documents in a specific folder.

        Args:
            folder_path: Folder path to query
            include_subfolders: If True, include documents in subfolders
            limit: Max documents to return
            offset: Pagination offset

        Returns:
            List of Document objects
        """
        stmt = select(Document).where(Document.tenant_id == self.tenant_id)

        if include_subfolders:
            # Use LIKE for prefix matching
            stmt = stmt.where(Document.folder_path.startswith(folder_path))
        else:
            stmt = stmt.where(Document.folder_path == folder_path)

        stmt = stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def move_document(
        self,
        document_id: str,
        new_folder_path: str,
    ) -> bool:
        """
        Move a document to a new folder.

        Steps:
        1. Update folder_path in DB
        2. Move file in GCS (if storage_service available)
        3. Mark as manually classified (not auto_classified)

        Args:
            document_id: Document UUID
            new_folder_path: New folder path

        Returns:
            True if successful
        """
        # Get document
        stmt = (
            select(Document)
            .where(Document.id == UUID(document_id))
            .where(Document.tenant_id == self.tenant_id)
        )
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document:
            logger.warning(f"Document {document_id} not found")
            return False

        old_folder = document.folder_path
        old_file_path = document.file_path

        # Normalize new folder path
        if not new_folder_path.startswith("/"):
            new_folder_path = "/" + new_folder_path

        # Calculate new file path
        # IMPORTANT: Extract the stored filename (with UUID) from the current path
        # NOT the original filename. The file in GCS is stored as {uuid}.{ext}
        stored_filename = old_file_path.split("/")[-1]  # Get last part of path (the actual file)
        new_file_path = f"{new_folder_path.lstrip('/')}/{stored_filename}"

        # Move in GCS if storage service available
        if self.storage_service and old_file_path != new_file_path:
            try:
                # Get tenant for bucket name
                tenant_stmt = select(Tenant).where(Tenant.id == self.tenant_id)
                tenant_result = await self.db.execute(tenant_stmt)
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    await self._move_file_in_gcs(
                        tenant.bucket_name,
                        old_file_path,
                        new_file_path,
                    )
            except Exception as e:
                logger.error(f"Failed to move file in GCS: {e}")
                # Continue anyway - DB update is more important

        # Update DB
        document.folder_path = new_folder_path
        document.file_path = new_file_path
        document.auto_classified = False  # Manual move = not auto-classified
        document.classification_reasoning = f"Movido manualmente de {old_folder}"

        try:
            await self.db.commit()
            logger.info(f"Moved document {document_id} from {old_folder} to {new_folder_path}")
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update document folder: {e}")
            return False

    async def _move_file_in_gcs(
        self,
        bucket_name: str,
        old_path: str,
        new_path: str,
    ):
        """Move file in GCS using storage service."""
        try:
            result = await self.storage_service.move_file(old_path, new_path)
            logger.info(f"Moved file in GCS: {old_path} -> {new_path} (bucket: {bucket_name})")
            return result
        except Exception as e:
            logger.error(f"Failed to move file in GCS: {old_path} -> {new_path}: {e}")
            raise

    async def get_classification_stats(self) -> FolderStats:
        """
        Get statistics about document classification.

        Used to determine if auto-classification should be suggested.
        Combines stats from both Document and IndexedDocument tables.
        """
        # Total documents from Document table
        doc_total_stmt = (
            select(func.count(Document.id))
            .where(Document.tenant_id == self.tenant_id)
        )
        doc_total_result = await self.db.execute(doc_total_stmt)
        doc_total = doc_total_result.scalar() or 0

        # Total documents from IndexedDocument table
        idx_total_stmt = (
            select(func.count(IndexedDocument.id))
            .where(IndexedDocument.tenant_id == UUID(self.tenant_id))
        )
        idx_total_result = await self.db.execute(idx_total_stmt)
        idx_total = idx_total_result.scalar() or 0

        total = doc_total + idx_total

        # Unclassified from Document table (in /Sin Clasificar)
        doc_unclassified_stmt = (
            select(func.count(Document.id))
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.folder_path == "/Sin Clasificar")
        )
        doc_unclassified_result = await self.db.execute(doc_unclassified_stmt)
        doc_unclassified = doc_unclassified_result.scalar() or 0

        # IndexedDocument doesn't have /Sin Clasificar concept - all are "classified" by source
        # But we can check for null/empty external_path
        idx_unclassified_stmt = (
            select(func.count(IndexedDocument.id))
            .where(IndexedDocument.tenant_id == UUID(self.tenant_id))
            .where(
                (IndexedDocument.external_path.is_(None)) |
                (IndexedDocument.external_path == "") |
                (IndexedDocument.external_path == "/")
            )
        )
        idx_unclassified_result = await self.db.execute(idx_unclassified_stmt)
        idx_unclassified = idx_unclassified_result.scalar() or 0

        unclassified = doc_unclassified + idx_unclassified

        # Auto-classified from Document table
        auto_stmt = (
            select(func.count(Document.id))
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.auto_classified == True)
        )
        auto_result = await self.db.execute(auto_stmt)
        auto_classified = auto_result.scalar() or 0
        # IndexedDocument doesn't have auto_classified concept

        # Distinct folders from Document table (excluding /Sin Clasificar)
        doc_folders_stmt = (
            select(func.count(distinct(Document.folder_path)))
            .where(Document.tenant_id == self.tenant_id)
            .where(Document.folder_path != "/Sin Clasificar")
            .where(Document.folder_path.isnot(None))
        )
        doc_folders_result = await self.db.execute(doc_folders_stmt)
        doc_folders = doc_folders_result.scalar() or 0

        # Distinct folders from IndexedDocument table
        idx_folders_stmt = (
            select(func.count(distinct(IndexedDocument.external_path)))
            .where(IndexedDocument.tenant_id == UUID(self.tenant_id))
            .where(IndexedDocument.external_path.isnot(None))
            .where(IndexedDocument.external_path != "")
            .where(IndexedDocument.external_path != "/")
        )
        idx_folders_result = await self.db.execute(idx_folders_stmt)
        idx_folders = idx_folders_result.scalar() or 0

        # Note: This might double-count folders with same path in both tables
        # but that's rare in practice
        distinct_folders = doc_folders + idx_folders

        classified = total - unclassified

        # Ready for activation: at least 20 classified docs in 3+ folders
        ready = classified >= 20 and distinct_folders >= 3

        return FolderStats(
            total_documents=total,
            classified_documents=classified,
            unclassified_documents=unclassified,
            auto_classified_documents=auto_classified,
            distinct_folders=distinct_folders,
            ready_for_activation=ready,
        )


# =============================================================================
# Convenience Functions (Async)
# =============================================================================

async def get_folder_tree(db: AsyncSession, tenant_id: str) -> FolderNode:
    """Get folder tree for a tenant."""
    service = FolderService(db, tenant_id)
    return await service.get_folder_tree()


async def get_classification_stats(db: AsyncSession, tenant_id: str) -> FolderStats:
    """Get classification statistics for a tenant."""
    service = FolderService(db, tenant_id)
    return await service.get_classification_stats()
