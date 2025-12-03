"""CAG Service facade built directly on top of Elysia + Weaviate."""
from typing import Dict, Any, Optional, List, AsyncGenerator
from loguru import logger
import httpx

from ...services.elysia_service import elysia_service
from ...services.weaviate_service import weaviate_service
from ...schemas.elysia import ElysiaQuery, QueryType
from ..core.config import settings


class CAGService:
    """Expose legacy /api/v1/cag endpoints while delegating all logic to Elysia."""

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        await self._ensure_initialized()

    async def _ensure_initialized(self):
        if not self._initialized:
            await weaviate_service.initialize()
            await elysia_service.initialize()
            self._initialized = True
            logger.info("✅ CAGService bridged to Elysia + Weaviate")

    def _map_response(self, response) -> Dict[str, Any]:
        debug_data = response.data if isinstance(response.data, dict) else {}
        context_chunks = debug_data.get("documents_context", 0)
        gaps_identified = debug_data.get("gaps_identified", 0)
        metadata: Dict[str, Any] = {
            "decision_path": response.decision_path,
            "tools_used": response.tools_used,
        }
        if debug_data:
            metadata["debug"] = debug_data
        if response.visualization:
            metadata["visualization"] = response.visualization

        return {
            "success": True,
            "answer": response.answer,
            "quality_score": response.confidence_score,
            "iterations": response.iterations,
            "gaps_identified": gaps_identified,
            "context_chunks_used": context_chunks,
            "execution_time": response.execution_time_ms / 1000,
            "metadata": metadata,
        }

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
        await self._ensure_initialized()

        session_id = None
        merged_context = context or {}
        if isinstance(merged_context, dict):
            session_id = merged_context.get("conversation_id")

        elysia_query = ElysiaQuery(
            query=query,
            tenant_id=tenant_id,
            session_id=session_id,
            context=merged_context,
            query_type=QueryType.SEARCH,
            max_iterations=max_iterations or 3,
        )

        response = await elysia_service.execute_query(elysia_query)
        mapped = self._map_response(response)
        mapped["query"] = query
        mapped["metadata"]["user_id"] = user_id
        return mapped

    async def process_query_stream(
        self,
        query: str,
        tenant_id: str,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_initialized()
        yield {"type": "progress", "content": "Inicializando Elysia...", "progress": 10}
        result = await self.process_query(query, tenant_id, user_id, context)
        yield {"type": "result", "content": result}

    async def analyze_document(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive",
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        prompt = (
            f"Analiza el documento ({analysis_type}) y devuelve hallazgos clave, riesgos y recomendaciones.\n"
            f"Documento:\n{document_content}"
        )
        context = {
            "document_id": document_id,
            "analysis_type": analysis_type,
            "document_length": len(document_content),
        }
        elysia_query = ElysiaQuery(
            query=prompt,
            tenant_id=tenant_id,
            session_id=document_id,
            context=context,
            query_type=QueryType.ANALYZE,
            max_iterations=4,
        )
        response = await elysia_service.execute_query(elysia_query)
        mapped = self._map_response(response)
        return {
            "success": True,
            "document_id": document_id,
            "document_type": response.data.get("document_type") if isinstance(response.data, dict) else None,
            "confidence": mapped["quality_score"],
            "analysis_type": analysis_type,
            "analysis": mapped["answer"],
            "answer": mapped["answer"],
            "quality_score": mapped["quality_score"],
            "execution_time": mapped["execution_time"],
            "metadata": mapped["metadata"],
        }

    async def analyze_document_stream(
        self,
        document_content: str,
        document_id: str,
        tenant_id: str,
        user_id: str,
        analysis_type: str = "comprehensive",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_initialized()
        yield {"type": "progress", "content": "Analizando documento con Elysia...", "progress": 10}
        result = await self.analyze_document(
            document_content=document_content,
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            analysis_type=analysis_type,
        )
        yield {"type": "result", "content": result}

    async def chat(
        self,
        message: str,
        tenant_id: str,
        user_id: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        context = {"message_history": chat_history or []}
        return await self.process_query(message, tenant_id, user_id, context)

    async def generate_embeddings(
        self,
        texts: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._ensure_initialized()
        provider = settings.llm_provider
        target_model = (
            settings.openai_embedding_model if provider == "openai" else settings.embedding_model
        )
        if not target_model:
            raise ValueError("Embedding model is not configured")
        if provider == "openai" and not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")

        embeddings: List[List[float]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for text in texts:
                try:
                    if provider == "openai":
                        response = await client.post(
                            f"{settings.openai_base_url.rstrip('/')}/embeddings",
                            json={"model": target_model, "input": text},
                            headers={
                                "Authorization": f"Bearer {settings.openai_api_key}",
                                "Content-Type": "application/json",
                            },
                        )
                    else:
                        response = await client.post(
                            f"{settings.ollama_base_url}/api/embeddings",
                            json={"model": target_model, "prompt": text},
                        )
                    if response.status_code == 200:
                        data = response.json()
                        if provider == "openai":
                            rows = data.get("data") or []
                            embeddings.append(rows[0].get("embedding", []) if rows else [])
                        else:
                            embeddings.append(data.get("embedding", []))
                    else:
                        logger.warning(
                            f"⚠️ Embedding request failed ({provider}): {response.status_code}"
                        )
                        embeddings.append([])
                except Exception as exc:
                    logger.warning(f"⚠️ Could not generate embedding: {exc}")
                    embeddings.append([])

        return {
            "success": True,
            "embeddings": embeddings,
            "count": len(embeddings),
            "model": target_model,
            "tenant_id": tenant_id,
        }

    async def get_available_agents_info(self, tenant_id: str = "default") -> Dict[str, Any]:
        await self._ensure_initialized()
        tools = await elysia_service.list_tools()
        return {
            "service": "elysia",
            "tenant_id": tenant_id,
            "total": len(tools),
            "agents": tools,
        }

    async def health_check(self) -> Dict[str, Any]:
        await self._ensure_initialized()
        elysia_health = await elysia_service.health_check()
        return {
            "status": "healthy" if elysia_health.get("status") == "healthy" else "initializing",
            "service": "elysia",
            "checks": {
                "elysia_tree": elysia_health.get("tree_initialized", False),
                "tools_registered": elysia_health.get("tools_registered", False),
                "collections_preprocessed": elysia_health.get("collections_preprocessed", False),
            },
            "agents_count": elysia_health.get("active_sessions", 0),
        }


cag_service = CAGService()
