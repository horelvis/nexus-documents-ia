"""
Unified Document Query Service

Provides a unified interface for querying documents from both:
- Document table (direct uploads via web UI - SaaS mode)
- IndexedDocument table (connector documents - On-Premise mode)

This abstraction ensures that all document-related queries work correctly
regardless of deployment mode (SaaS vs On-Premise).

Usage:
    from app.services.unified_document_query import UnifiedDocumentQuery

    # In an async endpoint:
    query = UnifiedDocumentQuery(db, user)

    # Get total document count
    total = await query.count_documents()

    # Get documents with pagination
    docs = await query.get_documents(page=1, per_page=20)

    # Get document by ID (searches both tables)
    doc = await query.get_document_by_id(document_id)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.base import UserProfile
from app.db.models import Document, IndexedDocument

logger = logging.getLogger(__name__)


class DocumentSource(str, Enum):
    """Source of a document."""
    UPLOAD = "upload"      # Direct upload (Document table)
    CONNECTOR = "connector"  # From connector (IndexedDocument table)
    BOTH = "both"          # Query both tables


@dataclass
class UnifiedDocument:
    """
    Unified document representation that works with both Document and IndexedDocument.

    Maps fields from both tables to a common structure.
    """
    id: UUID
    title: str
    filename: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: int = 0
    file_extension: Optional[str] = None

    # Status
    is_indexed: bool = False
    indexing_status: str = "pending"  # pending, processing, indexed, failed
    indexing_error: Optional[str] = None

    # Source info
    source: DocumentSource = DocumentSource.UPLOAD
    connector_id: Optional[UUID] = None
    connector_type: Optional[str] = None
    external_id: Optional[str] = None
    external_url: Optional[str] = None

    # Weaviate reference
    weaviate_id: Optional[UUID] = None
    weaviate_collection: Optional[str] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Additional metadata
    folder_path: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = None

    # Access control (for IndexedDocument)
    owner_id: Optional[UUID] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    @classmethod
    def from_document(cls, doc: Document) -> "UnifiedDocument":
        """Create UnifiedDocument from Document model."""
        return cls(
            id=doc.id,
            title=doc.title or doc.filename,
            filename=doc.filename,
            description=doc.description,
            mime_type=doc.mime_type,
            file_size=doc.file_size or 0,
            file_extension=doc.file_type,
            is_indexed=doc.indexed == 1,
            indexing_status="indexed" if doc.indexed == 1 else ("failed" if doc.indexed == 2 else "pending"),
            indexing_error=doc.indexing_error,
            source=DocumentSource.UPLOAD,
            weaviate_id=doc.weaviate_id if hasattr(doc, 'weaviate_id') else None,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            folder_path=doc.folder_path,
            category=doc.category,
            tags=[tag.name for tag in doc.tags] if hasattr(doc, 'tags') and doc.tags else [],
            owner_id=doc.created_by,
        )

    @classmethod
    def from_indexed_document(cls, doc: IndexedDocument) -> "UnifiedDocument":
        """Create UnifiedDocument from IndexedDocument model."""
        return cls(
            id=doc.id,
            title=doc.title,
            filename=doc.title,  # IndexedDocument uses title as filename
            description=doc.description,
            mime_type=doc.mime_type,
            file_size=doc.size_bytes or 0,
            file_extension=doc.file_extension,
            is_indexed=doc.indexing_status == "indexed",
            indexing_status=doc.indexing_status or "pending",
            indexing_error=doc.indexing_error,
            source=DocumentSource.CONNECTOR,
            connector_id=doc.connector_id,
            connector_type=doc.connector_type,
            external_id=doc.external_id,
            external_url=doc.external_url,
            weaviate_id=doc.weaviate_id,
            weaviate_collection=doc.weaviate_collection,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            folder_path=doc.external_path,
            owner_id=doc.owner_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "title": self.title,
            "filename": self.filename,
            "description": self.description,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_extension": self.file_extension,
            "is_indexed": self.is_indexed,
            "indexing_status": self.indexing_status,
            "indexing_error": self.indexing_error,
            "source": self.source.value,
            "connector_id": str(self.connector_id) if self.connector_id else None,
            "connector_type": self.connector_type,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "weaviate_id": str(self.weaviate_id) if self.weaviate_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "folder_path": self.folder_path,
            "category": self.category,
            "tags": self.tags,
        }


class UnifiedDocumentQuery:
    """
    Unified query interface for documents from both tables.

    This class provides methods to query, count, and aggregate documents
    from both the Document and IndexedDocument tables.
    """

    def __init__(
        self,
        db: AsyncSession,
        user: Optional[UserProfile] = None,
        source: DocumentSource = DocumentSource.BOTH,
    ):
        """
        Initialize the query service.

        Args:
            db: Async database session
            user: Current user profile for ACL filtering (None = admin/background scope)
            source: Which table(s) to query (default: both)
        """
        self.db = db
        self.user = user
        self.source = source

    def _apply_doc_acl(self, query):
        """Pass-through: all authenticated users can see all documents.
        Role-based ACL removed; kept as identity function for call-site compatibility."""
        return query

    async def count_documents(
        self,
        indexed_only: bool = False,
        include_errors: bool = True,
    ) -> Dict[str, int]:
        """
        Count total documents across both tables.

        Args:
            indexed_only: Only count successfully indexed documents
            include_errors: Include documents with errors in count

        Returns:
            Dictionary with counts: {total, indexed, processing, error, uploads, connectors}
        """
        result = {
            "total": 0,
            "indexed": 0,
            "processing": 0,
            "error": 0,
            "uploads": 0,
            "connectors": 0,
        }

        # Count from Document table
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_query = select(
                func.count(Document.id).label('total'),
                func.sum(case((Document.indexed == 1, 1), else_=0)).label('indexed'),
                func.sum(case((Document.indexed == 0, 1), else_=0)).label('processing'),
                func.sum(case((Document.indexing_error != None, 1), else_=0)).label('error'),
            )

            doc_result = await self.db.execute(doc_query)
            doc_row = doc_result.one()

            result["uploads"] = doc_row.total or 0
            result["total"] += doc_row.total or 0
            result["indexed"] += doc_row.indexed or 0
            result["processing"] += doc_row.processing or 0
            result["error"] += doc_row.error or 0

        # Count from IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_query = select(
                func.count(IndexedDocument.id).label('total'),
                func.sum(case((IndexedDocument.indexing_status == 'indexed', 1), else_=0)).label('indexed'),
                func.sum(case((IndexedDocument.indexing_status.in_(['pending', 'processing']), 1), else_=0)).label('processing'),
                func.sum(case((IndexedDocument.indexing_status == 'failed', 1), else_=0)).label('error'),
            )

            idx_result = await self.db.execute(idx_query)
            idx_row = idx_result.one()

            result["connectors"] = idx_row.total or 0
            result["total"] += idx_row.total or 0
            result["indexed"] += idx_row.indexed or 0
            result["processing"] += idx_row.processing or 0
            result["error"] += idx_row.error or 0

        return result

    async def get_total_storage(self) -> Dict[str, int]:
        """
        Get total storage used across both tables.

        Returns:
            Dictionary with storage info: {total_bytes, uploads_bytes, connectors_bytes}
        """
        result = {
            "total_bytes": 0,
            "uploads_bytes": 0,
            "connectors_bytes": 0,
        }

        # Storage from Document table
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_query = select(
                func.coalesce(func.sum(Document.file_size), 0)
            )

            doc_result = await self.db.execute(doc_query)
            result["uploads_bytes"] = doc_result.scalar() or 0
            result["total_bytes"] += result["uploads_bytes"]

        # Storage from IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_query = select(
                func.coalesce(func.sum(IndexedDocument.size_bytes), 0)
            )

            idx_result = await self.db.execute(idx_query)
            result["connectors_bytes"] = idx_result.scalar() or 0
            result["total_bytes"] += result["connectors_bytes"]

        return result

    async def get_document_by_id(
        self,
        document_id: Union[str, UUID],
    ) -> Optional[UnifiedDocument]:
        """
        Get a document by ID, searching both tables.

        Args:
            document_id: Document ID to find

        Returns:
            UnifiedDocument if found, None otherwise
        """
        doc_id = UUID(document_id) if isinstance(document_id, str) else document_id

        # Try Document table first
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_query = self._apply_doc_acl(
                select(Document).where(Document.id == doc_id)
            )
            doc_result = await self.db.execute(doc_query)
            doc = doc_result.scalar_one_or_none()
            if doc:
                return UnifiedDocument.from_document(doc)

        # Try IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_query = select(IndexedDocument).where(
                IndexedDocument.id == doc_id,
            )
            idx_result = await self.db.execute(idx_query)
            idx_doc = idx_result.scalar_one_or_none()
            if idx_doc:
                return UnifiedDocument.from_indexed_document(idx_doc)

        return None

    async def get_documents(
        self,
        page: int = 1,
        per_page: int = 20,
        indexed_only: bool = False,
        order_by: str = "created_at",
        order_desc: bool = True,
        folder_path: Optional[str] = None,
        search_term: Optional[str] = None,
    ) -> Tuple[List[UnifiedDocument], int]:
        """
        Get paginated list of documents from both tables.

        Args:
            page: Page number (1-indexed)
            per_page: Documents per page
            indexed_only: Only return indexed documents
            order_by: Field to sort by
            order_desc: Sort descending
            folder_path: Filter by folder path
            search_term: Search in title/filename

        Returns:
            Tuple of (documents list, total count)
        """
        documents: List[UnifiedDocument] = []
        total = 0
        offset = (page - 1) * per_page

        # Get from Document table
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_filters = []

            if indexed_only:
                doc_filters.append(Document.indexed == 1)
            if folder_path:
                doc_filters.append(Document.folder_path == folder_path)
            if search_term:
                doc_filters.append(
                    or_(
                        Document.title.ilike(f"%{search_term}%"),
                        Document.filename.ilike(f"%{search_term}%"),
                    )
                )

            # Count (ACL-scoped if user present)
            count_base = select(func.count(Document.id))
            if doc_filters:
                count_base = count_base.where(and_(*doc_filters))
            count_query = self._apply_doc_acl(count_base)
            count_result = await self.db.execute(count_query)
            doc_count = count_result.scalar() or 0
            total += doc_count

            # Get documents
            doc_base = select(Document)
            if doc_filters:
                doc_base = doc_base.where(and_(*doc_filters))
            doc_query = self._apply_doc_acl(doc_base)

            # Order
            order_col = getattr(Document, order_by, Document.created_at)
            doc_query = doc_query.order_by(order_col.desc() if order_desc else order_col.asc())

            # Paginate (simple approach - get all and slice)
            doc_result = await self.db.execute(doc_query)
            for doc in doc_result.scalars().all():
                documents.append(UnifiedDocument.from_document(doc))

        # Get from IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_filters = []

            if indexed_only:
                idx_filters.append(IndexedDocument.indexing_status == "indexed")
            if folder_path:
                idx_filters.append(IndexedDocument.external_path == folder_path)
            if search_term:
                idx_filters.append(IndexedDocument.title.ilike(f"%{search_term}%"))

            # Count
            count_query = select(func.count(IndexedDocument.id))
            if idx_filters:
                count_query = count_query.where(and_(*idx_filters))
            count_result = await self.db.execute(count_query)
            idx_count = count_result.scalar() or 0
            total += idx_count

            # Get documents
            idx_query = select(IndexedDocument)
            if idx_filters:
                idx_query = idx_query.where(and_(*idx_filters))

            # Order
            order_col = getattr(IndexedDocument, order_by, IndexedDocument.created_at)
            idx_query = idx_query.order_by(order_col.desc() if order_desc else order_col.asc())

            idx_result = await self.db.execute(idx_query)
            for idx_doc in idx_result.scalars().all():
                documents.append(UnifiedDocument.from_indexed_document(idx_doc))

        # Sort combined results
        if order_by == "created_at":
            documents.sort(key=lambda d: d.created_at or datetime.min, reverse=order_desc)
        elif order_by == "title":
            documents.sort(key=lambda d: d.title or "", reverse=order_desc)
        elif order_by == "file_size":
            documents.sort(key=lambda d: d.file_size or 0, reverse=order_desc)

        # Apply pagination to combined results
        paginated = documents[offset:offset + per_page]

        return paginated, total

    async def get_recent_documents(
        self,
        limit: int = 10,
        days: int = 7,
    ) -> List[UnifiedDocument]:
        """
        Get recently created/indexed documents.

        Args:
            limit: Maximum documents to return
            days: How many days back to look

        Returns:
            List of recent documents
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        documents: List[UnifiedDocument] = []

        # From Document table
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_query = self._apply_doc_acl(
                select(Document)
                .where(Document.created_at >= cutoff)
                .order_by(Document.created_at.desc())
                .limit(limit)
            )
            doc_result = await self.db.execute(doc_query)
            for doc in doc_result.scalars().all():
                documents.append(UnifiedDocument.from_document(doc))

        # From IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_query = (
                select(IndexedDocument)
                .where(IndexedDocument.created_at >= cutoff)
                .order_by(IndexedDocument.created_at.desc())
                .limit(limit)
            )
            idx_result = await self.db.execute(idx_query)
            for idx_doc in idx_result.scalars().all():
                documents.append(UnifiedDocument.from_indexed_document(idx_doc))

        # Sort and limit
        documents.sort(key=lambda d: d.created_at or datetime.min, reverse=True)
        return documents[:limit]

    async def get_folder_stats(self) -> Dict[str, int]:
        """
        Get document counts by folder path.

        Returns:
            Dictionary mapping folder path to document count
        """
        from collections import defaultdict
        folder_counts: Dict[str, int] = defaultdict(int)

        # From Document table
        if self.source in (DocumentSource.UPLOAD, DocumentSource.BOTH):
            doc_query = (
                select(
                    Document.folder_path,
                    func.count(Document.id).label("count")
                )
                .group_by(Document.folder_path)
            )
            doc_result = await self.db.execute(doc_query)
            for row in doc_result:
                path = row.folder_path or "/"
                folder_counts[path] += row.count

        # From IndexedDocument table
        if self.source in (DocumentSource.CONNECTOR, DocumentSource.BOTH):
            idx_query = (
                select(
                    IndexedDocument.external_path,
                    func.count(IndexedDocument.id).label("count")
                )
                .group_by(IndexedDocument.external_path)
            )
            idx_result = await self.db.execute(idx_query)
            for row in idx_result:
                path = row.external_path or "/"
                folder_counts[path] += row.count

        return dict(folder_counts)


# Convenience function for quick access
async def get_unified_document_count(
    db: AsyncSession,
    user: Optional[UserProfile] = None,
) -> int:
    """Quick helper to get total document count."""
    query = UnifiedDocumentQuery(db, user)
    counts = await query.count_documents()
    return counts["total"]


async def get_unified_document(
    db: AsyncSession,
    document_id: Union[str, UUID],
    user: Optional[UserProfile] = None,
) -> Optional[UnifiedDocument]:
    """Quick helper to get a document by ID."""
    query = UnifiedDocumentQuery(db, user)
    return await query.get_document_by_id(document_id)
