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
        Find documents that need reindexing:
        1. Documents marked as INDEXED but missing from vector store
        2. Documents marked as INDEXING_ERROR
        
        Args:
            db: Database session
            
        Returns:
            List of documents that need reindexing
        """
        try:
            documents_needing_reindex = []

            # 1. Get documents in ERROR state
            error_documents = db.query(Document).filter(
                and_(
                    Document.tenant_id == self.tenant_id,
                    Document.indexed == IndexingStatus.INDEXING_ERROR
                )
            ).all()
            documents_needing_reindex.extend(error_documents)

            # 2. Get documents marked as INDEXED
            indexed_documents = db.query(Document).filter(
                and_(
                    Document.tenant_id == self.tenant_id,
                    Document.indexed == IndexingStatus.INDEXED
                )
            ).all()
            
            logger.info(f"Found {len(error_documents)} ERROR docs and {len(indexed_documents)} INDEXED docs")
            
            # Check which INDEXED ones are missing from vector store
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
                    logger.debug(f"Document {doc.id} ({doc.filename}) missing from vector store")
            
            logger.info(f"Found {len(documents_needing_reindex)} total documents needing reindexing")
            return documents_needing_reindex
            
        except Exception as e:
            logger.error(f"Error finding documents needing reindex: {str(e)}")
            return []
    
    async def reindex_document(self, db: Session, document: Document) -> bool:
        """
        Reindex a single document with enhanced error handling.
        
        Args:
            db: Database session
            document: Document to reindex
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Starting reindex for document {document.id} ({document.filename})")
            
            # IMPORTANT: Don't set status to INDEXING immediately to avoid potential enum issues
            # We'll set it only when we're about to start processing
            
            # First, validate the document exists and has required fields
            if not document.filename:
                logger.error(f"Document {document.id} has no filename")
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                return False
            
            # Download file content from storage
            file_path = document.file_path or f"{self.tenant_id}/{document.id}/{document.filename}"
            logger.info(f"Attempting to download file from path: {file_path}")
            
            try:
                file_content = self.storage_service.download_file(file_path)
                if file_content:
                    logger.info(f"File content downloaded successfully, size: {len(file_content)} bytes")
                else:
                    logger.error(f"Downloaded file content is empty for document {document.id}")
                    document.indexed = IndexingStatus.INDEXING_ERROR
                    db.commit()
                    return False
            except Exception as download_e:
                logger.error(f"Failed to download file for document {document.id}: {type(download_e).__name__}: {str(download_e)}")
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                return False
            
            # Now set status to processing since we have the file content
            logger.info(f"Setting document {document.id} status to PROCESSING")
            document.indexed = IndexingStatus.PROCESSING
            db.commit()
            
            # Extract file extension
            file_ext = document.filename.split('.')[-1].lower() if '.' in document.filename else ''
            logger.info(f"Processing document {document.id} with extension: {file_ext}")
            
            # Use a simplified approach for reindexing
            try:
                # Create a fresh document service instance
                from app.services.document_service import DocumentService
                doc_service = DocumentService(tenant_id=self.tenant_id, user_id=self.user_id)
                
                logger.info(f"Starting text extraction for document {document.id}")
                
                # Call the extraction and indexing method with proper error handling
                await doc_service._extract_and_index_text(
                    db=db,
                    db_document=document,
                    file_contents=file_content,
                    file_ext=file_ext,
                    title=document.title or document.filename
                )
                
                logger.info(f"Text extraction completed for document {document.id}")
                
            except Exception as processing_error:
                error_msg = f"Processing failed for document {document.id}: {type(processing_error).__name__}: {str(processing_error)}"
                logger.error(error_msg)
                
                # Log the full traceback for debugging
                import traceback
                logger.error(f"Full traceback for document {document.id}: {traceback.format_exc()}")
                
                # Set error status and return
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
                return False
            
            # Commit any changes made during processing
            db.commit()
            
            # Check final status
            success = document.indexed == IndexingStatus.INDEXED
            if success:
                logger.info(f"✅ Successfully reindexed document {document.id}")
            else:
                logger.error(f"❌ Reindexing failed for document {document.id} - final status: {document.indexed}")
                
            return success
            
        except Exception as e:
            error_msg = f"Unexpected error reindexing document {document.id}: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            
            # Log full traceback
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Ensure document is marked as error
            try:
                document.indexed = IndexingStatus.INDEXING_ERROR
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update document status after error: {commit_error}")
                
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

    async def reindex_all_force(self, max_concurrent: int = 3) -> Dict[str, Any]:
        """
        Force reindex ALL documents for the tenant, regardless of their status.
        
        Args:
            max_concurrent: Maximum number of concurrent reindexing operations
            
        Returns:
            Dictionary with reindexing results
        """
        try:
            logger.info(f"Starting FORCED bulk reindexing for tenant {self.tenant_id}")
            
            with SessionLocal() as db:
                # Get ALL documents for this tenant
                all_documents = db.query(Document).filter(
                    Document.tenant_id == self.tenant_id
                ).all()
                
                if not all_documents:
                    return {
                        "total_documents": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "message": "No documents found to reindex"
                    }
                
                logger.info(f"Found {len(all_documents)} documents to force reindex")
                
                # Process documents in batches
                semaphore = asyncio.Semaphore(max_concurrent)
                success_count = 0
                error_count = 0
                
                async def reindex_with_semaphore(doc):
                    async with semaphore:
                        # Create new DB session for each document
                        with SessionLocal() as doc_db:
                            # Refresh document
                            doc_refreshed = doc_db.query(Document).filter(Document.id == doc.id).first()
                            if doc_refreshed:
                                return await self.reindex_document(doc_db, doc_refreshed)
                            return False
                
                # Start all tasks
                tasks = [reindex_with_semaphore(doc) for doc in all_documents]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count results
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"Reindexing task failed: {result}")
                    elif result:
                        success_count += 1
                    else:
                        error_count += 1
                
                logger.info(f"Forced reindexing completed: {success_count} success, {error_count} errors")
                
                return {
                    "total_documents": len(all_documents),
                    "success_count": success_count,
                    "error_count": error_count,
                    "message": f"Force reindexed {success_count} of {len(all_documents)} documents"
                }
                
        except Exception as e:
            logger.error(f"Error in force reindexing: {str(e)}")
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
                processing_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.PROCESSING
                    )
                ).count()
                error_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.INDEXING_ERROR
                    )
                ).count()
                not_indexed_docs = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.NOT_INDEXED
                    )
                ).count()
                
                # Check for missing documents in vector store
                documents_needing_reindex = await self.get_documents_needing_reindex(db)
                missing_from_vector_store = len(documents_needing_reindex)
                
                return {
                    "tenant_id": self.tenant_id,
                    "total_documents": total_docs,
                    "indexed_documents": indexed_docs,
                    "processing_documents": processing_docs,
                    "error_documents": error_docs,
                    "not_indexed_documents": not_indexed_docs,
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
    
    async def auto_reindex_failed_documents(self) -> Dict[str, Any]:
        """
        Automatically reindex documents that have been in INDEXING_ERROR state.
        This method is meant to be called periodically by a background task.
        
        Returns:
            Dictionary with auto-reindex results
        """
        try:
            logger.info(f"Starting auto-reindex for tenant {self.tenant_id}")
            
            with SessionLocal() as db:
                # Find documents that have been in error state
                error_documents = db.query(Document).filter(
                    and_(
                        Document.tenant_id == self.tenant_id,
                        Document.indexed == IndexingStatus.INDEXING_ERROR
                    )
                ).all()
                
                if not error_documents:
                    logger.info(f"No documents in error state for tenant {self.tenant_id}")
                    return {
                        "total_documents": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "message": "No documents needed auto-reindexing"
                    }
                
                logger.info(f"Found {len(error_documents)} documents in error state for auto-reindexing")
                
                success_count = 0
                error_count = 0
                
                # Process each document
                for doc in error_documents:
                    try:
                        # Use existing reindex method
                        success = await self.reindex_document(db, doc)
                        if success:
                            success_count += 1
                            logger.info(f"Auto-reindexed document {doc.id} successfully")
                        else:
                            error_count += 1
                            logger.warning(f"Failed to auto-reindex document {doc.id}")
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Exception during auto-reindex of document {doc.id}: {str(e)}")
                
                result = {
                    "total_documents": len(error_documents),
                    "success_count": success_count,
                    "error_count": error_count,
                    "message": f"Auto-reindexed {success_count} of {len(error_documents)} error documents"
                }
                
                logger.info(f"Auto-reindex completed for tenant {self.tenant_id}: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Error in auto-reindex for tenant {self.tenant_id}: {str(e)}")
            return {
                "total_documents": 0,
                "success_count": 0,
                "error_count": 1,
                "error": str(e)
            }