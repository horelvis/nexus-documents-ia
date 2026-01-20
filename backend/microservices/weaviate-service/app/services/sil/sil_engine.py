"""
Structural Intelligence Layer Engine

The main entry point for the SIL.
Orchestrates all components to process queries with structural intelligence.

Usage:
    from app.services.sil import sil_engine

    # Process a query
    result = await sil_engine.process_query(
        query="How many contracts does ACME have?",
        tenant_id="tenant-123",
    )

    # Check if we can answer without RAG
    if not result.reasoning_result.requires_rag:
        # Answer directly from structural context
        context = result.reasoning_result.structural_context.to_context_string()
    else:
        # Use focused RAG with target documents
        target_docs = result.reasoning_result.target_document_ids
"""

import logging
import time
from typing import Optional, Dict, Any

from .schemas import (
    StructuralQueryResult,
    ReasoningResult,
    ReasoningType,
    Intent,
)
from .intent_detector import IntentDetector, intent_detector
from .pre_llm_reasoning import PreLLMReasoningEngine, pre_llm_engine
from .temporal_reasoning import TemporalReasoningEngine, temporal_engine
from .multihop_planner import MultiHopQueryPlanner, multihop_planner
from .multihop_executor import MultiHopExecutor, multihop_executor
from ...core.config import settings

logger = logging.getLogger(__name__)


class SILEngine:
    """
    Structural Intelligence Layer Engine.

    The main orchestrator that:
    1. Detects query intent
    2. Routes to appropriate reasoning engine
    3. Returns structural context and/or target documents
    4. Estimates token savings

    This engine is the gateway between user queries and the RAG pipeline,
    determining what can be answered structurally vs. what needs content.
    """

    def __init__(
        self,
        detector: Optional[IntentDetector] = None,
        reasoning_engine: Optional[PreLLMReasoningEngine] = None,
        temporal_engine_instance: Optional[TemporalReasoningEngine] = None,
        planner: Optional[MultiHopQueryPlanner] = None,
        executor: Optional[MultiHopExecutor] = None,
    ):
        self._detector = detector or intent_detector
        self._reasoning_engine = reasoning_engine or pre_llm_engine
        self._temporal_engine = temporal_engine_instance or temporal_engine
        self._planner = planner or multihop_planner
        self._executor = executor or multihop_executor
        self._initialized = False

        # Token estimation (approximate)
        self._avg_doc_tokens = 1500  # Average tokens per document
        self._structural_context_tokens = 200  # Approximate structural context size

    async def initialize(self) -> None:
        """Initialize all SIL components."""
        if self._initialized:
            return

        await self._detector.initialize()
        await self._reasoning_engine.initialize()
        await self._temporal_engine.initialize()
        await self._planner.initialize()
        await self._executor.initialize()

        self._initialized = True
        logger.info("✅ SILEngine initialized")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
    ) -> StructuralQueryResult:
        """
        Process a query through the Structural Intelligence Layer.

        This is the main entry point for SIL. It:
        1. Detects the query intent
        2. Determines if structural reasoning can answer it
        3. Returns structural context and/or target documents for RAG

        Args:
            query: The user's query
            tenant_id: Tenant identifier

        Returns:
            StructuralQueryResult with intent, context, and RAG guidance
        """
        start_time = time.time()
        await self.initialize()

        breakdown = {}

        try:
            # Step 1: Detect intent
            intent_start = time.time()
            intent = await self._detector.detect_intent(query)
            breakdown["intent_detection_ms"] = (time.time() - intent_start) * 1000

            logger.info(
                f"🧠 SIL Processing: '{query[:50]}...' "
                f"→ Intent: {intent.type.value} (confidence: {intent.confidence:.2f})"
            )

            # Step 2: Process through reasoning engine
            reasoning_start = time.time()
            reasoning_result = await self._reasoning_engine.process_query(
                query=query,
                tenant_id=tenant_id,
            )
            breakdown["reasoning_ms"] = (time.time() - reasoning_start) * 1000

            # Step 3: Build final result
            total_time = (time.time() - start_time) * 1000

            # Estimate token savings
            tokens_saved = self._estimate_token_savings(reasoning_result)

            # Generate answer if fully structural
            answer = None
            answer_confidence = 0.0
            if reasoning_result.type == ReasoningType.STRUCTURAL:
                answer = self._generate_structural_answer(intent, reasoning_result)
                answer_confidence = intent.confidence * 0.9

            # Build context string for LLM
            context_for_llm = None
            if reasoning_result.structural_context:
                context_for_llm = reasoning_result.structural_context.to_context_string()

            result = StructuralQueryResult(
                original_query=query,
                detected_intent=intent,
                reasoning_result=reasoning_result,
                answer=answer,
                answer_confidence=answer_confidence,
                context_for_llm=context_for_llm,
                tokens_saved=tokens_saved,
                total_processing_time_ms=total_time,
                breakdown=breakdown,
                success=True,
            )

            # Log summary
            self._log_summary(result)

            return result

        except Exception as e:
            logger.error(f"SIL processing failed: {e}")
            return StructuralQueryResult(
                original_query=query,
                detected_intent=Intent(),
                reasoning_result=ReasoningResult(type=ReasoningType.FULL_RAG),
                total_processing_time_ms=(time.time() - start_time) * 1000,
                breakdown=breakdown,
                success=False,
                error=str(e),
            )

    def _estimate_token_savings(self, result: ReasoningResult) -> int:
        """
        Estimate tokens saved by using structural reasoning.

        Compares:
        - Full RAG: Would retrieve N documents × avg tokens per doc
        - Structural: Only structural context tokens

        Returns estimated tokens saved.
        """
        if result.type == ReasoningType.FULL_RAG:
            return 0

        # Estimate what full RAG would have cost
        estimated_docs = 10  # Typical RAG retrieves 10 docs
        full_rag_tokens = estimated_docs * self._avg_doc_tokens

        if result.type == ReasoningType.STRUCTURAL:
            # No documents retrieved
            actual_tokens = self._structural_context_tokens
        elif result.type == ReasoningType.FOCUSED_RAG:
            # Only target documents
            focused_docs = len(result.target_document_ids)
            actual_tokens = (
                focused_docs * self._avg_doc_tokens
                + self._structural_context_tokens
            )
        else:
            # Hybrid or temporal
            actual_tokens = full_rag_tokens // 2

        return max(full_rag_tokens - actual_tokens, 0)

    def _generate_structural_answer(
        self,
        intent: Intent,
        result: ReasoningResult,
    ) -> Optional[str]:
        """
        Generate a direct answer for purely structural queries.

        This is used when LLM interpretation is optional because
        the answer is a simple count, list, or boolean.
        """
        if not result.structural_context:
            return None

        ctx = result.structural_context
        qr = ctx.query_result

        # Count queries
        if ctx.query_type == "count":
            count = qr.get("count", ctx.document_count)
            if intent.entities.document_types:
                doc_type = intent.entities.document_types[0].value
                return f"Hay {count} {doc_type}(s)."
            return f"Se encontraron {count} documentos."

        # Exists queries
        if ctx.query_type == "exists":
            exists = qr.get("exists", ctx.document_count > 0)
            if exists:
                count = qr.get("count", ctx.document_count)
                return f"Sí, se encontraron {count} documentos."
            return "No se encontraron documentos que coincidan."

        # Location queries
        if ctx.query_type == "location":
            if ctx.folder_path:
                return f"El documento se encuentra en: {ctx.folder_path}"
            if ctx.folder_hierarchy:
                return f"Documentos encontrados en: {', '.join(ctx.folder_hierarchy[:3])}"

        # For complex results, let LLM interpret
        return None

    def _log_summary(self, result: StructuralQueryResult) -> None:
        """Log a summary of SIL processing."""
        reasoning = result.reasoning_result

        summary_parts = [
            f"  Type: {reasoning.type.value}",
            f"  Requires RAG: {reasoning.requires_rag}",
            f"  Time: {result.total_processing_time_ms:.0f}ms",
        ]

        if result.tokens_saved > 0:
            summary_parts.append(f"  Tokens saved: ~{result.tokens_saved}")

        if reasoning.type == ReasoningType.FOCUSED_RAG:
            summary_parts.append(
                f"  Target docs: {len(reasoning.target_document_ids)}"
            )

        if result.answer:
            summary_parts.append(f"  Direct answer: {result.answer[:50]}...")

        logger.info("📊 SIL Summary:\n" + "\n".join(summary_parts))

    async def get_structural_stats(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get statistics about the structural graph for a tenant.

        Useful for monitoring and debugging.
        """
        await self.initialize()

        try:
            from .cypher_builder import cypher_builder

            cypher = cypher_builder.build_graph_stats_query(tenant_id)

            # Execute via reasoning engine
            async with self._reasoning_engine._graph._get_connection() as conn:
                results = await self._reasoning_engine._graph._execute_cypher(
                    conn,
                    cypher,
                    [
                        ("total_documents", "agtype"),
                        ("unique_types", "agtype"),
                        ("unique_domains", "agtype"),
                        ("unique_folders", "agtype"),
                    ],
                )

                if results:
                    return {
                        "tenant_id": tenant_id,
                        "total_documents": results[0].get("total_documents", 0),
                        "unique_types": results[0].get("unique_types", 0),
                        "unique_domains": results[0].get("unique_domains", 0),
                        "unique_folders": results[0].get("unique_folders", 0),
                        "sil_enabled": True,
                    }

                return {
                    "tenant_id": tenant_id,
                    "sil_enabled": True,
                    "note": "No structural data found",
                }

        except Exception as e:
            logger.error(f"Failed to get structural stats: {e}")
            return {
                "tenant_id": tenant_id,
                "sil_enabled": True,
                "error": str(e),
            }


# Global singleton instance
sil_engine = SILEngine()
