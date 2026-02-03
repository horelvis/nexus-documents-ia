"""Emma Background Service — Proactive LangGraph execution without HTTP.

This service allows Emma to run analyses triggered by events, schedules,
or background tasks — without requiring a user HTTP request.

It reuses the existing LangGraph graph and Emma service, providing
a simplified interface for background invocations.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmmaBackgroundService:
    """Orchestrates proactive Emma executions from background tasks."""

    async def analyze_document(
        self,
        document_id: str,
        tenant_id: str,
        prompt_template: Optional[str] = None,
        agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run Emma analysis on a newly indexed document.

        Args:
            document_id: The document to analyze
            tenant_id: Tenant context
            prompt_template: Custom prompt (may use {document_title} etc.)
            agent: Specific specialist agent to use
            metadata: Additional context (title, collection, tags, etc.)
        """
        metadata = metadata or {}
        title = metadata.get("title", document_id)

        # Build the query
        if prompt_template:
            query = prompt_template.format(
                document_title=title,
                document_id=document_id,
                **metadata,
            )
        else:
            query = f"Analiza el documento '{title}' y proporciona un resumen con los puntos clave."

        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            agent=agent,
            context={
                "background_task": True,
                "document_id": document_id,
                "trigger_type": "document_analysis",
            },
        )

    async def generate_daily_summary(
        self,
        tenant_id: str,
        collections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate a daily summary of recent activity for a tenant."""
        query = (
            "Genera un resumen ejecutivo de la actividad reciente: "
            "documentos nuevos, cambios importantes, y cualquier alerta relevante."
        )
        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            context={
                "background_task": True,
                "trigger_type": "daily_summary",
                "collections": collections or [],
            },
        )

    async def proactive_analysis(
        self,
        tenant_id: str,
        analysis_type: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a custom proactive analysis."""
        return await self._execute_emma(
            query=query,
            tenant_id=tenant_id,
            context={
                "background_task": True,
                "trigger_type": "proactive_analysis",
                "analysis_type": analysis_type,
                **(context or {}),
            },
        )

    async def _execute_emma(
        self,
        query: str,
        tenant_id: str,
        agent: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a query through the LangGraph pipeline."""
        session_id = f"bg-{uuid.uuid4().hex[:12]}"

        try:
            from app.services.emma_service import emma_service
            from app.schemas.emma import EmmaQuery

            emma_query = EmmaQuery(
                query=query,
                tenant_id=tenant_id,
                session_id=session_id,
                context=context or {},
                enable_learning=False,
                enable_debug=False,
            )

            response = await emma_service.execute_query(emma_query)

            # Extract sources from data.sources or data.references if available
            sources = []
            if response and response.data:
                sources = response.data.get("sources", response.data.get("references", []))

            return {
                "success": True,
                "session_id": session_id,
                "answer": response.answer if response else "Sin respuesta",
                "confidence_score": response.confidence_score if response else None,
                "sources_count": len(sources) if sources else 0,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Background Emma execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "session_id": session_id,
                "error": str(e),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }


# Global singleton
emma_background_service = EmmaBackgroundService()
