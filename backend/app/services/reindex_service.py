"""
Reindexing Service - Automatically reindex documents when collection is recreated
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.config import settings
from app.db.models import Document
from app.db.database import SessionLocal
from app.schemas.enums import IndexingStatus
from app.services.document_service import DocumentService
from app.services.vector_service import VectorService
from app.services.storage_factory import StorageServiceFactory

logger = logging.getLogger(__name__)


class ReindexService:
    """Service for managing document reindexing operations"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.user_id = user_id
        self.vector_service = VectorService(tenant_id=self.tenant_id, user_id=self.user_id)
        self.storage_service = StorageServiceFactory.create_storage_service(
            tenant_id=self.tenant_id,
            user_id=self.user_id
        )
        logger.info(f"ReindexService initialized for tenant: {self.tenant_id}")
    
    async def get_documents_needing_reindex(self, db: Session) -> List[Document]:
        """
        Find documents that are marked as INDEXED but don't exist in vector store.
        
        Args:
            db: Database session
            
        Returns:
            List of documents that need reindexing
        """
        try:
            # Get all documents marked as indexed for this tenant
            indexed_documents = db.query(Document).filter(
                and_(
                    Document.tenant_id == self.tenant_id,
                    Document.indexed == IndexingStatus.INDEXED
                )
            ).all()
            
            logger.info(f"Found {len(indexed_documents)} documents marked as INDEXED")
            
            # Check which ones are missing from vector store
            documents_needing_reindex = []
            
            for doc in indexed_documents:
                # Try to search for this specific document in vector store
                results = await self.vector_service.search_by_document_ids(
                    doc_ids=[str(doc.id)],
                    query=doc.title or doc.filename,
                    limit=1
                )
                
                # If no results found, document needs reindexing
                if not results:
                    documents_needing_reindex.append(doc)
                    logger.debug(f"Document {doc.id} ({doc.filename}) needs reindexing")
            
            logger.info(f"Found {len(documents_needing_reindex)} documents needing reindexing")
            return documents_needing_reindex
            
        except Exception as e:
            logger.error(f"Error finding documents needing reindex: {str(e)}")
            return []
    
    async def reindex_document(self, db: Session, document: Document) -> bool:
        """
        Reindex a single document.
        
        Args:
            db: Database session
            document: Document to reindex
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Reindexing document {document.id} ({document.filename})")
            
            # Set status to indexing
            document.indexed = IndexingStatus.INDEXING
            db.commit()
            
            # Download file content from storage
            file_path = document.file_path or f"{self.tenant_id}/{document.id}/{document.filename}"
            file_content = self.storage_service.download_file(file_path)
            
            if not file_content:
                logger.error(f"Could not download file content for document {document.id}")
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                return False
            
            # Create temporary document service for indexing
            doc_service = DocumentService(tenant_id=self.tenant_id, user_id=self.user_id)
            
            # Extract file extension
            file_ext = document.filename.split('.')[-1].lower() if '.' in document.filename else ''
            
            # Reindex the document
            await doc_service._extract_and_index_text(
                db=db,
                db_document=document,
                file_contents=file_content,
                file_ext=file_ext,
                title=document.title or document.filename
            )
            
            db.commit()
            
            success = document.indexed == IndexingStatus.INDEXED
            if success:
                logger.info(f"Successfully reindexed document {document.id}")
            else:
                logger.error(f"Failed to reindex document {document.id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error reindexing document {document.id}: {str(e)}")
            document.indexed = IndexingStatus.INDEXING_ERROR
            db.commit()
            return False
    
    async def reindex_all_missing(self, max_concurrent: int = 3) -> Dict[str, Any]:
        """
        Reindex all documents that are missing from vector store.
        
        Args:
            max_concurrent: Maximum number of concurrent reindexing operations
            
        Returns:
            Dictionary with reindexing results
        """
        try:
            logger.info("Starting bulk reindexing of missing documents")
            
            with SessionLocal() as db:
                documents_needing_reindex = await self.get_documents_needing_reindex(db)
                
                if not documents_needing_reindex:
                    return {
                        "total_documents": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "message": "No documents need reindexing"
                    }
                
                # Process documents in batches to avoid overwhelming the system
                semaphore = asyncio.Semaphore(max_concurrent)
                success_count = 0
                error_count = 0
                
                async def reindex_with_semaphore(doc):
                    async with semaphore:
                        # Create new DB session for each document to avoid conflicts
                        with SessionLocal() as doc_db:
                            # Refresh document in new session
                            doc_refreshed = doc_db.query(Document).filter(Document.id == doc.id).first()
                            if doc_refreshed:
                                return await self.reindex_document(doc_db, doc_refreshed)
                            return False
                
                # Start all reindexing tasks
                tasks = [reindex_with_semaphore(doc) for doc in documents_needing_reindex]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count results
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"Reindexing task failed with exception: {result}")
                    elif result:
                        success_count += 1
                    else:
                        error_count += 1
                
                logger.info(f"Bulk reindexing completed: {success_count} success, {error_count} errors")
                
                return {
                    "total_documents": len(documents_needing_reindex),
                    "success_count": success_count,
                    "error_count": error_count,
                    "message": f"Reindexed {success_count} of {len(documents_needing_reindex)} documents"
                }
                
        except Exception as e:
            logger.error(f"Error in bulk reindexing: {str(e)}")
            return {
                "total_documents": 0,
                "success_count": 0,
                "error_count": 1,
                "error": str(e)
            }
    
    async def reindex_specific_documents(self, document_ids: List[str]) -> Dict[str, Any]:
        """
        Reindex specific documents by their IDs.
        
        Args:
            document_ids: List of document IDs to reindex
            
        Returns:
            Dictionary with reindexing results
        """
        try:
            logger.info(f"Reindexing specific documents: {document_ids}")
            
            with SessionLocal() as db:
                documents = db.query(Document).filter(
                    and_(
                        Document.id.in_(document_ids),
                        Document.tenant_id == self.tenant_id
                    )
                ).all()
                
                if not documents:
                    return {
                        "total_documents": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "message": "No valid documents found for reindexing"
                    }
                
                success_count = 0
                error_count = 0
                
                for doc in documents:
                    try:
                        success = await self.reindex_document(db, doc)
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                    except Exception as e:
                        logger.error(f"Error reindexing document {doc.id}: {str(e)}")
                        error_count += 1
                
                return {
                    "total_documents": len(documents),
                    "success_count": success_count,
                    "error_count": error_count,
                    "message": f"Reindexed {success_count} of {len(documents)} documents"
                }
                
        except Exception as e:
            logger.error(f"Error in specific document reindexing: {str(e)}")
            return {
                "total_documents": 0,
                "success_count": 0,
                "error_count": 1,
                "error": str(e)
            }
    
    async def check_reindex_status(self) -> Dict[str, Any]:
        """
        Check the current reindexing status for the tenant.
        
        Returns:
            Dictionary with status information
        """
        try:
            with SessionLocal() as db:
                # Count documents by indexing status
                total_docs = db.query(Document).filter(Document.tenant_id == self.tenant_id).count()
                indexed_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.INDEXED
                    )
                ).count()
                indexing_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.INDEXING
                    )
                ).count()
                error_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.INDEXING_ERROR
                    )
                ).count()
                pending_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.PENDING
                    )
                ).count()
                
                # Check for missing documents in vector store
                documents_needing_reindex = await self.get_documents_needing_reindex(db)
                missing_from_vector_store = len(documents_needing_reindex)
                
                return {
                    "tenant_id": self.tenant_id,
                    "total_documents": total_docs,
                    "indexed_documents": indexed_docs,
                    "indexing_documents": indexing_docs,
                    "error_documents": error_docs,
                    "pending_documents": pending_docs,
                    "missing_from_vector_store": missing_from_vector_store,
                    "needs_reindexing": missing_from_vector_store > 0,
                    "vector_store_health": {
                        "collection_exists": True,  # Will be updated by vector service health check
                        "dimensions_correct": True  # Will be updated by vector service health check
                    }
                }
                
        except Exception as e:
            logger.error(f"Error checking reindex status: {str(e)}")
            return {
                "error": str(e),
                "tenant_id": self.tenant_id
            }