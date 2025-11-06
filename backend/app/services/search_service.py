"""
Hybrid Search Service combining Weaviate and Elasticsearch
- Weaviate: Fast semantic search (80% cases)
- Elasticsearch: Complex hybrid search + analytics (20% cases)
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.services.llm_service import LLMService
from app.services.vector_service import VectorService
from app.services.elasticsearch_client import elasticsearch_client
from app.db.database import SessionLocal
from app.db.models import Document

logger = logging.getLogger(__name__)


class SearchService:
    """Hybrid Search Service: Weaviate (primary) + Elasticsearch (specialized)"""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.llm_service = LLMService()
        self.vector_service = VectorService(tenant_id)  # Weaviate - Primary
        # Elasticsearch is now a microservice - no local initialization needed
        
        logger.info(f"SearchService initialized for tenant: {tenant_id}")
        logger.info("Using hybrid architecture: Weaviate (primary) + Elasticsearch (specialized)")
    
    async def chat_with_documents(
        self, 
        query: str, 
        doc_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        Realiza chat con documentos usando RAG.
        
        Args:
            query: Pregunta del usuario
            doc_ids: Lista opcional de IDs de documentos para filtrar
            
        Returns:
            Respuesta con fuentes
        """
        try:
            logger.info(f"Chat query for tenant {self.tenant_id}: {query[:100]}...")
            
            # Usar LLMService con RAG
            response = await self.llm_service.generate_response(
                query=query,
                doc_ids=doc_ids,
                tenant_id=self.tenant_id
            )
            
            logger.debug(f"Generated response with {len(response.get('sources', []))} sources")
            return response
            
        except Exception as e:
            logger.error(f"Error in chat_with_documents: {str(e)}")
            return {
                "answer": "Lo siento, ocurrió un error al procesar tu consulta.",
                "sources": [],
                "error": str(e)
            }
    
    async def search_documents(
        self, 
        query: str, 
        limit: int = 10,
        doc_ids: List[str] = None,
        search_type: str = "semantic",  # "semantic", "hybrid", "keyword"
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Smart hybrid search: routes to optimal engine based on query complexity
        
        Args:
            query: Search query
            limit: Maximum results
            doc_ids: Optional document ID filter
            search_type: "semantic" (Weaviate), "hybrid" (Elasticsearch), "keyword" (Elasticsearch)
            filters: Additional filters (tags, dates, etc.)
            
        Returns:
            List of documents with complete data
        """
        try:
            logger.debug(f"Hybrid search - Type: {search_type}, Query: {query[:100]}...")
            
            # Route to appropriate search engine
            if search_type == "hybrid" or search_type == "keyword":
                # Use Elasticsearch for hybrid/keyword search
                logger.info("🔍 Using Elasticsearch for hybrid/keyword search")
                results = await elasticsearch_client.hybrid_search(
                    tenant_id=self.tenant_id,
                    query=query,
                    limit=limit,
                    filters=filters or {}
                )
                
            else:
                # Use Weaviate for semantic search (default, faster)
                logger.info("🚀 Using Weaviate for semantic search")
                if doc_ids:
                    vector_results = await self.vector_service.search_by_document_ids(
                        doc_ids=doc_ids,
                        query=query,
                        limit=limit
                    )
                else:
                    vector_results = await self.vector_service.search_similar(
                        query=query,
                        limit=limit
                    )
                
                # Enrich with complete document data
                results = await self._enrich_search_results(vector_results)
            
            logger.info(f"✅ {search_type.capitalize()} search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"❌ Hybrid search failed: {str(e)}")
            return []
    
    async def _enrich_search_results(self, vector_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich vector search results with complete document data from database.
        
        Args:
            vector_results: Results from vector search with basic metadata
            
        Returns:
            Enriched results with full document data
        """
        if not vector_results:
            return []
        
        try:
            # Extract document IDs from vector results
            doc_ids = []
            results_by_doc_id = {}
            
            for result in vector_results:
                # Try different ways to extract doc_id
                doc_id = None
                if 'metadata' in result and result['metadata']:
                    doc_id = result['metadata'].get('doc_id') or result['metadata'].get('_id')
                
                if doc_id:
                    doc_ids.append(doc_id)
                    results_by_doc_id[doc_id] = result
                else:
                    logger.warning(f"No doc_id found in result: {result.keys()}")
            
            if not doc_ids:
                logger.warning("No document IDs found in vector search results")
                return vector_results
            
            # Get complete document data from database with tags
            with SessionLocal() as db:
                documents = db.query(Document).options(
                    joinedload(Document.tags)
                ).filter(
                    Document.id.in_(doc_ids),
                    Document.tenant_id == self.tenant_id
                ).all()
            
            # Create enriched results
            enriched_results = []
            for doc in documents:
                doc_id = str(doc.id)
                vector_result = results_by_doc_id.get(doc_id)
                
                if vector_result:
                    try:
                        # Create enriched result structure that matches frontend expectations
                        enriched_result = {
                            "document": {
                                "id": str(doc.id),
                                "title": doc.title or vector_result.get('metadata', {}).get('title', doc.filename),
                                "description": doc.description,
                                "filename": doc.filename or vector_result.get('metadata', {}).get('filename'),
                                "file_type": doc.file_type or vector_result.get('metadata', {}).get('file_type'),
                                "file_size": doc.file_size,
                                "mime_type": doc.mime_type,
                                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                                "indexed": str(doc.indexed) if doc.indexed is not None else "unknown",
                                "tenant_id": str(doc.tenant_id),
                                "tags": [tag.name for tag in doc.tags] if doc.tags else []
                            },
                            "score": vector_result.get('score', 0.0),
                            "matches": self._extract_matches_from_content(vector_result)
                        }
                        enriched_results.append(enriched_result)
                    except Exception as doc_error:
                        logger.error(f"Error processing document {doc.id}: {str(doc_error)}")
                        # Add original vector result as fallback
                        enriched_results.append(vector_result)
            
            logger.debug(f"Enriched {len(enriched_results)} search results with database data")
            return enriched_results
            
        except Exception as e:
            logger.error(f"Error enriching search results: {str(e)}")
            # Return original results if enrichment fails - frontend can handle both structures
            logger.info("Falling back to vector search results without database enrichment")
            return vector_results
    
    def _extract_matches_from_content(self, vector_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract text matches from vector search content.
        
        Args:
            vector_result: Single vector search result
            
        Returns:
            List of text matches with scores
        """
        matches = []
        content = vector_result.get('content', '')
        score = vector_result.get('score', 0.0)
        
        if content and len(content.strip()) > 0:
            # Create a match from the content
            # For now, we'll create one match per result
            # In the future, this could be more sophisticated
            matches.append({
                "text": content[:200] + "..." if len(content) > 200 else content,
                "score": score
            })
        
        return matches
    
    async def ask_documents(
        self, 
        question: str, 
        doc_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        Ask a question about documents using RAG.
        
        Args:
            question: Question to ask
            doc_ids: Optional list of document IDs to limit the search to
            
        Returns:
            Answer with sources
        """
        try:
            logger.debug(f"Asking question: {question[:100]}...")
            
            # Use the chat_with_documents method for RAG
            response = await self.chat_with_documents(
                query=question,
                doc_ids=doc_ids
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error in ask_documents: {str(e)}")
            return {
                "answer": "Lo siento, ocurrió un error al procesar tu pregunta.",
                "sources": [],
                "error": str(e)
            }
    
    async def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """
        Sugiere tags para un texto.
        
        Args:
            text: Texto para analizar
            num_tags: Número de tags a sugerir
            
        Returns:
            Lista de tags sugeridos
        """
        try:
            return await self.llm_service.suggest_tags(text, num_tags)
        except Exception as e:
            logger.error(f"Error suggesting tags: {str(e)}")
            return ["documento", "texto"]
    
    async def extract_metadata(self, text: str) -> Dict[str, str]:
        """
        Extrae metadatos de un texto.
        
        Args:
            text: Texto para analizar
            
        Returns:
            Diccionario con metadatos
        """
        try:
            return await self.llm_service.extract_metadata(text)
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {"título": "Documento", "tipo": "texto"}
    
    async def summarize_document(self, text: str, max_length: int = 200) -> str:
        """
        Genera un resumen de un documento.
        
        Args:
            text: Texto a resumir
            max_length: Longitud máxima del resumen
            
        Returns:
            Resumen del documento
        """
        try:
            return await self.llm_service.summarize_text(text, max_length)
        except Exception as e:
            logger.error(f"Error summarizing document: {str(e)}")
            return "Resumen no disponible."
    
    async def ask_documents(
        self, 
        question: str, 
        doc_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        Hace una pregunta sobre documentos específicos.
        Alias para chat_with_documents para compatibilidad con API.
        
        Args:
            question: Pregunta del usuario
            doc_ids: Lista opcional de IDs de documentos para filtrar
            
        Returns:
            Respuesta con fuentes
        """
        return await self.chat_with_documents(query=question, doc_ids=doc_ids)
    
    async def semantic_search(
        self, 
        query: str, 
        limit: int = 10,
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda semántica en los documentos.
        Versión síncrona que envuelve search_documents para compatibilidad con API.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            filters: Filtros adicionales (tags, fechas, etc.)
            
        Returns:
            Lista de documentos similares con puntuaciones
        """
        try:
            logger.debug(f"Semantic search for query: {query[:100]}...")
            
            # Por ahora, llamamos directamente al método síncrono del vector_service
            # En el futuro, se puede agregar lógica de filtros adicionales aquí
            if filters:
                # Aplicar filtros si están presentes
                doc_ids = filters.get('doc_ids')
                if doc_ids:
                    results = await self.vector_service.search_by_document_ids(
                        doc_ids=doc_ids,
                        query=query,
                        limit=limit
                    )
                else:
                    results = await self.vector_service.search_similar(
                        query=query,
                        limit=limit
                    )
            else:
                results = await self.vector_service.search_similar(
                    query=query,
                    limit=limit
                )
            
            # Formatear resultados para que coincidan con la estructura esperada por los tests
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "document": result.get("document", {}),
                    "score": result.get("score", 0.0),
                    "matches": result.get("matches", [])
                })
            
            logger.debug(f"Found {len(formatted_results)} semantic search results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            return []

    async def get_vector_store_info(self) -> Dict[str, Any]:
        """
        Obtiene información del vector store.
        
        Returns:
            Información del vector store
        """
        try:
            return await self.vector_service.get_collection_info()
        except Exception as e:
            logger.error(f"Error getting vector store info: {str(e)}")
            return {}
    
    async def get_search_analytics(
        self, 
        date_from: str = None, 
        date_to: str = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive search and document analytics from Elasticsearch
        
        Args:
            date_from: Start date for analytics
            date_to: End date for analytics
            
        Returns:
            Analytics data with insights
        """
        try:
            logger.info("📊 Fetching search analytics from Elasticsearch")
            analytics = await elasticsearch_client.get_analytics(
                tenant_id=self.tenant_id,
                date_from=date_from,
                date_to=date_to
            )
            
            # Add some computed metrics
            analytics["search_engines"] = {
                "weaviate": {"status": "active", "role": "primary_semantic"},
                "elasticsearch": {"status": "active", "role": "hybrid_analytics"}
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"❌ Failed to get search analytics: {str(e)}")
            return {"error": str(e)}
    
    async def suggest_search_type(self, query: str) -> str:
        """
        Intelligently suggest optimal search type based on query characteristics
        
        Args:
            query: User search query
            
        Returns:
            Suggested search type: "semantic", "hybrid", or "keyword"
        """
        query_lower = query.lower()
        
        # Check for wildcards first (highest priority)
        if '*' in query or '?' in query:
            return "hybrid"  # Use hybrid for wildcard patterns
        
        # Keyword search indicators
        keyword_indicators = [
            "type:", "category:", "tag:", "file:", "size:", 
            "before:", "after:", "author:", "created:",
            "AND", "OR", "NOT", '"'  # Boolean operators, exact phrases
        ]
        
        # Complex filter indicators (suggest hybrid)
        complex_indicators = [
            "recent", "latest", "last week", "last month",
            "large files", "small files", "pdf only", "documents about",
            "similar to", "related to", "contains exact"
        ]
        
        # Check for keyword search
        if any(indicator in query_lower for indicator in keyword_indicators):
            return "keyword"
            
        # Check for complex hybrid search
        if any(indicator in query_lower for indicator in complex_indicators):
            return "hybrid"
            
        # Default to semantic (fastest, best for most queries)
        return "semantic"