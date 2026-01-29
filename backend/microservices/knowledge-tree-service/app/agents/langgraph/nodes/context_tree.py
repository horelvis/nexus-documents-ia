"""
CONTEXT_TREE Node - Repository structure context for Emma

Fetches a lightweight folder/document tree summary via structural_query
so the LLM has repository context even when Weaviate doesn't index everything.
"""

import logging
import os
import time
from typing import Any, Dict

from ..state import RAGState
from ..reasoning_tracker import ReasoningTracker, StepType

logger = logging.getLogger(__name__)

# Configurable query for structural tree context
DEFAULT_TREE_QUERY = os.getenv(
    "CONTEXT_TREE_QUERY",
    "Muestra la estructura de carpetas y expedientes principales con conteos."
)
DEFAULT_TREE_MAX_RESULTS = int(os.getenv("CONTEXT_TREE_MAX_RESULTS", "50"))


async def context_tree_node(state: RAGState) -> Dict[str, Any]:
    """
    Fetch repository tree context via structural_query.
    Skips for conversational/identity intents.
    """
    start_time = time.time()
    tenant_id = state.get("tenant_id", "")

    intent = state.get("metadata", {}).get("coordinator_intent", "document_query")
    if intent in {"conversational", "identity"}:
        return {
            "metadata": {
                **state.get("metadata", {}),
                "context_tree_skipped": True,
                "context_tree_skip_reason": f"intent:{intent}",
            }
        }

    if not tenant_id:
        logger.warning("CONTEXT_TREE: missing tenant_id, skipping")
        return {
            "metadata": {
                **state.get("metadata", {}),
                "context_tree_skipped": True,
                "context_tree_skip_reason": "missing_tenant_id",
            }
        }

    with ReasoningTracker.create() as tracker:
        tracker.set_source("context_tree")
        tracker.add_step(
            StepType.QUERY_ANALYSIS,
            "Recopilando contexto estructural (árbol de carpetas)"
        )

        try:
            from app.clients.weaviate_client import get_weaviate_client
            from app.services.tenant_knowledge_service import get_tenant_knowledge_service

            client = get_weaviate_client()
            knowledge_service = get_tenant_knowledge_service()
            await knowledge_service.initialize()

            terminology = await knowledge_service.get_structural_summary(
                tenant_id=tenant_id
            )

            result = await client.structural_query(
                tenant_id=tenant_id,
                query=DEFAULT_TREE_QUERY,
                max_results=DEFAULT_TREE_MAX_RESULTS,
            )

            latency_ms = (time.time() - start_time) * 1000

            if result.route == "ERROR":
                error_msg = result.data.get("error", "Unknown error")
                tracker.add_error_step(error_msg)
                logger.warning(f"CONTEXT_TREE: structural_query error: {error_msg}")
                return {
                    "metadata": {
                        **state.get("metadata", {}),
                        "context_tree_error": error_msg,
                        "context_tree_latency_ms": latency_ms,
                    },
                    "reasoning_steps": tracker.get_steps(),
                }

            # Build a compact summary for LLM context
            summary = ""
            if terminology:
                summary += terminology.strip()
                summary += "\n\n"
            summary += result.context or ""
            data = result.data or {}

            if data.get("folders"):
                summary += "\n\nCarpetas principales:\n"
                for folder in data["folders"][:10]:
                    name = folder.get("name", folder.get("title", "Sin nombre"))
                    count = folder.get("document_count", folder.get("count", ""))
                    line = f"- {name}"
                    if count:
                        line += f" ({count} documentos)"
                    summary += line + "\n"

            tracker.add_step(
                StepType.DATA_EXTRACTION,
                "Contexto estructural recopilado",
                confidence=result.confidence,
            )

            return {
                "metadata": {
                    **state.get("metadata", {}),
                    "context_tree_summary": summary.strip(),
                    "context_tree_latency_ms": latency_ms,
                    "context_tree_route": result.route,
                    "context_tree_terminology": terminology or "",
                },
                "reasoning_steps": tracker.get_steps(),
            }

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"CONTEXT_TREE: failed: {e}")
            tracker.add_error_step(str(e))
            return {
                "metadata": {
                    **state.get("metadata", {}),
                    "context_tree_error": str(e),
                    "context_tree_latency_ms": latency_ms,
                },
                "reasoning_steps": tracker.get_steps(),
            }
