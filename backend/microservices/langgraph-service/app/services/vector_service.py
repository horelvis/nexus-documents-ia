"""
Vector Service - Handles vector storage and similarity search
"""
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, 
    VectorParams, 
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)
from loguru import logger
import uuid
from datetime import datetime


class VectorService:
    """Service for vector storage and retrieval using Qdrant"""
    
    def __init__(self, tenant_id: str, qdrant_client: QdrantClient, embeddings):
        self.tenant_id = tenant_id
        self.client = qdrant_client
        self.embeddings = embeddings
        # Sanitize tenant_id for collection name - replace : with _
        sanitized_tenant_id = tenant_id.replace(":", "_").replace("-", "_")
        self.collection_name = f"documents_{sanitized_tenant_id}"
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure collection exists with correct configuration"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                # Get embedding dimensions
                dimensions = self._get_embedding_dimensions()
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=dimensions,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection {self.collection_name} with {dimensions} dimensions")
                
        except Exception as e:
            logger.error(f"Error ensuring collection: {e}")
            # Collection might exist but with wrong dimensions
            # We'll handle this in recreate_collection if needed
    
    def _get_embedding_dimensions(self) -> int:
        """Get the dimensions of the embedding model"""
        try:
            # Generate a test embedding to get dimensions
            if hasattr(self.embeddings, 'embed_query'):
                test_embedding = self.embeddings.embed_query("test")
            else:
                # For async embeddings
                import asyncio
                loop = asyncio.new_event_loop()
                test_embedding = loop.run_until_complete(
                    self.embeddings.aembed_query("test")
                )
            
            return len(test_embedding)
            
        except Exception as e:
            logger.warning(f"Could not determine embedding dimensions: {e}")
            # Default to common dimensions
            return 384  # Default for all-MiniLM-L6-v2
    
    async def add_documents(
        self,
        doc_id: str,
        texts: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> bool:
        """Add multiple documents with embeddings to vector store"""
        try:
            # Generate embeddings
            if hasattr(self.embeddings, 'aembed_documents'):
                embeddings = await self.embeddings.aembed_documents(texts)
            else:
                import asyncio
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None,
                    self.embeddings.embed_documents,
                    texts
                )
            
            # Create points for Qdrant
            points = []
            for i, (text, embedding, metadata) in enumerate(zip(texts, embeddings, metadatas)):
                point_id = str(uuid.uuid4())
                
                # Prepare payload
                payload = {
                    "doc_id": doc_id,
                    "text": text,
                    "tenant_id": self.tenant_id,
                    "chunk_index": i,
                    "created_at": datetime.utcnow().isoformat(),
                    **metadata
                }
                
                points.append(PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                ))
            
            # Upsert to Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"Added {len(points)} chunks for document {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding documents: {e}")
            return False
    
    async def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any] = {}
    ) -> bool:
        """Add single document with embedding to vector store"""
        return await self.add_documents(doc_id, [text], [metadata])
    
    async def search_similar(
        self,
        query: str,
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar documents by query"""
        try:
            # Generate query embedding
            if hasattr(self.embeddings, 'aembed_query'):
                query_embedding = await self.embeddings.aembed_query(query)
            else:
                import asyncio
                loop = asyncio.get_event_loop()
                query_embedding = await loop.run_in_executor(
                    None,
                    self.embeddings.embed_query,
                    query
                )
            
            # Build Qdrant filter if provided
            qdrant_filter = None
            if filters:
                conditions = []
                for key, value in filters.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                qdrant_filter = Filter(must=conditions)
            
            # Search in Qdrant
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=qdrant_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            # Format results
            results = []
            for point in search_result:
                result = {
                    "score": point.score,
                    "doc_id": point.payload.get("doc_id"),
                    "text": point.payload.get("text"),
                    "metadata": {
                        k: v for k, v in point.payload.items()
                        if k not in ["doc_id", "text", "tenant_id"]
                    }
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar documents: {e}")
            return []
    
    async def search_by_document_ids(
        self,
        doc_ids: List[str],
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search within specific documents"""
        filters = {"doc_id": {"$in": doc_ids}}
        return await self.search_similar(query, limit, filters)
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete all vectors for a document"""
        try:
            # Delete by filter
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )
            
            logger.info(f"Deleted vectors for document {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection"""
        try:
            info = self.client.get_collection(self.collection_name)
            
            return {
                "collection_name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
                "config": {
                    "vector_size": info.config.params.vectors.size,
                    "distance": info.config.params.vectors.distance
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {
                "error": str(e),
                "collection_name": self.collection_name
            }
    
    async def recreate_collection(self) -> bool:
        """Recreate collection with correct dimensions"""
        try:
            # Delete existing collection
            try:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing collection {self.collection_name}")
            except Exception:
                pass  # Collection might not exist
            
            # Get correct dimensions
            dimensions = self._get_embedding_dimensions()
            
            # Create new collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE
                )
            )
            
            logger.info(f"Recreated collection {self.collection_name} with {dimensions} dimensions")
            return True
            
        except Exception as e:
            logger.error(f"Error recreating collection: {e}")
            return False
    
    async def check_health(self) -> Dict[str, Any]:
        """Check collection health and configuration"""
        try:
            info = await self.get_collection_info()
            
            if "error" in info:
                return {
                    "status": "error",
                    "error": info["error"]
                }
            
            # Get expected dimensions
            expected_dimensions = self._get_embedding_dimensions()
            actual_dimensions = info["config"]["vector_size"]
            
            return {
                "collection_name": self.collection_name,
                "collection_exists": True,
                "current_dimensions": actual_dimensions,
                "required_dimensions": expected_dimensions,
                "dimensions_match": actual_dimensions == expected_dimensions,
                "vectors_count": info["vectors_count"],
                "status": "healthy" if actual_dimensions == expected_dimensions else "dimension_mismatch"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "collection_name": self.collection_name
            }