"""
Direct Vector Service using Qdrant client
"""
import logging
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.core.config import settings
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class VectorServiceDirect:
    """Direct service for vector operations using Qdrant"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.user_id = user_id
        self.collection_name = f"tenant_{self.tenant_id}_documents"
        self.client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        self.embedding_service = EmbeddingService(tenant_id=self.tenant_id)
        logger.info(f"VectorServiceDirect initialized for tenant: {self.tenant_id}")
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure the collection exists in Qdrant"""
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
                )
                logger.info(f"Collection {self.collection_name} created")
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
    
    async def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a single document to vector store
        
        Args:
            doc_id: Document ID
            text: Document text
            metadata: Optional metadata
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"Adding document {doc_id} to vector store")
            
            # Generate embedding
            embedding = await self.embedding_service.get_embedding(text)
            
            if not embedding:
                logger.error(f"Failed to generate embedding for document {doc_id}")
                return False
            
            # Create point
            point = PointStruct(
                id=doc_id,
                vector=embedding,
                payload={
                    "doc_id": doc_id,
                    "tenant_id": self.tenant_id,
                    "text": text[:1000],  # Store first 1000 chars
                    **(metadata or {})
                }
            )
            
            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.info(f"Successfully added document {doc_id} to vector store")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {e}")
            return False
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents
        
        Args:
            query: Search query
            limit: Number of results
            filter_dict: Optional filters
            
        Returns:
            List of search results
        """
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.get_embedding(query)
            
            if not query_embedding:
                logger.error("Failed to generate query embedding")
                return []
            
            # Search in Qdrant
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit
            )
            
            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "doc_id": result.payload.get("doc_id"),
                    "score": result.score,
                    "text": result.payload.get("text"),
                    "metadata": result.payload
                })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            return []
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from vector store
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if successful
        """
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[doc_id]
            )
            logger.info(f"Deleted document {doc_id} from vector store")
            return True
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False