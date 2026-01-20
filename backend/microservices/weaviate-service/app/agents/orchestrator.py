"""
Agent Orchestrator - Main Entry Point for Agent System (DEPRECATED)

⚠️ DEPRECATED: This orchestrator is deprecated. Use EmmaCoordinator instead.
The recommended flow is EmmaCoordinator + semantic-router.
This file is maintained for backward compatibility only.

This orchestrator manages:
1. Agent and workflow creation (lazy loading)
2. Automatic workflow selection based on query analysis
3. Timeout handling and fallback to RAG pipeline
4. Multi-tenant support

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework to Qwen-Agent
- Uses Assistant with get_llm_config() instead of ChatAgent

Usage:
    from app.agents import get_orchestrator

    orchestrator = get_orchestrator()
    result = await orchestrator.execute(
        query="What are the payment terms?",
        tenant_id="tenant-123"
    )
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, AsyncIterator
from dataclasses import dataclass
from enum import Enum

from .config import agent_config, AgentConfig, WorkflowType

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from the agent orchestrator."""
    answer: str
    workflow_used: str
    agents_involved: list
    success: bool
    fallback_used: bool = False
    error: Optional[str] = None
    execution_time_ms: float = 0
    metadata: Optional[Dict[str, Any]] = None


class AgentOrchestrator:
    """
    Main orchestrator for the Agent system (DEPRECATED).

    ⚠️ DEPRECATED: Use EmmaCoordinator instead for new implementations.
    This class is maintained for backward compatibility only.

    Responsibilities:
    1. Create and manage Assistants on demand (lazy loading)
    2. Select appropriate workflow based on query characteristics
    3. Execute workflows with timeout protection
    4. Automatic fallback to RAG pipeline on failure

    FRAMEWORK: Qwen-Agent
    All components are lazily loaded to avoid startup failures
    if LLM provider (vLLM/OpenAI) is not available.
    """

    def __init__(self, config: AgentConfig = None):
        """
        Initialize the orchestrator.

        Args:
            config: Agent configuration (uses global if None)
        """
        self.config = config or agent_config
        self._llm_cfg = None
        self._workflows: Dict[WorkflowType, Any] = {}
        self._rag_pipeline = None
        self._initialized = False

        logger.warning(
            "⚠️ AgentOrchestrator is DEPRECATED. "
            "Use EmmaCoordinator + semantic-router instead. "
            "Enable only for legacy compatibility (AUTOGEN_ENABLED=true)."
        )
        logger.info(
            f"AgentOrchestrator created: enabled={self.config.enabled}, "
            f"provider={self.config.model_provider}"
        )

    def _ensure_initialized(self):
        """Initialize components if not already done."""
        if self._initialized:
            return

        if not self.config.enabled:
            logger.info("Agent system disabled, using RAG only")
            self._initialized = True
            return

        try:
            # Test that we can import Qwen-Agent
            from qwen_agent.agents import Assistant
            self._initialized = True
            logger.info("Qwen-Agent initialized successfully")
        except ImportError as e:
            logger.warning(f"Qwen-Agent not available: {e}")
            self.config.enabled = False
            self._initialized = True

    def _get_llm_config(self):
        """Get or create the LLM configuration (lazy)."""
        if self._llm_cfg is None:
            from .model_client import get_llm_config
            try:
                self._llm_cfg = get_llm_config()
                logger.debug(f"LLM config created: {self._llm_cfg.get('model', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to create LLM config: {e}")
                raise
        return self._llm_cfg

    def _get_rag_pipeline(self):
        """Get or create RAG pipeline for fallback."""
        if self._rag_pipeline is None:
            try:
                from app.services.rag.rag_pipeline import RAGPipeline
                self._rag_pipeline = RAGPipeline()
            except ImportError:
                logger.warning("RAG pipeline not available")
        return self._rag_pipeline

    def _get_workflow(self, workflow_type: WorkflowType):
        """Get or create a specific workflow (lazy)."""
        if workflow_type in self._workflows:
            return self._workflows[workflow_type]

        try:
            llm_cfg = self._get_llm_config()

            if workflow_type == WorkflowType.SEQUENTIAL:
                from .workflows import create_analysis_pipeline
                self._workflows[workflow_type] = create_analysis_pipeline(
                    llm_cfg,
                    max_turns=self.config.max_turns
                )

            elif workflow_type == WorkflowType.GROUP_CHAT:
                from .workflows import create_specialist_group
                self._workflows[workflow_type] = create_specialist_group(
                    llm_cfg,
                    max_turns=self.config.max_turns
                )

            elif workflow_type == WorkflowType.SWARM:
                from .workflows import create_document_swarm
                self._workflows[workflow_type] = create_document_swarm(
                    llm_cfg,
                    max_turns=self.config.max_turns
                )

            logger.debug(f"Created workflow: {workflow_type.value}")
            return self._workflows.get(workflow_type)

        except Exception as e:
            logger.error(f"Failed to create workflow {workflow_type}: {e}")
            return None

    def _auto_select_workflow(self, query: str) -> WorkflowType:
        """
        Automatically select the best workflow for a query.

        Heuristics:
        - Contract/compliance keywords → SWARM (triage to specialist)
        - Analysis/comparison keywords → GROUP_CHAT (dynamic selection)
        - Simple search queries → SEQUENTIAL (search → analyze → summarize)
        """
        query_lower = query.lower()

        # Keywords indicating need for specialized agents
        contract_keywords = [
            "contrato", "contract", "cláusula", "clause",
            "obligación", "obligation", "firmante", "signatory",
            "vigencia", "validity", "terminación", "termination"
        ]

        compliance_keywords = [
            "gdpr", "rgpd", "lopd", "cumplimiento", "compliance",
            "privacidad", "privacy", "datos personales", "personal data",
            "consentimiento", "consent"
        ]

        analysis_keywords = [
            "analiza", "analyze", "compara", "compare",
            "diferencias", "differences", "similitudes", "similarities",
            "riesgos", "risks", "evalúa", "evaluate"
        ]

        # Route to appropriate workflow
        if any(kw in query_lower for kw in contract_keywords + compliance_keywords):
            logger.debug(f"Auto-selected SWARM for query with contract/compliance keywords")
            return WorkflowType.SWARM

        if any(kw in query_lower for kw in analysis_keywords):
            logger.debug(f"Auto-selected GROUP_CHAT for analysis query")
            return WorkflowType.GROUP_CHAT

        # Default to sequential for simple queries
        logger.debug(f"Auto-selected SEQUENTIAL (default) for query")
        return WorkflowType.SEQUENTIAL

    async def execute(
        self,
        query: str,
        tenant_id: str,
        workflow_type: WorkflowType = WorkflowType.AUTO,
        **kwargs
    ) -> AgentResponse:
        """
        Execute a query using the agent system.

        This is the main entry point for processing queries. It:
        1. Selects the appropriate workflow (or uses AUTO selection)
        2. Executes with timeout protection
        3. Falls back to RAG pipeline if agents fail

        Args:
            query: User's question or request
            tenant_id: Tenant ID for data isolation
            workflow_type: Which workflow to use (AUTO for automatic)
            **kwargs: Additional parameters passed to workflow

        Returns:
            AgentResponse with answer and execution metadata
        """
        start_time = time.time()

        self._ensure_initialized()

        # If agents disabled, go straight to RAG
        if not self.config.enabled:
            return await self._fallback_to_rag(
                query, tenant_id, "Agent Framework disabled"
            )

        try:
            # Select workflow
            if workflow_type == WorkflowType.AUTO:
                workflow_type = self._auto_select_workflow(query)

            workflow = self._get_workflow(workflow_type)
            if workflow is None:
                return await self._fallback_to_rag(
                    query, tenant_id,
                    f"Workflow {workflow_type.value} not available"
                )

            # Build task with tenant context
            task = self._build_task(query, tenant_id, **kwargs)

            # Execute with timeout
            logger.info(
                f"Executing workflow {workflow_type.value} for tenant {tenant_id}"
            )

            result = await asyncio.wait_for(
                workflow.run(task),
                timeout=self.config.timeout_seconds
            )

            execution_time = (time.time() - start_time) * 1000

            # Extract answer from workflow result
            answer = result.answer if hasattr(result, 'answer') else str(result)
            agents_used = result.agents_used if hasattr(result, 'agents_used') else []

            return AgentResponse(
                answer=answer,
                workflow_used=workflow_type.value,
                agents_involved=agents_used,
                success=True,
                execution_time_ms=execution_time,
                metadata={
                    "turns": getattr(result, 'turns_taken', 0),
                    "completed": getattr(result, 'completed', True),
                }
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"Agent execution timed out after {self.config.timeout_seconds}s"
            )
            return await self._fallback_to_rag(
                query, tenant_id, "Execution timeout"
            )

        except Exception as e:
            logger.exception(f"Agent execution error: {e}")
            return await self._fallback_to_rag(query, tenant_id, str(e))

    def _build_task(self, query: str, tenant_id: str, **kwargs) -> str:
        """Build the task string for agents."""
        task = f"""Tenant ID: {tenant_id}

User Query: {query}

Instructions:
1. Use the available tools to answer the user's query
2. ALWAYS include tenant_id="{tenant_id}" in all tool calls
3. Cite sources when providing information from documents
4. When you have fully answered the query, include "TASK_COMPLETE" in your response
"""

        # Add document content if provided (for specific document analysis)
        if kwargs.get('document_content'):
            doc_title = kwargs.get('document_title', 'Documento')
            doc_id = kwargs.get('document_id', 'unknown')
            doc_content = kwargs.get('document_content')

            # Truncate content if too long (keep first 15000 chars for context)
            max_content_length = 15000
            if len(doc_content) > max_content_length:
                doc_content = doc_content[:max_content_length] + "\n\n[... contenido truncado ...]"

            task += f"""

=== DOCUMENT FOR ANALYSIS ===
Title: {doc_title}
Document ID: {doc_id}

Content:
{doc_content}
=== END DOCUMENT ===

IMPORTANT: Analyze the document above. Do NOT search for it, the content is already provided.
"""

        # Add any additional context
        if kwargs.get('document_ids'):
            task += f"\nRelevant document IDs: {kwargs['document_ids']}"

        if kwargs.get('collection_name'):
            task += f"\nCollection: {kwargs['collection_name']}"

        return task

    async def _fallback_to_rag(
        self,
        query: str,
        tenant_id: str,
        reason: str
    ) -> AgentResponse:
        """
        Fallback to RAG pipeline when agents fail.

        This ensures users always get a response even if the
        agent system is unavailable or fails.
        """
        start_time = time.time()
        logger.info(f"Falling back to RAG pipeline: {reason}")

        try:
            pipeline = self._get_rag_pipeline()
            if pipeline is None:
                return AgentResponse(
                    answer="Unable to process query: RAG pipeline not available",
                    workflow_used="error",
                    agents_involved=[],
                    success=False,
                    fallback_used=True,
                    error="RAG pipeline not available"
                )

            result = await pipeline.process_query(
                query=query,
                tenant_id=tenant_id,
                validate_claims=True
            )

            execution_time = (time.time() - start_time) * 1000

            answer = result.answer if hasattr(result, 'answer') else str(result)

            return AgentResponse(
                answer=answer,
                workflow_used="rag_fallback",
                agents_involved=["RAGPipeline"],
                success=True,
                fallback_used=True,
                error=reason,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.exception(f"RAG fallback also failed: {e}")
            return AgentResponse(
                answer=f"Error processing query: {e}",
                workflow_used="error",
                agents_involved=[],
                success=False,
                fallback_used=True,
                error=str(e)
            )

    async def execute_stream(
        self,
        query: str,
        tenant_id: str,
        workflow_type: WorkflowType = WorkflowType.AUTO,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute with streaming of agent messages.

        Yields messages as they are generated, allowing for
        real-time display of agent activity.

        Args:
            query: User's question
            tenant_id: Tenant ID
            workflow_type: Workflow to use

        Yields:
            Dict with message type and content
        """
        self._ensure_initialized()

        if not self.config.enabled:
            result = await self._fallback_to_rag(
                query, tenant_id, "Agent Framework disabled"
            )
            yield {"type": "final", "content": result.answer}
            return

        if workflow_type == WorkflowType.AUTO:
            workflow_type = self._auto_select_workflow(query)

        workflow = self._get_workflow(workflow_type)
        if workflow is None:
            result = await self._fallback_to_rag(
                query, tenant_id, "Workflow not available"
            )
            yield {"type": "final", "content": result.answer}
            return

        task = self._build_task(query, tenant_id)

        try:
            async for message in workflow.run_stream(task):
                yield {
                    "type": "message",
                    "agent": getattr(message, 'source', 'unknown'),
                    "content": getattr(message, 'content', str(message)),
                }
        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield {"type": "error", "content": str(e)}

    def get_available_workflows(self) -> list:
        """Get list of available workflow types."""
        return [wt.value for wt in WorkflowType]

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status and configuration."""
        return {
            "enabled": self.config.enabled,
            "provider": self.config.model_provider,
            "model": getattr(
                self.config,
                f"{self.config.model_provider}_model",
                "unknown"
            ),
            "max_turns": self.config.max_turns,
            "timeout_seconds": self.config.timeout_seconds,
            "fallback_enabled": self.config.fallback_to_rag,
            "workflows_loaded": list(self._workflows.keys()),
            "initialized": self._initialized,
        }


# Singleton instance management
_orchestrator_instance: Optional[AgentOrchestrator] = None


def get_orchestrator(config: AgentConfig = None) -> AgentOrchestrator:
    """
    Get or create the orchestrator singleton.

    Args:
        config: Optional configuration override

    Returns:
        AgentOrchestrator instance
    """
    global _orchestrator_instance

    if _orchestrator_instance is None:
        _orchestrator_instance = AgentOrchestrator(config)

    return _orchestrator_instance


def reset_orchestrator():
    """Reset the orchestrator singleton (for testing)."""
    global _orchestrator_instance
    _orchestrator_instance = None
