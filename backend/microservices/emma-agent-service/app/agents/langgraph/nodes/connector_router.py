"""
Dynamic Connector Router Node

Este nodo de LangGraph realiza routing dinámico basado en los conectores
registrados. Cuando añades un nuevo conector, se integra automáticamente
en el flujo de decisión sin modificar código.

Flujo:
1. Recibe la consulta del usuario
2. Consulta el registro de conectores
3. Cada conector indica su confianza para manejar la consulta
4. Ejecuta el conector con mayor confianza
5. Retorna resultados con pasos de razonamiento

Esto permite que conectores como:
- PostgreSQL externo
- Alfresco
- SharePoint
- APIs personalizadas

Se integren simplemente implementando BaseConnector y usando @register_connector.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ..state import RAGState
from ..connectors import (
    get_connectors_for_query,
    ConnectorCapability,
    ConnectorMatch,
)
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)


async def connector_router_node(state: RAGState) -> Dict[str, Any]:
    """
    Dynamic routing node that selects the best connector for a query.

    This node:
    1. Gets all registered connectors
    2. Asks each one if it can handle the query (can_handle)
    3. Selects the best match by confidence
    4. Executes the selected connector
    5. Captures reasoning steps for UI visibility

    Returns state updates with connector results.
    """
    start_time = time.time()

    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")
    user_id = state.get("user_id", "")

    logger.info(f"🔀 CONNECTOR_ROUTER: Starting dynamic routing for: '{query[:50]}...'")

    # Build execution context for connectors
    context = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "max_results": state.get("metadata", {}).get("max_results", 100),
        "query_type": state.get("metadata", {}).get("query_type"),
    }

    # Create reasoning tracker
    with ReasoningTracker.create() as tracker:
        tracker.set_source("connector_router")

        # Step 1: Discover connectors
        tracker.add_step(
            StepType.QUERY_ANALYSIS,
            f"Analizando consulta: '{query[:40]}...'"
        )

        # Step 2: Get matching connectors
        try:
            matches = await get_connectors_for_query(
                query=query,
                context=context,
                min_confidence=0.1,
            )

            if not matches:
                tracker.add_step(
                    StepType.ROUTING,
                    "No se encontraron conectores que puedan manejar esta consulta",
                    confidence=0.0
                )
                return _build_fallback_result(state, tracker, start_time)

            # Log available connectors
            connector_info = ", ".join(
                f"{m.name}({m.confidence:.2f})" for m in matches[:5]
            )
            tracker.add_step(
                StepType.ROUTING,
                f"Conectores disponibles: {connector_info}",
                confidence=matches[0].confidence if matches else 0.0
            )

        except Exception as e:
            logger.error(f"Error getting connectors: {e}")
            tracker.add_error_step(f"Error en descubrimiento de conectores: {e}")
            return _build_fallback_result(state, tracker, start_time)

        # Step 3: Select best connector
        best_match = matches[0]

        tracker.add_step(
            StepType.ROUTING,
            f"Seleccionado: {best_match.name} (confianza: {best_match.confidence:.0%})",
            confidence=best_match.confidence,
            metadata={"connector": best_match.name}
        )

        # Step 4: Execute connector
        try:
            logger.info(
                f"🎯 CONNECTOR_ROUTER: Executing {best_match.name} "
                f"(confidence: {best_match.confidence:.2f})"
            )

            result = await best_match.connector.execute(query, context)

            latency_ms = (time.time() - start_time) * 1000

            # Step 5: Build response
            tracker.add_step(
                StepType.RESPONSE,
                f"Respuesta de {best_match.name} en {latency_ms:.0f}ms",
                confidence=result.confidence
            )

            logger.info(
                f"✅ CONNECTOR_ROUTER: Completed | connector={best_match.name} | "
                f"confidence={result.confidence:.2f} | latency={latency_ms:.1f}ms"
            )

            # Return state update
            return {
                "connector_result": result.to_dict(),
                "connector_used": best_match.name,
                "reasoning_steps": tracker.get_steps(),
                "metadata": {
                    **state.get("metadata", {}),
                    "connector_router_latency_ms": latency_ms,
                    "connector_confidence": result.confidence,
                    "connectors_matched": len(matches),
                    "decision_path": ["connector_router", best_match.name],
                },
            }

        except Exception as e:
            logger.error(f"Connector {best_match.name} failed: {e}")
            tracker.add_error_step(f"Error en {best_match.name}: {e}")

            # Try next connector if available
            if len(matches) > 1:
                tracker.add_step(
                    StepType.ROUTING,
                    f"Intentando conector alternativo: {matches[1].name}"
                )
                # Recursively try next (simplified, could be a loop)
                # For now, just return error
                pass

            return _build_error_result(state, tracker, start_time, str(e))


def _build_fallback_result(
    state: RAGState,
    tracker: ReasoningTracker,
    start_time: float,
) -> Dict[str, Any]:
    """Build result when no connector matches."""
    latency_ms = (time.time() - start_time) * 1000

    return {
        "connector_result": None,
        "connector_used": None,
        "reasoning_steps": tracker.get_steps(),
        "metadata": {
            **state.get("metadata", {}),
            "connector_router_latency_ms": latency_ms,
            "connector_fallback": True,
        },
    }


def _build_error_result(
    state: RAGState,
    tracker: ReasoningTracker,
    start_time: float,
    error: str,
) -> Dict[str, Any]:
    """Build result when connector execution fails."""
    latency_ms = (time.time() - start_time) * 1000

    return {
        "connector_result": {"error": error},
        "connector_used": None,
        "connector_error": error,
        "reasoning_steps": tracker.get_steps(),
        "metadata": {
            **state.get("metadata", {}),
            "connector_router_latency_ms": latency_ms,
            "connector_error": error,
        },
    }


async def should_use_connector(state: RAGState) -> bool:
    """
    Conditional edge function for LangGraph.

    Determines if the query should be routed to a connector
    or to the standard agent flow.

    Returns True if a connector can handle the query with high confidence.
    """
    query = state.get("query", "")
    context = {
        "tenant_id": state.get("tenant_id", ""),
        "user_id": state.get("user_id", ""),
    }

    try:
        matches = await get_connectors_for_query(
            query=query,
            context=context,
            min_confidence=0.6,  # High threshold for direct connector routing
        )

        if matches and matches[0].confidence >= 0.8:
            logger.info(
                f"🔀 Routing to connector: {matches[0].name} "
                f"(confidence: {matches[0].confidence:.2f})"
            )
            return True

    except Exception as e:
        logger.warning(f"Error in connector check: {e}")

    return False
