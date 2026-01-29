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

    if state.get("metadata", {}).get("uploaded_texts") or state.get("metadata", {}).get("uploaded_file_ids"):
        return {
            "metadata": {
                **state.get("metadata", {}),
                "context_tree_skipped": True,
                "context_tree_skip_reason": "uploaded_context",
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
            from app.clients import get_knowledge_tree_client

            client = get_knowledge_tree_client()
            result = await client.get_tree_context(
                tenant_id=tenant_id,
                limit=DEFAULT_TREE_MAX_RESULTS,
            )

            latency_ms = (time.time() - start_time) * 1000

            if not result or not result.get("success", False):
                error_msg = result.get("metadata", {}).get("error", "Unknown error")
                tracker.add_error_step(error_msg)
                logger.warning(f"CONTEXT_TREE: knowledge-tree-service error: {error_msg}")
                return {
                    "metadata": {
                        **state.get("metadata", {}),
                        "context_tree_error": error_msg,
                        "context_tree_latency_ms": latency_ms,
                    },
                    "reasoning_steps": tracker.get_steps(),
                }

            # Build a compact summary for LLM context
            summary = result.get("context_for_llm", "")

            tracker.add_step(
                StepType.DATA_EXTRACTION,
                "Contexto estructural recopilado",
                confidence=0.9,
            )

            return {
                "metadata": {
                    **state.get("metadata", {}),
                    "context_tree_summary": summary.strip(),
                    "context_tree_latency_ms": latency_ms,
                    "context_tree_route": "KNOWLEDGE_TREE",
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
