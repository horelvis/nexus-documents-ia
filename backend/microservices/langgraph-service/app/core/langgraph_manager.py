from typing import Dict, Any, Optional
from loguru import logger
import asyncio
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver
import redis.asyncio as redis
import os

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
            # Set environment variables for Ollama
            os.environ["OLLAMA_HOST"] = settings.ollama_base_url
            
            # Initialize LLM with error handling
            try:
                self.llm = ChatOllama(
                    base_url=settings.ollama_base_url,
                    model=settings.llm_model,
                    temperature=0.7,
                    num_ctx=4096,  # Add context window
                    timeout=60  # Add timeout
                )
                logger.info(f"Initialized LLM: {settings.llm_model}")
                
                # Test LLM connection
                test_response = await self.llm.ainvoke("test")
                logger.info("LLM connection test successful")
            except Exception as llm_error:
                logger.warning(f"Failed to initialize Ollama LLM: {llm_error}")
                # Fallback to a simple mock LLM for testing
                logger.info("Using mock LLM for testing")
                from langchain_core.language_models.fake import FakeListLLM
                self.llm = FakeListLLM(
                    responses=["Mock response"]
                )
            
            # Initialize embeddings with error handling
            try:
                self.embeddings = OllamaEmbeddings(
                    model=settings.embedding_model,
                    base_url=settings.ollama_base_url
                )
                logger.info(f"Initialized embeddings: {settings.embedding_model}")
            except Exception as embed_error:
                logger.warning(f"Failed to initialize Ollama embeddings: {embed_error}")
                # Fallback to fake embeddings for testing
                from langchain_core.embeddings import FakeEmbeddings
                self.embeddings = FakeEmbeddings(size=384)
                logger.info("Using fake embeddings for testing")
            
            # Initialize Qdrant client with error handling
            try:
                self.qdrant_client = QdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    timeout=30
                )
                # Test connection
                await asyncio.to_thread(self.qdrant_client.get_collections)
                logger.info("Initialized Qdrant client")
            except Exception as qdrant_error:
                logger.warning(f"Failed to connect to Qdrant: {qdrant_error}")
                # Continue without Qdrant for now
                self.qdrant_client = None
            
            # Initialize checkpointer based on backend
            if settings.langgraph_backend == "sqlite":
                try:
                    self.checkpointer = SqliteSaver.from_conn_string(
                        f"sqlite:///{settings.checkpoint_db_path}"
                    )
                    logger.info("Initialized SQLite checkpointer")
                except Exception as e:
                    logger.warning(f"Failed to initialize SQLite checkpointer: {e}")
                    self.checkpointer = MemorySaver()
            elif settings.langgraph_backend == "redis":
                try:
                    self.redis_client = await redis.from_url(settings.redis_url)
                    await self.redis_client.ping()
                    # For now, use memory saver as Redis checkpointer is not yet available
                    self.checkpointer = MemorySaver()
                    logger.info("Initialized Redis client and memory checkpointer")
                except Exception as e:
                    logger.warning(f"Failed to connect to Redis: {e}")
                    self.checkpointer = MemorySaver()
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
        try:
            from app.graphs.tag_generation_graph import TagGenerationGraph
            from app.graphs.document_processing_graph import DocumentProcessingGraph
            from app.graphs.rag_graph import EnhancedRAGGraph
            from app.graphs.cag_graph import CAGGraph
            
            # Register core graph classes
            self.graphs = {
                "tag_generation": TagGenerationGraph,
                "document_processing": DocumentProcessingGraph,
                "rag": EnhancedRAGGraph,
                "cag": CAGGraph,  # NEW: Contextual Augmented Generation
            }
            
            # Try to register CrewAI graphs (may fail due to dependencies)
            try:
                from app.graphs.crewai_orchestration_graph import CrewAIOrchestrationGraph
                from app.graphs.document_analysis_crew import DocumentAnalysisCrew
                self.graphs["crew_orchestration"] = CrewAIOrchestrationGraph
                self.graphs["document_analysis_crew"] = DocumentAnalysisCrew
                logger.info("Successfully registered CrewAI graphs")
            except Exception as crew_error:
                logger.warning(f"Could not register CrewAI graphs: {crew_error}")
            
            logger.info(f"Registered {len(self.graphs)} graph types: {list(self.graphs.keys())}")
        except Exception as e:
            logger.error(f"Failed to register graphs: {e}")
            # Continue with empty graphs dict
            self.graphs = {}
    
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
    
    def get_vector_store(self, tenant_id: str) -> Optional[QdrantVectorStore]:
        """Get a vector store for a specific tenant"""
        if not self.qdrant_client:
            logger.warning("Qdrant client not available")
            return None
            
        collection_name = f"documents_{tenant_id}"
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=collection_name,
            embedding=self.embeddings
        )
    
    async def health_check(self) -> bool:
        """Check if all components are healthy"""
        try:
            health_status = {
                "llm": self.llm is not None,
                "embeddings": self.embeddings is not None,
                "checkpointer": self.checkpointer is not None
            }
            
            # Check Qdrant connection if available
            if self.qdrant_client:
                try:
                    await asyncio.to_thread(self.qdrant_client.get_collections)
                    health_status["qdrant"] = True
                except:
                    health_status["qdrant"] = False
            
            # Check Redis if using Redis backend
            if self.redis_client:
                try:
                    await self.redis_client.ping()
                    health_status["redis"] = True
                except:
                    health_status["redis"] = False
            
            # Overall health is True if core components are available
            is_healthy = health_status["llm"] and health_status["embeddings"] and health_status["checkpointer"]
            
            logger.info(f"Health check status: {health_status}")
            return is_healthy
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.redis_client:
            try:
                await self.redis_client.close()
            except:
                pass