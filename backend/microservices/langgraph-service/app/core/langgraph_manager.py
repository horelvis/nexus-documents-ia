from typing import Dict, Any, Optional
from loguru import logger
import asyncio
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver
import redis.asyncio as redis

from app.core.config import settings


class LangGraphManager:
    """Singleton manager for LangGraph components"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.llm = None
            self.embeddings = None
            self.qdrant_client = None
            self.checkpointer = None
            self.redis_client = None
            self.graphs = {}
            self._initialized = True
    
    async def initialize(self):
        """Initialize all LangGraph components"""
        try:
            # Initialize LLM
            self.llm = ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.llm_model,
                temperature=0.7
            )
            logger.info(f"Initialized LLM: {settings.llm_model}")
            
            # Initialize embeddings
            # Set OLLAMA_HOST environment variable for OllamaEmbeddings
            import os
            os.environ["OLLAMA_HOST"] = settings.ollama_base_url
            
            self.embeddings = OllamaEmbeddings(
                model=settings.embedding_model
            )
            logger.info(f"Initialized embeddings: {settings.embedding_model}")
            
            # Initialize Qdrant client
            self.qdrant_client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port
            )
            logger.info("Initialized Qdrant client")
            
            # Initialize checkpointer based on backend
            if settings.langgraph_backend == "sqlite":
                self.checkpointer = SqliteSaver.from_conn_string(
                    f"sqlite:///{settings.checkpoint_db_path}"
                )
                logger.info("Initialized SQLite checkpointer")
            elif settings.langgraph_backend == "redis":
                self.redis_client = await redis.from_url(settings.redis_url)
                # For now, use memory saver as Redis checkpointer is not yet available
                self.checkpointer = MemorySaver()
                logger.info("Initialized Redis client and memory checkpointer")
            else:
                self.checkpointer = MemorySaver()
                logger.info("Initialized memory checkpointer")
            
            # Register available graphs
            await self._register_graphs()
            
        except Exception as e:
            logger.error(f"Failed to initialize LangGraphManager: {e}")
            raise
    
    async def _register_graphs(self):
        """Register all available graph types"""
        from app.graphs.tag_generation_graph import TagGenerationGraph
        from app.graphs.document_processing_graph import DocumentProcessingGraph
        from app.graphs.rag_graph import EnhancedRAGGraph
        from app.graphs.crewai_orchestration_graph import CrewAIOrchestrationGraph
        from app.graphs.document_analysis_crew import DocumentAnalysisCrew
        
        # Register graph classes
        self.graphs = {
            "tag_generation": TagGenerationGraph,
            "document_processing": DocumentProcessingGraph,
            "rag": EnhancedRAGGraph,
            "crew_orchestration": CrewAIOrchestrationGraph,
            "document_analysis_crew": DocumentAnalysisCrew
        }
        logger.info(f"Registered {len(self.graphs)} graph types")
    
    def get_graph(self, graph_name: str, **kwargs):
        """Get a graph instance by name"""
        if graph_name not in self.graphs:
            raise ValueError(f"Unknown graph type: {graph_name}")
        
        graph_class = self.graphs[graph_name]
        return graph_class(
            llm=self.llm,
            embeddings=self.embeddings,
            qdrant_client=self.qdrant_client,
            checkpointer=self.checkpointer,
            **kwargs
        )
    
    def get_vector_store(self, tenant_id: str) -> QdrantVectorStore:
        """Get a vector store for a specific tenant"""
        collection_name = f"documents_{tenant_id}"
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name,
            embedding=self.embeddings
        )
    
    async def health_check(self) -> bool:
        """Check if all components are healthy"""
        try:
            # Check Qdrant connection
            collections = await asyncio.to_thread(
                self.qdrant_client.get_collections
            )
            
            # Check Redis if using Redis backend
            if self.redis_client:
                await self.redis_client.ping()
            
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.redis_client:
            await self.redis_client.close()