"""
High-level helper that routes all text generation tasks through Elysia/CAG.
Replaces the legacy LLMService that talked directly to Ollama/OpenAI.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.services.cag_client import cag_client

logger = logging.getLogger(__name__)


class ElysiaInsightsService:
    """Wrapper around CAG/Elysia for common insight tasks (summaries, tags, metadata)."""

    def __init__(self, default_tenant: Optional[str] = None, default_user: str = "system"):
        self.default_tenant = default_tenant or settings.DEFAULT_TENANT
        self.default_user = default_user

    async def _ask(
        self,
        prompt: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.3,
        max_iterations: int = 4,
    ) -> Dict[str, Any]:
        """Execute a generic query via CAG/Elysia and return the raw JSON response."""
        tenant = tenant_id or self.default_tenant
        user = user_id or self.default_user
        result = await cag_client.query(
            query=prompt,
            tenant_id=str(tenant),
            user_id=str(user),
            context=context,
            temperature=temperature,
            max_iterations=max_iterations,
        )
        if not result.get("success"):
            error = result.get("error") or "Elysia query failed"
            logger.warning("Elysia query failed | tenant=%s user=%s error=%s", tenant, user, error)
            raise RuntimeError(error)
        return result

    async def generate_response(
        self,
        query: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """General-purpose RAG response with optional document scoping."""
        ctx = context.copy() if context else {}
        if doc_ids:
            ctx["doc_ids"] = doc_ids
        result = await self._ask(
            query,
            tenant_id=tenant_id,
            user_id=user_id,
            context=ctx,
            temperature=0.4,
            max_iterations=5,
        )
        metadata = result.get("metadata") or {}
        sources = metadata.get("documents") or metadata.get("debug", {}).get("documents", [])
        return {
            "answer": result.get("answer", ""),
            "sources": sources,
            "metadata": metadata,
            "quality_score": result.get("quality_score"),
            "iterations": result.get("iterations"),
            "success": result.get("success", True),
        }

    async def summarize_text(
        self,
        text: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        max_length: int = 220,
        filename: Optional[str] = None,
    ) -> str:
        """Generate a concise summary for UI previews."""
        trimmed_text = text[:5000] if len(text) > 5000 else text
        prompt = (
            f"Genera un resumen conciso (máx {max_length} palabras) del siguiente documento.\n"
            f"Archivo: {filename or 'documento'}\n\n{trimmed_text}"
        )
        try:
            result = await self._ask(
                prompt,
                tenant_id=tenant_id,
                user_id=user_id,
                context={"task": "document_summary", "filename": filename},
                temperature=0.2,
            )
            summary = (result.get("answer") or "").strip()
            if max_length and len(summary) > max_length:
                summary = summary[:max_length].rstrip() + "…"
            return summary
        except Exception as exc:
            logger.warning("Summary generation failed: %s", exc)
            return trimmed_text[:max_length] if trimmed_text else ""

    async def suggest_tags(
        self,
        text: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        num_tags: int = 5,
    ) -> List[str]:
        """Suggest descriptive tags for a text snippet."""
        prompt = (
            f"Analiza el siguiente texto y sugiere {num_tags} etiquetas relevantes. "
            "Devuelve solo las etiquetas separadas por comas, sin explicación adicional.\n\n"
            f"Texto:\n{text[:2000]}"
        )
        try:
            result = await self._ask(
                prompt,
                tenant_id=tenant_id,
                user_id=user_id,
                context={"task": "suggest_tags"},
                temperature=0.2,
                max_iterations=3,
            )
            raw = (result.get("answer") or "").strip()
            tags = [tag.strip() for tag in raw.split(",") if tag.strip()]
            return tags[:num_tags]
        except Exception as exc:
            logger.warning("Tag suggestion failed: %s", exc)
            return []

    async def extract_metadata(
        self,
        text: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract structured metadata (title, date, etc.) from text."""
        prompt = (
            "Extrae metadatos clave del siguiente texto y responde únicamente con un JSON "
            "válido que incluya campos como title, author, date, category, language.\n\n"
            f"Texto:\n{text[:4000]}"
        )
        try:
            result = await self._ask(
                prompt,
                tenant_id=tenant_id,
                user_id=user_id,
                context={"task": "extract_metadata"},
                temperature=0.1,
                max_iterations=3,
            )
            answer = result.get("answer") or "{}"
            return json.loads(answer)
        except json.JSONDecodeError as exc:
            logger.warning("Metadata JSON parse failed: %s", exc)
            return {"extracted_text": answer}
        except Exception as exc:
            logger.warning("Metadata extraction failed: %s", exc)
            return {}
