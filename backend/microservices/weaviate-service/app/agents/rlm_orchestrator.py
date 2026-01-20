"""
RLM (Recursive Language Models) Orchestrator

Implements the RLM paradigm from arXiv:2512.24601 for processing
documents with "almost infinite" context through recursive decomposition.

Key concepts:
- Instead of truncating long contexts, decompose into sub-tasks
- Each sub-task processes a manageable chunk with full LLM attention
- Aggregate sub-results into a coherent final answer

Reference: Zhang, Kraska, Khattab (MIT/Stanford) - "RLM: Language Models Can Act as Recursive Interpreters"
Repository: https://github.com/alexzhang13/rlm
License: MIT
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from ..core.config import settings

logger = logging.getLogger(__name__)


class RLMTaskType(str, Enum):
    """Types of RLM sub-tasks"""

    EXTRACT = "extract"  # Extract specific information
    SUMMARIZE = "summarize"  # Summarize a section
    ANALYZE = "analyze"  # Analyze for specific criteria
    COMPARE = "compare"  # Compare sections
    AGGREGATE = "aggregate"  # Aggregate sub-results


@dataclass
class RLMSubTask:
    """A sub-task in the RLM decomposition"""

    task_id: str
    task_type: RLMTaskType
    query: str  # The sub-query to answer
    context_start: int  # Character offset start
    context_end: int  # Character offset end
    depth: int  # Recursion depth
    parent_task_id: Optional[str] = None
    result: Optional[str] = None
    tokens_processed: int = 0
    execution_time_ms: float = 0.0


@dataclass
class RLMResult:
    """Result from RLM processing"""

    final_answer: str
    sub_tasks: List[RLMSubTask]
    total_tokens_processed: int
    original_context_tokens: int
    recursion_depth_reached: int
    execution_time_ms: float
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RLMOrchestrator:
    """
    Recursive Language Model orchestrator for long documents.

    Decomposes complex queries into sub-tasks, processes recursively,
    and aggregates results to handle documents >50K tokens.

    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    RLM PROCESSING FLOW                       │
    ├─────────────────────────────────────────────────────────────┤
    │  Input (100K+ tokens) → Analyze if recursion needed          │
    │           ↓                                                  │
    │  Decompose into sub-tasks based on document structure        │
    │           ↓                                                  │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │  Sub-task 1: LLM(section_1) → result_1                 │ │
    │  │  Sub-task 2: LLM(section_2) → result_2                 │ │
    │  │  ...                                                    │ │
    │  │  (recursive if section still too large)                 │ │
    │  └─────────────────────────────────────────────────────────┘ │
    │           ↓                                                  │
    │  Aggregate: LLM(results[]) → Final Answer                    │
    └─────────────────────────────────────────────────────────────┘
    """

    def __init__(self):
        self._llm_client = None
        self._initialized = False
        # Configuration from settings
        self._threshold_tokens = settings.rlm_threshold_tokens
        self._max_recursion = settings.rlm_max_recursion_depth
        self._chunk_size = settings.rlm_chunk_size_tokens
        # Chars per token estimate
        self._chars_per_token = 4

    async def initialize(self):
        """Initialize the RLM orchestrator"""
        if self._initialized:
            return

        try:
            from .model_client import get_model_client

            self._llm_client = await get_model_client()
            self._initialized = True
            logger.info("✅ RLMOrchestrator initialized")

        except Exception as e:
            logger.error(f"❌ RLMOrchestrator initialization failed: {e}")
            raise

    async def process(
        self,
        query: str,
        context: str,
        tenant_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RLMResult:
        """
        Process a query against long context using RLM.

        Args:
            query: The user's query
            context: Full document context (can be 100K+ tokens)
            tenant_id: Tenant identifier
            metadata: Additional metadata

        Returns:
            RLMResult with aggregated answer and processing details
        """
        if not settings.rlm_enabled:
            # RLM disabled, return direct processing
            return await self._direct_process(query, context, tenant_id)

        await self.initialize()

        start_time = datetime.now()

        # Estimate token count
        context_tokens = self._estimate_tokens(context)
        logger.info(
            f"🔄 RLM processing: {context_tokens} tokens, "
            f"threshold: {self._threshold_tokens}"
        )

        # Check if recursion is needed
        if context_tokens < self._threshold_tokens:
            logger.info("  Context below threshold, using direct processing")
            return await self._direct_process(query, context, tenant_id)

        try:
            # Decompose into sub-tasks
            sub_tasks = await self._decompose_query(
                query=query,
                context=context,
                depth=0,
            )

            logger.info(f"  Decomposed into {len(sub_tasks)} sub-tasks")

            # Process each sub-task
            for task in sub_tasks:
                task_context = context[task.context_start : task.context_end]
                task.result = await self._process_subtask(
                    task=task,
                    context=task_context,
                    depth=task.depth,
                )
                task.tokens_processed = self._estimate_tokens(task_context)

            # Aggregate results
            final_answer = await self._aggregate_results(
                query=query,
                sub_tasks=sub_tasks,
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return RLMResult(
                final_answer=final_answer,
                sub_tasks=sub_tasks,
                total_tokens_processed=sum(t.tokens_processed for t in sub_tasks),
                original_context_tokens=context_tokens,
                recursion_depth_reached=max(t.depth for t in sub_tasks),
                execution_time_ms=execution_time,
                success=True,
                metadata={
                    "tenant_id": tenant_id,
                    "sub_task_count": len(sub_tasks),
                    **(metadata or {}),
                },
            )

        except Exception as e:
            logger.error(f"❌ RLM processing failed: {e}")
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return RLMResult(
                final_answer=f"Error processing: {str(e)}",
                sub_tasks=[],
                total_tokens_processed=0,
                original_context_tokens=context_tokens,
                recursion_depth_reached=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e),
            )

    async def _direct_process(
        self,
        query: str,
        context: str,
        tenant_id: str,
    ) -> RLMResult:
        """Direct processing without recursion (context fits in window)"""
        await self.initialize()

        start_time = datetime.now()
        context_tokens = self._estimate_tokens(context)

        try:
            # Truncate if needed for safety
            max_chars = self._chunk_size * self._chars_per_token
            truncated_context = context[:max_chars] if len(context) > max_chars else context

            prompt = self._build_answer_prompt(query, truncated_context)

            response = await self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.3,
            )

            answer = response.content if hasattr(response, "content") else str(response)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return RLMResult(
                final_answer=answer,
                sub_tasks=[],
                total_tokens_processed=context_tokens,
                original_context_tokens=context_tokens,
                recursion_depth_reached=0,
                execution_time_ms=execution_time,
                success=True,
                metadata={"direct_processing": True, "tenant_id": tenant_id},
            )

        except Exception as e:
            logger.error(f"❌ Direct processing failed: {e}")
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            return RLMResult(
                final_answer=f"Error: {str(e)}",
                sub_tasks=[],
                total_tokens_processed=0,
                original_context_tokens=context_tokens,
                recursion_depth_reached=0,
                execution_time_ms=execution_time,
                success=False,
                error=str(e),
            )

    async def _decompose_query(
        self,
        query: str,
        context: str,
        depth: int,
    ) -> List[RLMSubTask]:
        """
        Decompose a query into sub-tasks based on document structure.

        Uses LLM to analyze document structure and create appropriate
        sub-tasks for each section.
        """
        if depth >= self._max_recursion:
            # Max depth reached, process as single task
            return [
                RLMSubTask(
                    task_id=f"task_{depth}_0",
                    task_type=RLMTaskType.ANALYZE,
                    query=query,
                    context_start=0,
                    context_end=len(context),
                    depth=depth,
                )
            ]

        # Calculate chunk boundaries
        chunk_chars = self._chunk_size * self._chars_per_token
        num_chunks = (len(context) + chunk_chars - 1) // chunk_chars

        if num_chunks <= 1:
            # Single chunk, no decomposition needed
            return [
                RLMSubTask(
                    task_id=f"task_{depth}_0",
                    task_type=RLMTaskType.ANALYZE,
                    query=query,
                    context_start=0,
                    context_end=len(context),
                    depth=depth,
                )
            ]

        # Try to find natural boundaries (sections, paragraphs)
        boundaries = self._find_section_boundaries(context, num_chunks)

        sub_tasks = []
        for i, (start, end) in enumerate(boundaries):
            task_type = self._determine_task_type(query, i, len(boundaries))

            sub_tasks.append(
                RLMSubTask(
                    task_id=f"task_{depth}_{i}",
                    task_type=task_type,
                    query=self._create_subtask_query(query, task_type, i, len(boundaries)),
                    context_start=start,
                    context_end=end,
                    depth=depth,
                )
            )

        return sub_tasks

    def _find_section_boundaries(
        self,
        context: str,
        target_chunks: int,
    ) -> List[Tuple[int, int]]:
        """
        Find natural section boundaries for chunking.

        Prefers to split at:
        1. Markdown headers (##, ###)
        2. Legal section markers (CAPÍTULO, ARTÍCULO, CLÁUSULA)
        3. Double newlines (paragraph boundaries)
        4. Character boundaries (fallback)
        """
        import re

        # Section patterns (priority order)
        patterns = [
            r"\n#{1,3}\s+",  # Markdown headers
            r"\n(?:CAPÍTULO|ARTÍCULO|SECCIÓN|CLÁUSULA|TÍTULO)\s+",  # Legal sections
            r"\n\d+\.\d*\s+[A-ZÁÉÍÓÚ]",  # Numbered sections
            r"\n{2,}",  # Paragraph breaks
        ]

        # Find all potential boundaries
        all_positions = [0]  # Start of document

        for pattern in patterns:
            for match in re.finditer(pattern, context, re.MULTILINE):
                all_positions.append(match.start())

        all_positions.append(len(context))  # End of document
        all_positions = sorted(set(all_positions))

        # Select boundaries to achieve target_chunks
        if len(all_positions) <= target_chunks + 1:
            # Not enough natural boundaries, add character-based splits
            chunk_size = len(context) // target_chunks
            positions = []
            for i in range(target_chunks + 1):
                pos = min(i * chunk_size, len(context))
                # Snap to nearest word boundary
                if pos < len(context) and pos > 0:
                    space_pos = context.rfind(" ", max(0, pos - 100), pos + 100)
                    if space_pos > 0:
                        pos = space_pos
                positions.append(pos)
            all_positions = sorted(set(positions))

        # Create boundaries
        # Distribute positions to achieve target_chunks
        step = max(1, len(all_positions) // (target_chunks + 1))
        selected = [all_positions[i * step] for i in range(target_chunks)]
        selected.append(all_positions[-1])

        boundaries = []
        for i in range(len(selected) - 1):
            boundaries.append((selected[i], selected[i + 1]))

        return boundaries

    def _determine_task_type(
        self,
        query: str,
        chunk_index: int,
        total_chunks: int,
    ) -> RLMTaskType:
        """Determine the appropriate task type based on query and position"""
        query_lower = query.lower()

        if "resumen" in query_lower or "summary" in query_lower:
            return RLMTaskType.SUMMARIZE
        elif "extrae" in query_lower or "extract" in query_lower or "lista" in query_lower:
            return RLMTaskType.EXTRACT
        elif "compara" in query_lower or "compare" in query_lower:
            return RLMTaskType.COMPARE
        else:
            return RLMTaskType.ANALYZE

    def _create_subtask_query(
        self,
        original_query: str,
        task_type: RLMTaskType,
        chunk_index: int,
        total_chunks: int,
    ) -> str:
        """Create a specific query for the sub-task"""
        position = "inicial" if chunk_index == 0 else (
            "final" if chunk_index == total_chunks - 1 else f"intermedia {chunk_index + 1}"
        )

        if task_type == RLMTaskType.SUMMARIZE:
            return f"Resume la sección {position} del documento enfocándote en: {original_query}"
        elif task_type == RLMTaskType.EXTRACT:
            return f"En la sección {position}, extrae información relevante a: {original_query}"
        elif task_type == RLMTaskType.ANALYZE:
            return f"Analiza la sección {position} para responder: {original_query}"
        else:
            return f"Procesa la sección {position}: {original_query}"

    async def _process_subtask(
        self,
        task: RLMSubTask,
        context: str,
        depth: int,
    ) -> str:
        """Process a single sub-task"""
        start_time = datetime.now()

        # Check if context still too large (needs further recursion)
        context_tokens = self._estimate_tokens(context)

        if context_tokens > self._chunk_size and depth < self._max_recursion:
            # Recursive decomposition
            sub_sub_tasks = await self._decompose_query(
                query=task.query,
                context=context,
                depth=depth + 1,
            )

            results = []
            for sub_task in sub_sub_tasks:
                sub_context = context[sub_task.context_start : sub_task.context_end]
                result = await self._process_subtask(sub_task, sub_context, depth + 1)
                results.append(result)

            # Combine recursive results
            combined = "\n\n".join(f"[Resultado {i + 1}]: {r}" for i, r in enumerate(results))
            return combined

        # Process directly
        prompt = self._build_subtask_prompt(task, context)

        try:
            response = await self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
            )

            result = response.content if hasattr(response, "content") else str(response)
            task.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            return result

        except Exception as e:
            logger.warning(f"⚠️ Sub-task {task.task_id} failed: {e}")
            return f"[Error en sub-tarea: {e}]"

    async def _aggregate_results(
        self,
        query: str,
        sub_tasks: List[RLMSubTask],
    ) -> str:
        """Aggregate sub-task results into final answer"""
        if not sub_tasks:
            return "No se encontraron resultados."

        if len(sub_tasks) == 1:
            return sub_tasks[0].result or "Sin resultado."

        # Build aggregation prompt
        results_text = "\n\n".join(
            f"=== Sección {i + 1} ({task.task_type.value}) ===\n{task.result or 'Sin resultado'}"
            for i, task in enumerate(sub_tasks)
        )

        prompt = f"""Se ha procesado un documento largo en {len(sub_tasks)} secciones.
A continuación están los resultados parciales de cada sección:

{results_text}

---

Pregunta original: {query}

Sintetiza los resultados anteriores en una respuesta coherente y completa.
- Combina información de todas las secciones relevantes
- Elimina redundancias
- Mantén la precisión de los datos encontrados
- Si hay información contradictoria, menciona las discrepancias

Respuesta:"""

        try:
            response = await self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.3,
            )

            return response.content if hasattr(response, "content") else str(response)

        except Exception as e:
            logger.error(f"❌ Aggregation failed: {e}")
            # Fallback: concatenate results
            return "\n\n".join(
                f"[Sección {i + 1}]: {task.result}"
                for i, task in enumerate(sub_tasks)
                if task.result
            )

    def _build_subtask_prompt(self, task: RLMSubTask, context: str) -> str:
        """Build prompt for sub-task processing"""
        return f"""Procesa el siguiente fragmento de documento:

{context}

---

Tarea: {task.query}

Responde de forma concisa y precisa basándote SOLO en el fragmento proporcionado.
Si la información solicitada no está en este fragmento, indica "No encontrado en esta sección"."""

    def _build_answer_prompt(self, query: str, context: str) -> str:
        """Build prompt for direct answer"""
        return f"""Basándote en el siguiente contexto, responde la pregunta:

CONTEXTO:
{context}

---

PREGUNTA: {query}

RESPUESTA:"""

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text"""
        return len(text) // self._chars_per_token


# Global instance
rlm_orchestrator = RLMOrchestrator()
