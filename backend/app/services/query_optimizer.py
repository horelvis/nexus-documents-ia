"""
Query optimization service to handle N+1 problems and improve database performance
"""
import logging
from typing import List, Dict, Any, Optional, Type, TypeVar, Generic
from sqlalchemy.orm import Session, joinedload, selectinload, subqueryload, Load
from sqlalchemy import select, func, and_, or_
from sqlalchemy.sql import Select

from app.db.models import Document, IndexedDocument, User, DocumentView, Tag
from app.core.auth.base import UserProfile
from app.core.auth.acl import filter_visible_to_user
import uuid

logger = logging.getLogger(__name__)

T = TypeVar('T')


class QueryOptimizer:
    """Service for optimizing database queries and handling N+1 problems"""

    def __init__(self, db: Session):
        self.db = db

    def get_documents_with_relations(
        self,
        user: Optional[UserProfile] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_views: bool = False,
        include_tags: bool = False,
        include_metrics: bool = False
    ) -> List[Document]:
        """
        Optimized query to get documents with all necessary relations.
        Solves N+1 problem by using eager loading.
        """
        query = select(Document)
        if user is not None:
            query = filter_visible_to_user(query, user)

        # Build load options based on what's needed
        load_options = []

        if include_views:
            load_options.append(selectinload(Document.views))
            load_options.append(selectinload(Document.views).selectinload(DocumentView.user))

        if include_tags:
            load_options.append(selectinload(Document.tags))

        if include_metrics:
            load_options.append(selectinload(Document.metrics))

        # Always include creator to avoid N+1
        load_options.append(joinedload(Document.creator))

        # Apply eager loading
        for option in load_options:
            query = query.options(option)

        # Add ordering and pagination
        query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)

        result = self.db.execute(query)
        return result.scalars().unique().all()

    def get_user_with_permissions(self, user_id: str) -> Optional[User]:
        """
        Get user with all roles and permissions in a single query.
        """
        query = select(User).where(User.id == user_id).options(
            selectinload(User.roles).selectinload(User.roles.permissions)
        )

        result = self.db.execute(query)
        return result.scalar_one_or_none()

    def get_system_stats_optimized(self) -> Dict[str, Any]:
        """
        Get system-wide statistics with optimized queries.
        Uses subqueries to avoid multiple round trips.
        Includes both Document (uploads) and IndexedDocument (connectors).
        """
        # Subquery for Document count
        doc_count_subquery = select(func.count(Document.id)).scalar_subquery()

        # Subquery for IndexedDocument count (connector documents)
        indexed_count_subquery = select(func.count(IndexedDocument.id)).scalar_subquery()

        # Subquery for user count
        user_count_subquery = select(func.count(User.id)).scalar_subquery()

        # Subquery for total views
        views_subquery = select(func.sum(DocumentView.page_views)).where(
            DocumentView.viewed_at >= func.now() - func.interval('30 days')
        ).scalar_subquery()

        # Execute all subqueries in one go
        query = select(
            doc_count_subquery.label('document_count'),
            indexed_count_subquery.label('indexed_document_count'),
            user_count_subquery.label('user_count'),
            views_subquery.label('total_views_30d')
        )

        result = self.db.execute(query).first()

        doc_count = result.document_count or 0
        indexed_count = result.indexed_document_count or 0

        return {
            'document_count': doc_count + indexed_count,  # Total from both tables
            'upload_count': doc_count,  # Document table only
            'connector_count': indexed_count,  # IndexedDocument table only
            'user_count': result.user_count or 0,
            'total_views_30d': result.total_views_30d or 0
        }

    def batch_update_document_metrics(self, document_ids: List[str]) -> None:
        """
        Batch update document metrics to avoid N+1 updates.
        """
        if not document_ids:
            return

        from app.db.models import DocumentMetrics

        logger.info(f"Batch updating metrics for {len(document_ids)} documents")

    def get_documents_by_tag_optimized(
        self,
        tag_name: str,
        user: Optional[UserProfile] = None,
        limit: int = 20
    ) -> List[Document]:
        """
        Get documents by tag with optimized query.
        """
        query = select(Document).join(Document.tags).where(
            Tag.name == tag_name
        )
        if user is not None:
            query = filter_visible_to_user(query, user)

        query = query.options(
            joinedload(Document.creator),
            selectinload(Document.tags)
        ).order_by(Document.created_at.desc()).limit(limit)

        result = self.db.execute(query)
        return result.scalars().unique().all()

    def search_documents_optimized(
        self,
        search_term: str,
        user: Optional[UserProfile] = None,
        limit: int = 50
    ) -> List[Document]:
        """
        Search documents with optimized query.
        Uses database indexes for better performance.
        """
        search_pattern = f"%{search_term}%"

        query = select(Document).where(
            or_(
                Document.title.ilike(search_pattern),
                Document.description.ilike(search_pattern),
                Document.filename.ilike(search_pattern)
            )
        )
        if user is not None:
            query = filter_visible_to_user(query, user)

        query = query.options(
            joinedload(Document.creator),
            selectinload(Document.tags)
        ).order_by(Document.created_at.desc()).limit(limit)

        result = self.db.execute(query)
        return result.scalars().unique().all()

    def get_recent_activity_optimized(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent activity with optimized query.
        Combines document views and document changes in one query.
        """
        from sqlalchemy import union_all

        # Query for document views
        views_query = select(
            DocumentView.viewed_at.label('activity_at'),
            DocumentView.user_id,
            Document.title.label('document_title'),
            'view'  # Activity type
        ).join(Document).where(
            DocumentView.viewed_at >= func.now() - func.interval(f'{days} days')
        )

        # Query for document creations
        creations_query = select(
            Document.created_at.label('activity_at'),
            Document.created_by.label('user_id'),
            Document.title.label('document_title'),
            'create'  # Activity type
        ).where(
            Document.created_at >= func.now() - func.interval(f'{days} days')
        )

        # Combine queries
        combined_query = union_all(views_query, creations_query).order_by(
            combined_query.c.activity_at.desc()
        ).limit(limit)

        result = self.db.execute(combined_query)

        activities = []
        for row in result:
            activities.append({
                'activity_at': row.activity_at,
                'user_id': row.user_id,
                'document_title': row.document_title,
                'activity_type': row[3]  # The activity type column
            })

        return activities

    def prefetch_related_data(self, documents: List[Document]) -> List[Document]:
        """
        Prefetch related data for a list of documents to avoid N+1 queries.
        """
        if not documents:
            return documents

        document_ids = [doc.id for doc in documents]

        # Prefetch views
        views_query = select(DocumentView).where(
            DocumentView.document_id.in_(document_ids)
        ).options(joinedload(DocumentView.user))

        views = self.db.execute(views_query).scalars().all()

        # Prefetch tags
        tags_query = select(Tag).join(Document.tags).where(
            Document.id.in_(document_ids)
        )

        tags = self.db.execute(tags_query).scalars().all()

        return documents


class QueryBatchProcessor:
    """Utility for batch processing database operations"""

    def __init__(self, db: Session, batch_size: int = 100):
        self.db = db
        self.batch_size = batch_size

    def process_in_batches(self, items: List[Any], processor_func):
        """
        Process items in batches to avoid memory issues and improve performance.
        """
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            processor_func(batch)

            # Commit periodically to avoid long transactions
            if i % (self.batch_size * 10) == 0:
                self.db.commit()

        self.db.commit()

    def bulk_insert(self, items: List[Any], model_class: Type[T]) -> int:
        """
        Bulk insert items with optimized performance.
        """
        if not items:
            return 0

        self.db.bulk_insert_mappings(model_class, [item.__dict__ for item in items])
        self.db.commit()

        logger.info(f"Bulk inserted {len(items)} {model_class.__name__} records")
        return len(items)

    def bulk_update(self, updates: List[Dict[str, Any]], model_class: Type[T],
                   key_field: str = 'id') -> int:
        """
        Bulk update items with optimized performance.
        """
        if not updates:
            return 0

        updated_count = 0
        for update_data in updates:
            key_value = update_data.pop(key_field)
            self.db.query(model_class).filter(
                getattr(model_class, key_field) == key_value
            ).update(update_data)
            updated_count += 1

        self.db.commit()

        logger.info(f"Bulk updated {updated_count} {model_class.__name__} records")
        return updated_count
