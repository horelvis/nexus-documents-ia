"""CAG Service implementation - SOLO CrewAI"""
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger

from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Qdrant as QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from ..core.config import settings

# Import OFFICIAL CrewAI service - YAML pattern from docs!
from .official_crewai_service import official_crewai_service
logger.info("🚀 Using OFFICIAL CrewAI - YAML pattern from official docs!")


class CAGService:
    """Main CAG service implementation - SOLO CrewAI"""
    
    def __init__(self):
        self.llm = None
        self.embeddings = None
        self.qdrant_client = None
        self.cag_engine = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize CAG service components"""
        if self._initialized:
            return
        
        # Initialize embeddings for the service
        if not self.embeddings:
            logger.info("Initializing embeddings service...")
            self.embeddings = OllamaEmbeddings(
                model="all-minilm",
                base_url=settings.ollama_base_url
            )
        
        # OFFICIAL CrewAI, patrón YAML oficial
        try:
            await official_crewai_service.initialize()
            self._initialized = True
            logger.info("CAG service initialized with OFFICIAL CrewAI and embeddings")
        except Exception as e:
            logger.error(f"Failed to initialize OFFICIAL CrewAI: {e}")
            raise RuntimeError(f"OFFICIAL CrewAI is required but failed to initialize: {e}")
    
    def _get_tenant_collection(self, tenant_id: str) -> str:
        """Get collection name for tenant"""
        return f"tenant_{tenant_id}_documents"
    
    def _get_vector_store(self, tenant_id: str):
        """Get or create vector store for tenant"""
        if not self.qdrant_client:
            self.qdrant_client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port
            )
        
        if not self.embeddings:
            self.embeddings = OllamaEmbeddings(
                model="all-minilm",
                base_url=settings.ollama_base_url
            )
        
        collection_name = self._get_tenant_collection(tenant_id)
        
        # Ensure collection exists
        try:
            self.qdrant_client.get_collection(collection_name)
        except Exception:
            logger.info(f"Creating collection for tenant {tenant_id}")
            self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=384,  # all-minilm dimension
                    distance=Distance.COSINE
                )
            )
        
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name,
            embeddings=self.embeddings  # Changed from 'embedding' to 'embeddings'
        )
    
    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process a query using CAG"""
        # SOLO CrewAI, sin fallbacks
        if not self._initialized:
            await self.initialize()
            
        try:
            return await official_crewai_service.process_query(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,
                context=context
            )
        except Exception as e:
            logger.error(f"Official CrewAI processing failed: {e}")
            return {
                "success": False,
                "error": f"Official CrewAI failed: {str(e)}",
                "query": query,
                "answer": None
            }
    
    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive"
    ) -> Dict[str, Any]:
        """Analyze a document using CAG"""
        # SOLO CrewAI, sin fallbacks
        if not self._initialized:
            await self.initialize()
            
        try:
            # Para análisis de documentos, usar el query processor simple
            query = f"Analyze this document content: {document_content[:500]}"
            return await official_crewai_service.process_query(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,
                context={"document_id": document_id, "analysis_type": analysis_type}
            )
        except Exception as e:
            logger.error(f"Official CrewAI document analysis failed: {e}")
            return {
                "success": False,
                "error": f"Official CrewAI failed: {str(e)}",
                "document_id": document_id,
                "analysis": None
            }
    
    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None
    ):
        """Process a query using CAG with streaming progress"""
        # SOLO CrewAI, sin fallbacks
        if not self._initialized:
            await self.initialize()
            
        try:
            # Simple streaming - just return the regular response as a single event
            result = await official_crewai_service.process_query(
                query=query,
                tenant_id=tenant_id,
                user_id=user_id,
                context=context
            )
            
            if result.get("success"):
                yield {
                    "type": "content",
                    "content": result.get("response", ""),
                    "success": True
                }
                yield {
                    "type": "done",
                    "metadata": result.get("metadata", {}),
                    "success": True
                }
            else:
                yield {
                    "type": "error",
                    "content": result.get("error", "Unknown error"),
                    "success": False
                }
        except Exception as e:
            logger.error(f"Official CrewAI streaming failed: {e}")
            yield {
                "type": "error",
                "content": f"Official CrewAI failed: {str(e)}",
                "success": False
            }
    
    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Chat with CAG"""
        # SOLO CrewAI
        if not self._initialized:
            await self.initialize()
            
        try:
            return await official_crewai_service.chat(
                message=message,
                tenant_id=tenant_id,
                user_id=user_id,
                context={"history": chat_history or []}
            )
        except Exception as e:
            logger.error(f"Official CrewAI chat failed: {e}")
            return {
                "success": False,
                "error": f"Official CrewAI failed: {str(e)}",
                "response": None
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        # SOLO CrewAI
        try:
            return await official_crewai_service.health_check()
        except Exception as e:
            logger.error(f"Official CrewAI health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": f"Official CrewAI failed: {str(e)}"
            }
    
    def get_available_agents_info(self, tenant_id: str = "default") -> Dict[str, Any]:
        """Get REAL available agents information - delegated to CrewAI"""
        # SOLO CrewAI
        try:
            return official_crewai_service.get_available_agents_info(tenant_id)
        except Exception as e:
            logger.error(f"Official CrewAI get agents info failed: {e}")
            return {
                "available_types": {},
                "total": 0,
                "error": f"Official CrewAI failed: {str(e)}"
            }


# Global instance
cag_service = CAGService()