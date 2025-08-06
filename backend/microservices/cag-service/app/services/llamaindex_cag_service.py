"""
CAG Service usando LlamaIndex - Framework que YA hace todo el RAG/CAG
No reinventamos la rueda, usamos lo que ya existe y funciona
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from llama_index.core import (
    VectorStoreIndex,
    Document,
    Settings,
    StorageContext,
    ServiceContext
)
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.node_parser import SentenceSplitter

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

from qdrant_client import QdrantClient
import nest_asyncio

# LlamaIndex requiere esto para funcionar en async
nest_asyncio.apply()


class LlamaIndexCAGService:
    """
    Servicio CAG usando LlamaIndex - TODO ya está hecho
    """
    
    def __init__(self):
        self.llm = None
        self.embed_model = None
        self.qdrant_client = None
        self._initialized = False
        self._tenant_indexes = {}  # Cache de índices por tenant
        
    async def initialize(self):
        """Inicializar LlamaIndex con Ollama"""
        if self._initialized:
            return
            
        try:
            logger.info("Inicializando LlamaIndex CAG Service...")
            
            # Configurar LLM (Ollama)
            self.llm = Ollama(
                model="llama3.2",
                base_url="http://host.docker.internal:11435",  # Puerto correcto
                request_timeout=60.0,
                temperature=0.7
            )
            
            # Configurar Embeddings (Ollama)
            self.embed_model = OllamaEmbedding(
                model_name="nomic-embed-text",
                base_url="http://host.docker.internal:11435",
                embed_batch_size=10
            )
            
            # Configurar Settings globales de LlamaIndex
            Settings.llm = self.llm
            Settings.embed_model = self.embed_model
            Settings.chunk_size = 1024
            Settings.chunk_overlap = 200
            
            # Conectar a Qdrant
            self.qdrant_client = QdrantClient(
                host="qdrant",
                port=6333,
                timeout=30
            )
            
            self._initialized = True
            logger.info("✅ LlamaIndex CAG Service inicializado")
            
        except Exception as e:
            logger.error(f"Error inicializando LlamaIndex: {e}")
            raise
    
    def _get_tenant_index(self, tenant_id: str) -> VectorStoreIndex:
        """Obtener o crear índice para tenant"""
        if tenant_id not in self._tenant_indexes:
            # Crear vector store para tenant
            collection_name = f"tenant_{tenant_id}_documents"
            
            vector_store = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=collection_name,
                enable_hybrid=True  # Búsqueda híbrida (vector + keyword)
            )
            
            # Crear storage context
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store
            )
            
            # Crear índice
            self._tenant_indexes[tenant_id] = VectorStoreIndex.from_documents(
                documents=[],  # Vacío inicialmente
                storage_context=storage_context,
                show_progress=True
            )
            
        return self._tenant_indexes[tenant_id]
    
    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Procesar query usando LlamaIndex Query Engine
        TODO el CAG/RAG ya está implementado en el framework
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            start_time = datetime.utcnow()
            
            # Obtener índice del tenant
            index = self._get_tenant_index(tenant_id)
            
            # Crear Query Engine con configuración avanzada
            query_engine = index.as_query_engine(
                # Retriever configuration
                similarity_top_k=5,
                
                # Response synthesis
                response_mode="tree_summarize",  # Mejor para respuestas largas
                
                # Postprocessing
                node_postprocessors=[
                    SimilarityPostprocessor(similarity_cutoff=0.7)
                ],
                
                # Streaming
                streaming=False,
                
                # Verbose para debugging
                verbose=True
            )
            
            # Ejecutar query
            logger.info(f"Procesando query para tenant {tenant_id}: {query[:100]}")
            response = query_engine.query(query)
            
            # Calcular tiempo de ejecución
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "success": True,
                "query": query,
                "answer": str(response),
                "source_nodes": [
                    {
                        "text": node.node.text[:200],
                        "score": node.score,
                        "metadata": node.node.metadata
                    } 
                    for node in response.source_nodes
                ] if hasattr(response, 'source_nodes') else [],
                "execution_time": execution_time,
                "engine": "llamaindex",
                "metadata": {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "response_mode": "tree_summarize"
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando query: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "answer": None
            }
    
    async def index_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        metadata: Optional[Dict] = None
    ) -> bool:
        """Indexar documento en LlamaIndex"""
        if not self._initialized:
            await self.initialize()
        
        try:
            # Obtener índice del tenant
            index = self._get_tenant_index(tenant_id)
            
            # Crear documento de LlamaIndex
            doc = Document(
                text=document_content,
                metadata={
                    "document_id": document_id,
                    "tenant_id": tenant_id,
                    "indexed_at": datetime.utcnow().isoformat(),
                    **(metadata or {})
                }
            )
            
            # Insertar en índice
            index.insert(doc)
            logger.info(f"Documento {document_id} indexado para tenant {tenant_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error indexando documento: {e}")
            return False
    
    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """Analizar documento usando LlamaIndex"""
        
        # Primero indexar el documento
        await self.index_document(
            document_content=document_content,
            document_id=document_id,
            tenant_id=tenant_id,
            metadata={"analysis_type": analysis_type}
        )
        
        # Queries especializadas por tipo de análisis
        queries = {
            "comprehensive": """
                Analiza este documento y proporciona:
                1. Resumen ejecutivo detallado
                2. Puntos clave y hallazgos principales
                3. Entidades importantes (personas, organizaciones, fechas, cantidades)
                4. Recomendaciones y próximos pasos
                5. Riesgos identificados
            """,
            
            "contract": """
                Analiza este contrato y extrae:
                1. Partes involucradas
                2. Obligaciones y términos clave
                3. Fechas importantes y plazos
                4. Cláusulas de penalización
                5. Condiciones de terminación
            """,
            
            "financial": """
                Realiza análisis financiero:
                1. Cifras y métricas clave
                2. Tendencias identificadas
                3. Riesgos financieros
                4. Oportunidades de mejora
                5. Comparación con estándares
            """
        }
        
        query = queries.get(analysis_type, queries["comprehensive"])
        
        # Procesar con el query engine
        result = await self.process_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            context={
                "document_id": document_id,
                "analysis_type": analysis_type
            }
        )
        
        if result["success"]:
            return {
                "success": True,
                "document_id": document_id,
                "analysis_type": analysis_type,
                "analysis": result["answer"],
                "source_nodes": result.get("source_nodes", []),
                "execution_time": result.get("execution_time", 0),
                "engine": "llamaindex"
            }
        
        return result
    
    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Chat conversacional usando LlamaIndex ChatEngine
        Mantiene contexto de la conversación
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Obtener índice
            index = self._get_tenant_index(tenant_id)
            
            # Crear Chat Engine (mantiene estado de conversación)
            chat_engine = index.as_chat_engine(
                chat_mode="condense_plus_context",  # Mejor modo para chat
                verbose=True
            )
            
            # Procesar mensaje
            response = chat_engine.chat(message)
            
            return {
                "success": True,
                "message": message,
                "response": str(response),
                "engine": "llamaindex-chat"
            }
            
        except Exception as e:
            logger.error(f"Error en chat: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio"""
        try:
            if not self._initialized:
                await self.initialize()
            
            # Test LLM
            llm_ok = False
            try:
                response = self.llm.complete("test")
                llm_ok = bool(response)
            except:
                pass
            
            # Test Embeddings
            embed_ok = False
            try:
                embedding = self.embed_model.get_text_embedding("test")
                embed_ok = len(embedding) > 0
            except:
                pass
            
            # Test Qdrant
            qdrant_ok = False
            try:
                self.qdrant_client.get_collections()
                qdrant_ok = True
            except:
                pass
            
            return {
                "status": "healthy" if all([llm_ok, embed_ok, qdrant_ok]) else "unhealthy",
                "service": "llamaindex-cag",
                "checks": {
                    "llm": llm_ok,
                    "embeddings": embed_ok,
                    "qdrant": qdrant_ok,
                    "llamaindex": True
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Instancia global
llamaindex_service = LlamaIndexCAGService()