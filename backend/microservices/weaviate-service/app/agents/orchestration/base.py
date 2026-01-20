"""
Base classes for orchestration patterns.

This module defines the common data structures used by all orchestration
patterns (Sequential, Concurrent, Handoff).

ARCHITECTURE:
All orchestration patterns follow the same interface:
1. Accept a task/query and list of agents
2. Execute according to their pattern logic
3. Return an OrchestrationResult with standardized fields
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from qwen_agent.agents import Assistant

logger = logging.getLogger(__name__)


class OrchestrationPattern(str, Enum):
    """Available orchestration patterns."""
    HANDOFF = "handoff"      # Default: LLM decides via .as_tool()
    SEQUENTIAL = "sequential"  # Pipeline: A → B → C
    CONCURRENT = "concurrent"  # Parallel: A | B | C → Aggregate
    RLM_LONG = "rlm_long"    # Recursive: For documents >50K tokens (arXiv:2512.24601)


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_name: str
    success: bool
    answer: str
    execution_time_ms: float
    tools_called: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationResult:
    """
    Standardized result from any orchestration pattern.

    All patterns return this structure, making it easy to integrate
    with emma_service.py regardless of which pattern was used.
    """
    success: bool
    answer: str
    pattern: OrchestrationPattern
    agents_executed: List[str]
    execution_time_ms: float
    intermediate_results: List[AgentResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def agents_delegated(self) -> List[str]:
        """Alias for compatibility with EmmaCoordinatorResult."""
        return self.agents_executed

    @property
    def tools_called(self) -> List[str]:
        """All tools called across all agents."""
        tools = []
        for result in self.intermediate_results:
            tools.extend(result.tools_called)
        return list(set(tools))


class BaseOrchestration(ABC):
    """
    Abstract base class for orchestration patterns.

    Each orchestration pattern must implement:
    - execute(): Main execution method
    - execute_stream(): Optional streaming variant
    """

    def __init__(self, name: str = "BaseOrchestration"):
        self.name = name
        self._pattern: OrchestrationPattern = OrchestrationPattern.HANDOFF

    @property
    def pattern(self) -> OrchestrationPattern:
        """Return the orchestration pattern type."""
        return self._pattern

    @abstractmethod
    async def execute(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        agents: List["Assistant"],
        **kwargs
    ) -> OrchestrationResult:
        """
        Execute the orchestration pattern.

        Args:
            task: The user's query/task
            tenant_id: Tenant identifier
            session_id: Session identifier for context
            agents: List of agents to orchestrate
            **kwargs: Pattern-specific arguments

        Returns:
            OrchestrationResult with execution details
        """
        pass

    def _create_result(
        self,
        success: bool,
        answer: str,
        agents_executed: List[str],
        start_time: float,
        intermediate_results: Optional[List[AgentResult]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> OrchestrationResult:
        """Helper to create standardized OrchestrationResult."""
        execution_time_ms = (time.perf_counter() - start_time) * 1000

        return OrchestrationResult(
            success=success,
            answer=answer,
            pattern=self._pattern,
            agents_executed=agents_executed,
            execution_time_ms=execution_time_ms,
            intermediate_results=intermediate_results or [],
            metadata=metadata or {}
        )


def detect_orchestration_pattern_keywords(query: str) -> Optional[OrchestrationPattern]:
    """
    DEPRECATED: Minimal keyword fallback for when Semantic Router is unavailable.

    This function is kept as a last-resort fallback only.
    The primary classification is done by SemanticPatternRouter in router.py
    which uses embeddings for robust multi-language pattern detection.

    Returns None if no clear pattern detected.
    """
    # Minimal fallback - Semantic Router handles these cases much better
    # Only kept for emergency fallback if semantic-router package fails to load
    return None


async def detect_orchestration_pattern_llm(
    query: str,
    vllm_base_url: str = "http://vllm:8000/v1",
    vllm_model: str = "Qwen/Qwen3-14B"
) -> OrchestrationPattern:
    """
    DEPRECATED: LLM-based pattern classification.

    This function is kept for backward compatibility but is no longer used.
    SemanticPatternRouter provides faster (~10ms) and more reliable classification
    using embeddings instead of LLM calls (~500ms).

    Always returns HANDOFF as a safe default.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ detect_orchestration_pattern_llm is deprecated. Use SemanticPatternRouter instead.")
    return OrchestrationPattern.HANDOFF


async def detect_orchestration_pattern(
    query: str,
    use_semantic: bool = True,
    use_llm: bool = False,  # DEPRECATED - kept for backward compatibility
    vllm_base_url: str = "http://vllm:8000/v1",
    vllm_model: str = "Qwen/Qwen3-14B"
) -> OrchestrationPattern:
    """
    Detect the optimal orchestration pattern using Semantic Router.

    The Semantic Router uses embeddings (all-MiniLM-L6-v2) to classify queries
    into patterns with ~10ms latency and automatic multi-language support.

    Patterns:
    - HANDOFF: Default for conversational queries, simple questions, greetings
    - SEQUENTIAL: When user requests step-by-step processing (A → B → C)
    - CONCURRENT: When user wants multi-perspective analysis (A | B | C)

    Args:
        query: User's query
        use_semantic: Whether to use Semantic Router (default True)
        use_llm: DEPRECATED - ignored, kept for backward compatibility
        vllm_base_url: DEPRECATED - ignored
        vllm_model: DEPRECATED - ignored

    Returns:
        OrchestrationPattern
    """
    # PRIMARY & ONLY: Semantic Router (~10ms latency)
    if use_semantic:
        try:
            from .router import get_semantic_router
            router = get_semantic_router()
            pattern = router.classify(query)
            logger.info(f"🎯 Semantic Router: {pattern.value} for: {query[:50]}...")
            return pattern
        except ImportError:
            logger.warning("⚠️ semantic-router not installed, defaulting to HANDOFF")
        except Exception as e:
            logger.warning(f"⚠️ Semantic Router failed: {e}, defaulting to HANDOFF")

    # Default: HANDOFF (preserves memory, safest choice)
    logger.info(f"🎯 Default: HANDOFF for: {query[:50]}...")
    return OrchestrationPattern.HANDOFF


def get_agents_for_pattern(
    pattern: OrchestrationPattern,
    query: str,
    available_agents: Dict[str, "Assistant"]
) -> List["Assistant"]:
    """
    Get the list of agents to use for a given pattern.

    Uses SemanticDomainRouter to classify the query's domain and select
    appropriate specialist agents. This replaces hardcoded keyword matching
    with semantic similarity detection.

    Args:
        pattern: The orchestration pattern
        query: The user's query (for domain detection via SemanticDomainRouter)
        available_agents: Dict of agent_name -> ChatAgent

    Returns:
        List of agents in execution order (sequential) or parallel group (concurrent)
    """
    if pattern == OrchestrationPattern.HANDOFF:
        # HANDOFF: No specific agents - let LLM decide via .as_tool()
        return []

    # Use SemanticDomainRouter for domain classification
    try:
        from .router import get_domain_router
        domain_router = get_domain_router()
        agent_names = domain_router.get_agent_names(query)
        logger.info(f"🎯 Domain Router selected agents: {agent_names}")
    except ImportError:
        logger.warning("⚠️ SemanticDomainRouter not available, using analyst_agent")
        agent_names = ["analyst_agent"]
    except Exception as e:
        logger.warning(f"⚠️ Domain Router failed: {e}, using analyst_agent")
        agent_names = ["analyst_agent"]

    if pattern == OrchestrationPattern.SEQUENTIAL:
        # Build pipeline based on detected domains
        agents = []

        # Check if search is needed (domain router will detect this)
        if "search_agent" in agent_names and "search_agent" in available_agents:
            agents.append(available_agents["search_agent"])

        # Add domain-specific agent(s)
        for agent_name in agent_names:
            if agent_name != "search_agent" and agent_name != "summarizer_agent":
                if agent_name in available_agents and available_agents[agent_name] not in agents:
                    agents.append(available_agents[agent_name])

        # Add summarizer at the end if detected
        if "summarizer_agent" in agent_names and "summarizer_agent" in available_agents:
            agents.append(available_agents["summarizer_agent"])

        # Fallback to analyst if no specific agents found
        if not agents and "analyst_agent" in available_agents:
            agents.append(available_agents["analyst_agent"])

        return agents

    elif pattern == OrchestrationPattern.CONCURRENT:
        # For concurrent, we may need multiple domain agents
        # Check if this is a multi-perspective query
        query_lower = query.lower()

        # Semantic patterns for "all areas" - these are caught by concurrent pattern detection
        all_areas_indicators = [
            "all areas", "todas las áreas", "tous les domaines",
            "all perspectives", "todas las perspectivas",
            "multiple", "several", "varios", "diverses"
        ]

        if any(indicator in query_lower for indicator in all_areas_indicators):
            # Include all main domain agents for comprehensive analysis
            domain_agents = ["contract_agent", "labor_agent", "fiscal_agent", "compliance_agent"]
            agents = []
            for name in domain_agents:
                if name in available_agents:
                    agents.append(available_agents[name])
            return agents

        # Otherwise use the domain router result
        agents = []
        for agent_name in agent_names:
            if agent_name in available_agents:
                agents.append(available_agents[agent_name])

        return agents

    return []


def should_use_rlm(context_tokens: int) -> bool:
    """
    Determine if RLM pattern should be used based on context size.

    RLM (Recursive Language Models) is activated when the context
    exceeds the threshold defined in settings.rlm_threshold_tokens.

    Args:
        context_tokens: Estimated token count of the context

    Returns:
        True if RLM should be used, False otherwise
    """
    try:
        from app.core.config import settings
        return (
            settings.rlm_enabled
            and context_tokens > settings.rlm_threshold_tokens
        )
    except Exception:
        # Fallback to hardcoded threshold if settings unavailable
        return context_tokens > 50000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length."""
    return len(text) // 4  # Rough estimate: 4 chars per token
