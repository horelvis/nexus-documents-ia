"""Weaviate service implementation"""
import weaviate
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from app.core.config import settings
from app.core.security import get_tenant_collection_name
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery
)
from weaviate.exceptions import UnexpectedStatusCodeException

logger = logging.getLogger(__name__)


class WeaviateService:
    """Service for Weaviate operations"""
    
    def __init__(self):
        self.client = None
        self.embedding_model = None
        
    async def initialize(self):
        """Initialize Weaviate client and embeddings"""
        try:
            # Initialize Weaviate client v4 syntax - always use local (not WCD)
            # Parse host and port from URL
            url_without_protocol = settings.weaviate_url.replace("http://", "").replace("https://", "")
            if ":" in url_without_protocol:
                host = url_without_protocol.split(":")[0]
                port = int(url_without_protocol.split(":")[1])
            else:
                host = url_without_protocol
                port = 8080
            
            # Always connect to local Weaviate (no WCD)
            self.client = weaviate.connect_to_local(
                host=host,
                port=port
            )
            
            # Test connection
            if self.client.is_ready():
                logger.info(f"✅ Connected to Weaviate at {settings.weaviate_url}")
            else:
                raise Exception("Weaviate not ready")
                
            # Initialize embedding model using Ollama
            try:
                import httpx
                # Test Ollama connection and embedding model
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.ollama_base_url}/api/embeddings",
                        json={
                            "model": settings.embedding_model,
                            "prompt": "test"
                        }
                    )
                    if response.status_code == 200:
                        self.embedding_model = "ollama"
                        logger.info(f"✅ Loaded embedding model from Ollama: {settings.embedding_model}")
                    else:
                        logger.warning(f"⚠️ Ollama embedding model not available: {settings.embedding_model}")
                        self.embedding_model = None
            except Exception as e:
                logger.warning(f"⚠️ Could not connect to Ollama for embeddings: {e}")
                self.embedding_model = None
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Weaviate: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup connections"""
        if self.client:
            # Weaviate client doesn't need explicit cleanup
            self.client = None
            logger.info("✅ Weaviate client cleaned up")
    
    async def create_collection(self, collection_name: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new Weaviate collection"""
        try:
            # Default schema for document collections
            if not schema:
                schema = {
                    "class": collection_name,
                    "description": f"Collection for documents: {collection_name}",
                    "properties": [
                        {
                            "name": "title",
                            "dataType": ["text"],
                            "description": "Document title"
                        },
                        {
                            "name": "content", 
                            "dataType": ["text"],
                            "description": "Document content"
                        },
                        {
                            "name": "metadata",
                            "dataType": ["object"],
                            "description": "Document metadata"
                        },
                        {
                            "name": "tenant_id",
                            "dataType": ["text"],
                            "description": "Tenant identifier"
                        },
                        {
                            "name": "document_type",
                            "dataType": ["text"],
                            "description": "Type of document"
                        },
                        {
                            "name": "tags",
                            "dataType": ["text[]"],
                            "description": "Document tags"
                        },
                        {
                            "name": "created_at",
                            "dataType": ["date"],
                            "description": "Creation timestamp"
                        },
                        {
                            "name": "updated_at",
                            "dataType": ["date"],
                            "description": "Last update timestamp"
                        }
                    ],
                    "vectorizer": "text2vec-transformers" if not self.embedding_model else "none"
                }
            
            # Create the collection using v4 API - simplified approach
            collection = self.client.collections.create(
                name=collection_name,
                description=schema.get("description", f"Collection for documents: {collection_name}"),
                properties=[
                    weaviate.classes.config.Property(
                        name="title",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document title"
                    ),
                    weaviate.classes.config.Property(
                        name="content", 
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Document content"
                    ),
                    weaviate.classes.config.Property(
                        name="document_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="PostgreSQL document ID"
                    ),
                    weaviate.classes.config.Property(
                        name="tenant_id",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Tenant identifier"
                    ),
                    weaviate.classes.config.Property(
                        name="document_type",
                        data_type=weaviate.classes.config.DataType.TEXT,
                        description="Type of document"
                    ),
                    weaviate.classes.config.Property(
                        name="tags",
                        data_type=weaviate.classes.config.DataType.TEXT_ARRAY,
                        description="Document tags"
                    ),
                    weaviate.classes.config.Property(
                        name="created_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Creation timestamp"
                    ),
                    weaviate.classes.config.Property(
                        name="updated_at",
                        data_type=weaviate.classes.config.DataType.DATE,
                        description="Last update timestamp"
                    )
                ]
                # Default vector configuration will be used automatically
            )
            result = {"class": collection_name, "status": "created"}
            logger.info(f"✅ Created collection: {collection_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to create collection {collection_name}: {e}")
            raise
    
    async def ensure_collection_exists(self, collection_name: str) -> bool:
        """Ensure that a collection exists, create it if it doesn't"""
        try:
            # Check if collection exists
            collections = await self.list_collections()
            if collection_name in collections or collection_name.capitalize() in collections:
                logger.info(f"✅ Collection {collection_name} already exists")
                return True
            
            # Create the collection if it doesn't exist
            logger.info(f"🔧 Creating collection: {collection_name}")
            await self.create_collection(collection_name)
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to ensure collection {collection_name} exists: {e}")
            return False
    
    async def add_document(self, collection_name: str, document: DocumentCreate) -> DocumentResponse:
        """Add a document to Weaviate"""
        try:
            # Ensure collection exists before adding document
            if not await self.ensure_collection_exists(collection_name):
                raise Exception(f"Could not create or access collection: {collection_name}")
            
            # Generate ID if not provided
            doc_id = document.id or str(uuid.uuid4())
            
            # Prepare document data (removed metadata for now - no nested object schema)
            doc_data = {
                "title": document.title,
                "content": document.content,
                "document_id": doc_id,  # Store PostgreSQL document ID as property
                "tenant_id": document.tenant_id,
                "document_type": document.document_type,
                "tags": document.tags,
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "updated_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }
            
            # Get collection and add document using v4 API
            collection = self.client.collections.get(collection_name)
            
            # Generate embedding via Ollama if available
            if self.embedding_model:
                try:
                    import httpx
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.post(
                            f"{settings.ollama_base_url}/api/embeddings",
                            json={
                                "model": settings.embedding_model,
                                "prompt": f"{document.title} {document.content}"
                            },
                            timeout=30.0
                        )
                        if response.status_code == 200:
                            embedding_data = response.json()
                            embedding_vector = embedding_data.get("embedding", [])
                            if embedding_vector:
                                logger.info(f"🧮 Generated embedding vector of size {len(embedding_vector)}")
                            else:
                                logger.warning("⚠️ Empty embedding vector returned from Ollama")
                        else:
                            logger.warning(f"⚠️ Ollama embeddings failed: {response.status_code}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not generate embedding via Ollama: {e}")
            
            # Insert document; if it exists already, replace it
            try:
                result = collection.data.insert(
                    properties=doc_data,
                    uuid=doc_id
                )
                logger.info(f"✅ Inserted document {doc_id} to {collection_name}")
            except UnexpectedStatusCodeException as exc:
                if exc.status_code == 422 and "already exists" in str(exc):
                    logger.info(f"♻️ Document {doc_id} already exists in {collection_name}, replacing")
                    result = collection.data.replace(
                        properties=doc_data,
                        uuid=doc_id
                    )
                    logger.info(f"✅ Replaced document {doc_id} in {collection_name}")
                else:
                    raise
            
            vector_identifier = doc_id
            if result is not None:
                try:
                    vector_identifier = str(result)
                except Exception:
                    vector_identifier = doc_id
            
            return DocumentResponse(
                id=doc_id,
                title=document.title,
                content=document.content,
                metadata={},  # Empty for now
                tenant_id=document.tenant_id,
                document_type=document.document_type,
                tags=document.tags,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                vector_id=vector_identifier
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to add document to {collection_name}: {e}")
            raise
    
    async def search_documents(self, collection_name: str, search_request: SearchRequest) -> SearchResponse:
        """Search documents in Weaviate"""
        try:
            start_time = datetime.now()
            
            # Get collection for search using v4 API
            collection = self.client.collections.get(collection_name)
            
            # Build filters for tenant isolation using v4 API
            tenant_filter = weaviate.classes.query.Filter.by_property("tenant_id").equal(search_request.tenant_id)
            
            # Add additional filters if provided
            combined_filters = tenant_filter
            if search_request.filters:
                for key, value in search_request.filters.items():
                    additional_filter = weaviate.classes.query.Filter.by_property(key).equal(str(value))
                    combined_filters = combined_filters & additional_filter
            
            # Execute search based on type using v4 API
            if search_request.search_type == "vector":
                # Generate embedding for query using Ollama
                query_embedding = None
                if self.embedding_model:
                    try:
                        import httpx
                        async with httpx.AsyncClient() as http_client:
                            response_embed = await http_client.post(
                                f"{settings.ollama_base_url}/api/embeddings",
                                json={
                                    "model": settings.embedding_model,
                                    "prompt": search_request.query
                                },
                                timeout=30.0
                            )
                            if response_embed.status_code == 200:
                                embedding_data = response_embed.json()
                                query_embedding = embedding_data.get("embedding", [])
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate query embedding: {e}")
                
                if query_embedding:
                    # Vector search with near_vector using generated embedding
                    response = collection.query.near_vector(
                        near_vector=query_embedding,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(certainty=True, score=True),
                        filters=combined_filters
                    )
                else:
                    # Fall back to BM25 keyword search if no embeddings available
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters
                    )
            elif search_request.search_type == "keyword":
                # BM25 keyword search
                response = collection.query.bm25(
                    query=search_request.query,
                    limit=search_request.limit,
                    return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                    filters=combined_filters
                )
            else:  # hybrid
                # Hybrid search requires both vector and keyword
                query_embedding = None
                if self.embedding_model:
                    try:
                        import httpx
                        async with httpx.AsyncClient() as http_client:
                            response_embed = await http_client.post(
                                f"{settings.ollama_base_url}/api/embeddings",
                                json={
                                    "model": settings.embedding_model,
                                    "prompt": search_request.query
                                },
                                timeout=30.0
                            )
                            if response_embed.status_code == 200:
                                embedding_data = response_embed.json()
                                query_embedding = embedding_data.get("embedding", [])
                    except Exception as e:
                        logger.warning(f"⚠️ Could not generate query embedding for hybrid: {e}")
                
                if query_embedding:
                    response = collection.query.hybrid(
                        query=search_request.query,
                        vector=query_embedding,
                        limit=search_request.limit,
                        alpha=0.7,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True, explain_score=True),
                        filters=combined_filters
                    )
                else:
                    # Fall back to BM25 if no embeddings
                    response = collection.query.bm25(
                        query=search_request.query,
                        limit=search_request.limit,
                        return_metadata=weaviate.classes.query.MetadataQuery(score=True),
                        filters=combined_filters
                    )
            
            # Process results using v4 response format
            documents = []
            for item in response.objects:
                # Extract similarity score from metadata
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None) or getattr(item.metadata, 'score', None)
                
                # Handle datetime parsing safely
                created_at = datetime.now()
                updated_at = datetime.now()
                
                if item.properties.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(item.properties["created_at"])
                    except:
                        pass
                        
                if item.properties.get("updated_at"):
                    try:
                        updated_at = datetime.fromisoformat(item.properties["updated_at"])
                    except:
                        pass
                
                doc = DocumentResponse(
                    id=item.properties.get("document_id", str(item.uuid) if item.uuid else ""),  # Use PostgreSQL document_id
                    title=item.properties.get("title", ""),
                    content=item.properties.get("content", ""),
                    metadata=item.properties.get("metadata", {}),
                    tenant_id=item.properties.get("tenant_id", ""),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=created_at,
                    updated_at=updated_at,
                    similarity_score=similarity
                )
                documents.append(doc)
            
            search_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return SearchResponse(
                query=search_request.query,
                results=documents,
                total_results=len(documents),
                search_time_ms=search_time,
                search_type=search_request.search_type,
                tenant_id=search_request.tenant_id
            )
            
        except Exception as e:
            logger.error(f"❌ Search failed in {collection_name}: {e}")
            raise
    
    async def get_collection_info(self, collection_name: str) -> CollectionInfo:
        """Get information about a collection"""
        try:
            # Get collection info using v4 API
            collection = self.client.collections.get(collection_name)
            config = collection.config.get()
            schema = {
                "description": config.description or "",
                "properties": [prop.name for prop in config.properties] if config.properties else [],
                "vectorizer": str(config.vectorizer) if config.vectorizer else None
            }
            
            # Get object count using v4 API aggregate
            count_result = collection.aggregate.over_all(total_count=True)
            objects_count = count_result.total_count or 0
            
            return CollectionInfo(
                name=collection_name,
                description=schema.get("description", ""),
                objects_count=objects_count,
                properties=schema.get("properties", []),
                vectorizer=schema.get("vectorizer"),
                created_at=datetime.now()  # Weaviate doesn't store creation time
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to get info for collection {collection_name}: {e}")
            raise
    
    async def list_collections(self) -> List[str]:
        """List all collections"""
        try:
            # List collections using v4 API
            collections_list = self.client.collections.list_all()
            collections = [collection for collection in collections_list.keys() if collection is not None and isinstance(collection, str)]
            return collections
        except Exception as e:
            logger.error(f"❌ Failed to list collections: {e}")
            raise
    
    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection"""
        try:
            # Delete collection using v4 API
            self.client.collections.delete(collection_name)
            logger.info(f"✅ Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete collection {collection_name}: {e}")
            raise
    
    async def batch_add_documents(self, collection_name: str, documents: List[DocumentCreate]) -> Dict[str, Any]:
        """Batch add multiple documents"""
        try:
            results = []
            
            # Get collection for batch operations
            collection = self.client.collections.get(collection_name)
            
            # Prepare documents for batch insert
            batch_objects = []
            for document in documents:
                doc_id = document.id or str(uuid.uuid4())
                
                doc_data = {
                    "title": document.title,
                    "content": document.content,
                    "document_id": document.id,  # Store PostgreSQL document ID as property
                    "metadata": document.metadata,
                    "tenant_id": document.tenant_id,
                    "document_type": document.document_type,
                    "tags": document.tags,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Generate embeddings via Ollama if available
                if self.embedding_model:
                    import httpx
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.post(
                            f"{settings.ollama_base_url}/api/embeddings",
                            json={
                                "model": settings.embedding_model,
                                "prompt": f"{document.title} {document.content}"
                            }
                        )
                        if response.status_code == 200:
                            embedding_data = response.json()
                            doc_data["vector"] = embedding_data.get("embedding", [])
                
                batch_objects.append(weaviate.classes.data.DataObject(
                    properties=doc_data,
                    uuid=doc_id
                ))
                results.append(doc_id)
            
            # Execute batch insert using v4 API
            collection.data.insert_many(batch_objects)
            
            logger.info(f"✅ Batch added {len(documents)} documents to {collection_name}")
            return {"added_documents": len(documents), "document_ids": results}
            
        except Exception as e:
            logger.error(f"❌ Batch add failed for {collection_name}: {e}")
            raise
    
    async def vector_query(self, collection_name: str, query: VectorQuery) -> SearchResponse:
        """Execute raw vector query"""
        try:
            start_time = datetime.now()
            
            # Get collection for vector query using v4 API
            collection = self.client.collections.get(collection_name)
            
            # Build where filter for tenant isolation using v4 API
            where_filter = weaviate.classes.query.Filter.by_property("tenant_id").equal(query.tenant_id)
            
            if query.filters:
                for key, value in query.filters.items():
                    additional_filter = weaviate.classes.query.Filter.by_property(key).equal(str(value))
                    where_filter = where_filter & additional_filter
            
            # Execute vector search using v4 API
            return_metadata = [weaviate.classes.query.MetadataQuery.certainty()]
            if query.include_vector:
                return_metadata.append(weaviate.classes.query.MetadataQuery.vector())
            
            response = collection.query.near_vector(
                near_vector=query.vector,
                where=where_filter,
                limit=query.limit,
                return_metadata=return_metadata
            )
            
            # Process results using v4 response format
            documents = []
            for item in response.objects:
                similarity = None
                if hasattr(item, 'metadata') and item.metadata:
                    similarity = getattr(item.metadata, 'certainty', None)
                
                doc = DocumentResponse(
                    id=str(item.uuid) if item.uuid else "",
                    title=item.properties.get("title", ""),
                    content=item.properties.get("content", ""),
                    metadata=item.properties.get("metadata", {}),
                    tenant_id=item.properties.get("tenant_id", ""),
                    document_type=item.properties.get("document_type", ""),
                    tags=item.properties.get("tags", []),
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    similarity_score=similarity
                )
                documents.append(doc)
            
            search_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return SearchResponse(
                query="vector_query",
                results=documents,
                total_results=len(documents),
                search_time_ms=search_time,
                search_type="vector",
                tenant_id=query.tenant_id
            )
            
        except Exception as e:
            logger.error(f"❌ Vector query failed: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health"""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}
            
            is_ready = self.client.is_ready()
            is_live = self.client.is_live()
            
            return {
                "status": "healthy" if is_ready and is_live else "unhealthy",
                "ready": is_ready,
                "live": is_live,
                "url": settings.weaviate_url,
                "embedding_model": settings.embedding_model if self.embedding_model else None
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global service instance
weaviate_service = WeaviateService()
