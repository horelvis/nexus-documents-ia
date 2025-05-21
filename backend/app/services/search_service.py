import logging
from typing import List, Dict, Any, Optional, Set

from app.core.config import settings
from app.db.database import get_db
from app.db.models import Document, DocumentChunk
from app.services.document_tracking_service import DocumentTrackingService
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class SearchService:
    """Servicio para búsqueda semántica y respuesta a preguntas"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.embedding_service = EmbeddingService(tenant_id)
        self.llm_service = LLMService()
    
    def semantic_search(
        self, 
        query: str, 
        limit: int = 10, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza una búsqueda semántica en los documentos indexados.
        
        Args:
            query: Texto de consulta
            limit: Número máximo de resultados
            filters: Filtros adicionales (tags, fechas, etc.)
            
        Returns:
            Lista de resultados con metadatos y puntuaciones
        """
        db = next(get_db())
        
        try:
            # Preparar filtros de tenant
            search_filters = {"tenant_id": self.tenant_id}
            
            # Añadir filtros adicionales si existen
            if filters:
                if "tags" in filters and filters["tags"]:
                    search_filters["tags"] = filters["tags"]
                
                # Otros filtros...
            
            # Realizar búsqueda en embeddings
            vector_results = self.embedding_service.search(
                query=query,
                limit=limit * 3,  # Buscar más para agrupar por documento
                filters=search_filters
            )
            
            if not vector_results:
                return []
            
            # Agrupar resultados por documento y limitar
            doc_scores = {}  # Puntuación por documento
            doc_matches = {}  # Fragmentos relevantes por documento
            doc_ids = set()   # IDs de documentos encontrados
            
            for result in vector_results:
                doc_id = result['metadata'].get('doc_id')
                if doc_id:
                    doc_ids.add(doc_id)
                    
                    # Acumular puntuación por documento
                    if doc_id not in doc_scores:
                        doc_scores[doc_id] = 0
                        doc_matches[doc_id] = []
                    
                    score = result['score']
                    doc_scores[doc_id] += score
                    
                    # Guardar fragmento relevante
                    doc_matches[doc_id].append({
                        'chunk_text': result['metadata'].get('chunk_text', ''),
                        'score': score
                    })
            
            # Obtener información completa de los documentos
            documents = {}
            if doc_ids:
                db_docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
                for doc in db_docs:
                    documents[str(doc.id)] = doc
            
            # Formatear resultados
            results = []
            for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
                if doc_id in documents:
                    doc = documents[doc_id]
                    
                    # Ordenar fragmentos por puntuación
                    matches = sorted(doc_matches[doc_id], key=lambda x: x['score'], reverse=True)
                    
                    results.append({
                        'document': {
                            'id': str(doc.id),
                            'title': doc.title,
                            'description': doc.description,
                            'filename': doc.filename,
                            'file_type': doc.file_type,
                            'file_size': doc.file_size,
                            'created_at': doc.created_at.isoformat(),
                            'tags': [tag.name for tag in doc.tags]
                        },
                        'score': score,
                        'matches': matches[:3]  # Limitar a los 3 mejores fragmentos
                    })
                
                if len(results) >= limit:
                    break
            
            return results
            
        except Exception as e:
            logger.exception(f"Error during semantic search: {str(e)}")
            return []
    
    def ask_documents(self, question: str, doc_ids: List[str] = None) -> Dict[str, str]:
        """
        Responde una pregunta basándose en el contenido de los documentos.
        
        Args:
            question: Pregunta del usuario
            doc_ids: Lista opcional de IDs de documentos a consultar
            
        Returns:
            Respuesta generada
        """
        db = next(get_db())
        
        try:
            # Validar acceso a los documentos si se especifican
            if doc_ids:
                # Verificar acceso a los documentos especificados
                valid_docs = db.query(Document).filter(
                    Document.id.in_(doc_ids),
                    Document.tenant_id == self.tenant_id
                ).all()
                
                valid_doc_ids = [str(doc.id) for doc in valid_docs]
                
                # Si algún documento no es accesible, excluirlo
                if len(valid_doc_ids) < len(doc_ids):
                    logger.warning(f"Some documents were not found or not accessible: {set(doc_ids) - set(valid_doc_ids)}")
                
                doc_ids = valid_doc_ids
            
            # Preparar filtros para la búsqueda
            search_filters = {"tenant_id": self.tenant_id}
            if doc_ids:
                search_filters["doc_ids"] = doc_ids
            
            # Realizar búsqueda semántica para encontrar contexto relevante
            search_results = self.embedding_service.search(
                query=question,
                limit=10,
                filters=search_filters
            )
            
            if not search_results:
                return {"answer": "No encontré información relevante para responder a tu pregunta en los documentos disponibles."}
            
           # Extraer texto de los chunks relevantes para formar el contexto
            context_chunks = []
            document_ids_used = set()  # Conjunto para rastrear documentos usados
            
            for result in search_results:
                chunk_text = result['metadata'].get('chunk_text', '')
                doc_id = result['metadata'].get('doc_id')
                
                if chunk_text:
                    context_chunks.append(chunk_text)
                    
                # Registrar el documento usado si tiene ID
                if doc_id:
                    document_ids_used.add(doc_id)
            
            # Registrar las consultas para cada documento utilizado
            tracking_service = DocumentTrackingService(tenant_id=self.tenant_id, user_id=None)
            for doc_id in document_ids_used:
                tracking_service.record_document_query(doc_id)
            
            # Unir el contexto
            context = "\n\n".join(context_chunks)
            
            # Generar respuesta usando el LLM
            answer = self.llm_service.answer_question(question, context)
            
            return {"answer": answer}

        except Exception as e:
            logger.exception(f"Error answering question: {str(e)}")
            return {"answer": f"Lo siento, ocurrió un error al procesar tu pregunta: {str(e)}"}