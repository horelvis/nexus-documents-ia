"""
Predictive Analysis Tool — Sub-graph invoked from the ReAct agent.

Extracts legal/business factors from source documents, evaluates
evidence for each, and synthesizes a probabilistic recommendation.
"""

import logging
import time
from typing import Any, Dict, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class PredictiveAnalysisInput(BaseModel):
    """Input for predictive analysis."""
    query: str = Field(
        description="Descripcion del caso para analizar predictivamente. "
        "Incluye los hechos clave, contexto y la pregunta juridica o empresarial."
    )
    source_document_ids: list[str] = Field(
        default_factory=list,
        description="IDs de documentos fuente para el analisis. "
        "Si se proporcionan archivos subidos, se usan esos."
    )


class PredictiveAnalysisTool(EmmaTool):
    """Analyze a legal/business case and predict likely outcomes.

    Runs the PredictiveGraph sub-graph: extracts factors, evaluates
    evidence, and synthesizes a recommendation with confidence scores.
    """

    @property
    def name(self) -> str:
        return "predictive_analysis"

    @property
    def description(self) -> str:
        return (
            "Analisis predictivo de un caso juridico o empresarial. "
            "Extrae factores relevantes, evalua evidencia a favor y en contra, "
            "y genera una recomendacion con probabilidades. "
            "Usa esta herramienta cuando el usuario pida predecir resultados, "
            "evaluar riesgos, o analizar probabilidades de un caso."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return PredictiveAnalysisInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        start = time.time()

        query = arguments["query"]
        source_document_ids = arguments.get("source_document_ids", [])

        tenant_id = context.get("tenant_id", "")
        user_id = context.get("user_id")
        emit_sse = context.get("emit_sse")

        uploaded_texts = context.get("uploaded_texts", [])
        collections = context.get("collections", [])
        context_document_ids = context.get("context_document_ids", [])

        from app.agents.langgraph.subgraphs.predictive.state import create_predictive_state
        from app.agents.langgraph.subgraphs.predictive.graph import get_predictive_graph

        initial_state = create_predictive_state(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            max_factors=context.get("max_factors", 10),
            confidence_threshold=context.get("confidence_threshold", 0.7),
            uploaded_texts=uploaded_texts,
            collections=collections,
            context_document_ids=context_document_ids or source_document_ids,
            mode_config=context.get("mode_config", {}),
        )

        graph = get_predictive_graph()

        events_seen = 0
        final_state = initial_state

        try:
            async for snapshot in graph.astream(initial_state, stream_mode="values"):
                final_state = snapshot
                all_events = snapshot.get("pending_events", [])
                if emit_sse and len(all_events) > events_seen:
                    for event in all_events[events_seen:]:
                        emit_sse(event)
                    events_seen = len(all_events)
        except Exception as e:
            logger.error(f"Predictive analysis sub-graph failed: {e}")
            return ToolResult.from_error(
                f"Error en analisis predictivo: {e}",
                suggestion="Intenta con una descripcion de caso mas detallada.",
            )

        latency_ms = (time.time() - start) * 1000

        result = final_state.get("result")
        if not result or result.get("error"):
            error = result.get("error", "Sin resultado") if result else "Sin resultado"
            return ToolResult.from_error(f"Analisis predictivo fallido: {error}")

        # Build human-readable output for the ReAct agent
        recommendation = result.get("recommendation", "")
        probability = result.get("probability", 0)
        primary_outcome = result.get("primary_outcome_label", result.get("primary_outcome", ""))

        output = (
            f"**Resultado del analisis predictivo:**\n\n"
            f"**Resultado probable:** {primary_outcome} ({probability:.0%})\n\n"
            f"**Recomendacion:** {recommendation}\n\n"
            f"Factores analizados: {result.get('factors_weighted', 0)} aceptados, "
            f"{result.get('factors_rejected', 0)} rechazados."
        )

        return ToolResult(
            output=output,
            sources=result.get("sources", []),
            data={
                "session_id": final_state.get("session_id"),
                "probability": probability,
                "primary_outcome": primary_outcome,
                "recommendation": recommendation,
                "factors_weighted": result.get("factors_weighted", 0),
                "factors_rejected": result.get("factors_rejected", 0),
                "latency_ms": latency_ms,
            },
        )
