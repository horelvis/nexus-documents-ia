"""
Verified Generation Tool — Sub-graph invoked from the ReAct agent.

When the ReAct agent detects a "verified generation" intent (e.g., user asks
to generate a verified document), it calls this tool. The tool:

1. Builds initial VerifiedGenState from tool arguments
2. Streams the sub-graph with astream(stream_mode="values")
3. Drains pending_events from each snapshot → emits SSE via context callback
4. Returns ToolResult with the final document text
"""

import logging
import time
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class VerifiedGenerationInput(BaseModel):
    """Input for verified document generation."""
    query: str = Field(
        description="Tema o consulta para generar el documento verificado. "
        "Describe claramente qué tipo de documento necesitas."
    )
    source_document_ids: list[str] = Field(
        default_factory=list,
        description="IDs de documentos fuente para basar la generación. "
        "Si se proporcionan archivos subidos, se usan esos en su lugar."
    )
    auto_correct: bool = Field(
        default=True,
        description="Si True, las afirmaciones con baja confianza se corrigen automáticamente."
    )


class VerifiedGenerationTool(EmmaTool):
    """Generate a verified document claim-by-claim with two-tier verification.

    Runs the VerifiedGenGraph sub-graph internally. Each claim is generated
    from source documents, then verified for faithfulness (NLI) and
    corroborated with external evidence.

    SSE events (claim_generated, claim_verified, document_complete) are
    emitted via the emit_sse callback in the tool context.
    """

    @property
    def name(self) -> str:
        return "verified_generation"

    @property
    def description(self) -> str:
        return (
            "Genera un documento verificado claim-by-claim a partir de documentos fuente. "
            "Cada afirmación se verifica contra las fuentes originales y evidencia externa. "
            "Usa esta herramienta cuando el usuario pida generar un informe verificado, "
            "un documento académico, o cualquier texto que requiera verificación factual. "
            "Requiere documentos fuente (subidos por el usuario o IDs de documentos indexados)."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return VerifiedGenerationInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        start = time.time()

        query = arguments["query"]
        source_document_ids = arguments.get("source_document_ids", [])
        auto_correct = arguments.get("auto_correct", True)

        tenant_id = context.get("tenant_id", "")
        user_id = context.get("user_id")
        emit_sse = context.get("emit_sse")

        # Get uploaded texts from the execution context (passed by the API)
        uploaded_texts = context.get("uploaded_texts", [])
        collections = context.get("collections", [])
        context_document_ids = context.get("context_document_ids", [])

        if not uploaded_texts and not source_document_ids and not context_document_ids:
            return ToolResult.from_error(
                "No se han proporcionado documentos fuente. "
                "La generación verificada requiere al menos un documento.",
                suggestion="Sube un documento o proporciona source_document_ids.",
            )

        # Build initial state
        from app.agents.langgraph.subgraphs.verified_gen.state import create_verified_gen_state
        from app.agents.langgraph.subgraphs.verified_gen.graph import get_verified_gen_graph

        initial_state = create_verified_gen_state(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            max_claims=context.get("max_claims", 20),
            confidence_threshold=context.get("confidence_threshold", 0.7),
            auto_correct=auto_correct,
            uploaded_texts=uploaded_texts,
            collections=collections,
            context_document_ids=context_document_ids or source_document_ids,
            mode_config=context.get("mode_config", {}),
        )

        graph = get_verified_gen_graph()

        # Stream the sub-graph, draining SSE events from each snapshot
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
            logger.error(f"Verified generation sub-graph failed: {e}")
            return ToolResult.from_error(
                f"Error en generación verificada: {e}",
                suggestion="Intenta con un documento más corto o reformula la consulta.",
            )

        latency_ms = (time.time() - start) * 1000

        result = final_state.get("result")
        if not result or result.get("error"):
            error = result.get("error", "Sin resultado") if result else "Sin resultado"
            return ToolResult.from_error(f"Generación verificada fallida: {error}")

        document_text = result.get("document_text", "")
        if not document_text:
            return ToolResult.from_error("El documento generado está vacío.")

        return ToolResult(
            output=document_text,
            sources=result.get("sources", []),
            data={
                "session_id": final_state.get("session_id"),
                "claims_verified": result.get("claims_verified", 0),
                "claims_corrected": result.get("claims_corrected", 0),
                "claims_rejected": result.get("claims_rejected", 0),
                "average_confidence": result.get("average_confidence", 0),
                "doi_validations": result.get("doi_validations", []),
                "source_filenames": result.get("source_filenames", []),
                "latency_ms": latency_ms,
            },
        )
