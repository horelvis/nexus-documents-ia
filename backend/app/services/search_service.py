"""
LangChain-based Search Service with simplified RAG
"""
import logging
from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.services.llm_service import LLMService
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class SearchService:
    """Servicio de búsqueda simplificado usando LangChain"""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.llm_service = LLMService()
        self.vector_service = VectorService(tenant_id)
        
        logger.info(f"SearchService initialized for tenant: {tenant_id}")
    
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
        doc_ids: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca documentos similares a la consulta.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            doc_ids: Lista opcional de IDs de documentos para filtrar
            
        Returns:
            Lista de documentos similares
        """
        try:
            logger.debug(f"Searching documents for query: {query[:100]}...")
            
            if doc_ids:
                # Búsqueda filtrada por documentos específicos
                results = self.vector_service.search_by_document_ids(
                    doc_ids=doc_ids,
                    query=query,
                    limit=limit
                )
            else:
                # Búsqueda general
                results = self.vector_service.search_similar(
                    query=query,
                    limit=limit
                )
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return []
    
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