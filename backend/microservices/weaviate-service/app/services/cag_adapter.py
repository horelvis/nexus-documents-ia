"""Adapter that emulates the legacy CAG API on top of Elysia."""
import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from sentence_transformers import SentenceTransformer

from app.schemas.cag import (
    CAGQueryRequest,
    CAGQueryResponse,
    DocumentAnalysisRequest,
    DocumentAnalysisResponse,
    TaskExecutionRequest,
)
from app.schemas.elysia import ElysiaQuery
from app.services.elysia_service import elysia_service

logger = logging.getLogger(__name__)


class CAGAdapter:
    """Bridges old CAG endpoints with the new Elysia-based implementation."""

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        self.embedding_model = embedding_model
        self._embedder: Optional[SentenceTransformer] = None
        self._embedder_lock = asyncio.Lock()

    async def _ensure_elysia_ready(self) -> None:
        if not elysia_service.tree:
            logger.info("Initializing Elysia service for CAG adapter…")
            await elysia_service.initialize()

    async def _get_embedder(self) -> SentenceTransformer:
        if self._embedder:
            return self._embedder
        async with self._embedder_lock:
            if self._embedder:
                return self._embedder
            loop = asyncio.get_running_loop()
            logger.info("Loading SentenceTransformer model %s", self.embedding_model)
            self._embedder = await loop.run_in_executor(
                None, SentenceTransformer, self.embedding_model
            )
            return self._embedder

    async def process_query(self, request: CAGQueryRequest) -> CAGQueryResponse:
        await self._ensure_elysia_ready()

        elysia_request = ElysiaQuery(
            query=request.query,
            tenant_id=request.tenant_id,
            context=request.context or {},
        )
        response = await elysia_service.execute_query(elysia_request)

        return CAGQueryResponse(
            success=True,
            query=request.query,
            answer=response.answer,
            quality_score=response.confidence_score,
            iterations=response.iterations,
            gaps_identified=0,
            context_chunks_used=len(response.decision_path or []),
            execution_time=response.execution_time_ms / 1000 if response.execution_time_ms else 0.0,
            metadata={
                "session_id": response.session_id,
                "decision_path": response.decision_path,
                "tools_used": response.tools_used,
                "elysia": True,
            },
            error=None if response.answer else response.answer,
        )

    async def process_query_stream(
        self, request: CAGQueryRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "progress", "content": "Iniciando análisis", "progress": 10}
        result = await self.process_query(request)
        yield {
            "type": "result",
            "content": result.answer,
            "metadata": result.metadata,
        }
        yield {"type": "done"}

    async def analyze_document(
        self, request: DocumentAnalysisRequest
    ) -> DocumentAnalysisResponse:
        await self._ensure_elysia_ready()

        query = (
            f"Analiza el siguiente documento (tipo={request.analysis_type.value}) "
            f"y entrega hallazgos clave, riesgos y recomendaciones.\n\n"
            f"Documento:\n{request.document_content[:4000]}"
        )

        elysia_request = ElysiaQuery(
            query=query,
            tenant_id=request.tenant_id,
            context={
                "document_id": request.document_id,
                "analysis_type": request.analysis_type.value,
                "source": "cag_adapter",
            },
        )
        response = await elysia_service.execute_query(elysia_request)

        return DocumentAnalysisResponse(
            success=True,
            document_id=request.document_id,
            document_type=request.analysis_type.value,
            confidence=response.confidence_score,
            analysis_type=request.analysis_type.value,
            analysis=response.answer,
            quality_score=response.confidence_score,
            execution_time=response.execution_time_ms / 1000 if response.execution_time_ms else 0.0,
            metadata={
                "session_id": response.session_id,
                "decision_path": response.decision_path,
            },
        )

    async def analyze_document_stream(
        self, request: DocumentAnalysisRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "progress", "content": "Analizando documento", "progress": 5}
        result = await self.analyze_document(request)
        yield {"type": "result", "content": result.analysis, "metadata": result.metadata}
        yield {"type": "done"}

    async def generate_embeddings(self, texts: List[str]) -> Dict[str, Any]:
        embedder = await self._get_embedder()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, embedder.encode, texts)
        return {
            "success": True,
            "embeddings": embeddings.tolist() if hasattr(embeddings, "tolist") else embeddings,
            "count": len(texts),
            "model": self.embedding_model,
        }

    async def get_agents_info(self) -> Dict[str, Any]:
        await self._ensure_elysia_ready()
        tools = await elysia_service.list_tools()
        return {
            "total": len(tools),
            "available_types": {tool["category"]: tool["name"] for tool in tools},
            "tools": tools,
        }

    async def health(self) -> Dict[str, Any]:
        await self._ensure_elysia_ready()
        return {
            "status": "healthy" if elysia_service.tree else "initializing",
            "service": "cag-adapter",
            "checks": {
                "elysia_tree": elysia_service.tree is not None,
                "tools_registered": elysia_service.tools_registered,
                "collections_preprocessed": elysia_service.collections_preprocessed,
                "embedding_model_loaded": self._embedder is not None,
            },
        }

    async def execute_task_stream(
        self, request: TaskExecutionRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        synthetic_query = (
            f"Ejecuta la siguiente tarea para el usuario: {request.task_description}."
        )
        if request.expected_output:
            synthetic_query += f"\nEl resultado esperado es: {request.expected_output}."

        cag_request = CAGQueryRequest(
            query=synthetic_query,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            context=request.context,
        )
        async for chunk in self.process_query_stream(cag_request):
            yield chunk


cag_adapter = CAGAdapter()
