"""
CAG Service - Now powered by 5-Layer RAG Pipeline

This service facade exposes legacy /api/v1/cag endpoints while delegating
all logic to the new RAG Pipeline (replacing Elysia).

The CAG (Context-Augmented Generation) API is maintained for backwards
compatibility with existing frontend integrations.
"""
from typing import Dict, Any, Optional, List, AsyncGenerator
from loguru import logger
import httpx

from ...services.rag import RAGPipeline
from ...services.rag.rag_pipeline import rag_pipeline
from ...services.weaviate_service import weaviate_service
from ..core.config import settings


class CAGService:
    """
    CAG Service facade - bridges legacy API to new RAG Pipeline.

    The 7-layer RAG Pipeline provides:
    - Layer 1: Query Intelligence (expansion, intent classification)
    - Layer 2: Multi-Stage Retrieval (vector + reranking + fusion)
    - Layer 3: Context Assembly (token management)
    - Layer 4: Validated Generation (citations, fact-checking)
    """

    def __init__(self):
        self._initialized = False
        self._pipeline: RAGPipeline = rag_pipeline

    async def initialize(self):
        """Initialize the service"""
        await self._ensure_initialized()

    async def _ensure_initialized(self):
        """Ensure all components are initialized"""
        if not self._initialized:
            await weaviate_service.initialize()
            await self._pipeline.initialize()
            self._initialized = True
            logger.info("✅ CAGService initialized with 7-layer RAG Pipeline")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_iterations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process a query using the RAG Pipeline.

        Args:
            query: User's question
            tenant_id: Tenant identifier
            user_id: User identifier
            context: Additional context (conversation_id, etc.)
            model: LLM model override (not used in new pipeline)
            temperature: Generation temperature (not used - fixed at 0.3)
            max_iterations: Not used in new pipeline

        Returns:
            Dict with answer, quality_score, metadata, etc.
        """
        await self._ensure_initialized()

        # Extract conversation context if present
        merged_context = context or {}

        # Process through RAG Pipeline
        response = await self._pipeline.process_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            context=merged_context,
            top_k=10,
            validate_claims=True,
        )

        # Convert to CAG response format
        result = response.to_cag_response()
        result["query"] = query
        result["metadata"]["user_id"] = user_id

        return result

    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a query with streaming progress.

        Yields progress events and final result.
        """
        await self._ensure_initialized()

        yield {"type": "progress", "content": "Inicializando RAG Pipeline...", "progress": 5}

        async for event in self._pipeline.process_query_stream(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            context=context,
        ):
            yield event

    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive",
    ) -> Dict[str, Any]:
        """
        Analyze a document using the RAG Pipeline.

        Args:
            document_content: Full document text
            document_id: Document identifier
            tenant_id: Tenant identifier
            user_id: User identifier
            analysis_type: Type of analysis (comprehensive, risks, summary, etc.)

        Returns:
            Dict with analysis results
        """
        await self._ensure_initialized()

        result = await self._pipeline.analyze_document(
            document_content=document_content,
            document_id=document_id,
            tenant_id=tenant_id,
            analysis_type=analysis_type,
        )

        return result

    async def analyze_document_stream(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Analyze a document with streaming progress.

        Yields progress events and final result.
        """
        await self._ensure_initialized()

        yield {"type": "progress", "content": "Preparando análisis...", "progress": 10}

        # Document analysis doesn't stream internally, so we wrap it
        yield {"type": "progress", "content": "Analizando documento...", "progress": 30}

        result = await self.analyze_document(
            document_content=document_content,
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            analysis_type=analysis_type,
        )

        yield {"type": "progress", "content": "Finalizando...", "progress": 90}
        yield {"type": "result", "content": result}

    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Chat endpoint - delegates to process_query.

        Args:
            message: User's message
            tenant_id: Tenant identifier
            user_id: User identifier
            chat_history: Previous messages in conversation

        Returns:
            Dict with response
        """
        context = {"message_history": chat_history or []}
        return await self.process_query(message, tenant_id, user_id, context)

    async def generate_embeddings(
        self,
        texts: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate embeddings via intelligence-docs-service.

        Args:
            texts: List of texts to embed
            tenant_id: Optional tenant identifier

        Returns:
            Dict with embeddings
        """
        await self._ensure_initialized()

        from app.clients import intelligence_client

        embeddings = await intelligence_client.embed_batch(texts)
        if embeddings is None:
            embeddings = [[] for _ in texts]

        return {
            "success": True,
            "embeddings": embeddings,
            "count": len(embeddings),
            "model": settings.embedding_model,
            "tenant_id": tenant_id,
        }

    async def get_available_agents_info(self, tenant_id: str = "default") -> Dict[str, Any]:
        """
        Get available 'agents' info (pipeline stages for backwards compatibility).

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dict with pipeline stage info
        """
        await self._ensure_initialized()

        tools = await self._pipeline.list_tools()

        return {
            "service": "rag-pipeline-7layer",
            "tenant_id": tenant_id,
            "total": len(tools),
            "agents": tools,
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Check service health.

        Returns:
            Dict with health status
        """
        await self._ensure_initialized()

        pipeline_health = await self._pipeline.health_check()

        return {
            "status": pipeline_health.get("status", "unknown"),
            "service": "rag-pipeline-7layer",
            "checks": pipeline_health.get("components", {}),
            "config": pipeline_health.get("config", {}),
        }


# Global instance
cag_service = CAGService()
