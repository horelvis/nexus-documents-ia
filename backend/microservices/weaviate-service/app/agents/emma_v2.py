"""
Emma v2 - Redesigned AI Assistant

A simplified, efficient implementation of Emma that:
1. Uses native async LLM client (no Qwen-Agent thread overhead)
2. SLM Router for TOON-based query planning (70-90% token savings)
3. Loads domain-specific prompts dynamically (~700 vs ~4250 tokens)
4. Has 6 consolidated tools (vs 15+ in v1)

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                         Emma v2 Agent                                │
    │                                                                      │
    │   ┌───────────────────────────────────────────────────────────────┐ │
    │   │              SLM Router (TOON Planning)                       │ │
    │   │  Query → TGI (Qwen2-0.5B) → TOON Plan → Execute               │ │
    │   │  Routes: GRAPH_ONLY | VECTOR_ONLY | HYBRID | ASK_CLARIFY      │ │
    │   └───────────────────────────────────────────────────────────────┘ │
    │                              │                                       │
    │                              │ If SLM unavailable                    │
    │                              ▼                                       │
    │   ┌───────────────────────────────────────────────────────────────┐ │
    │   │              SIL Fallback (DEPRECATED)                        │ │
    │   │  Structural queries → Cypher → Direct answer                  │ │
    │   └───────────────────────────────────────────────────────────────┘ │
    │                              │                                       │
    │                              │ If content needed                     │
    │                              ▼                                       │
    │   ┌───────────────────────────────────────────────────────────────┐ │
    │   │                   Domain Router                               │ │
    │   │  Query → Keywords/Doc Type → Domain (labor|fiscal|...)        │ │
    │   └───────────────────────────────────────────────────────────────┘ │
    │                              │                                       │
    │                              ▼                                       │
    │   ┌───────────────────────────────────────────────────────────────┐ │
    │   │                   Agentic Loop                                │ │
    │   │  for iteration in range(max):                                 │ │
    │   │      response = await llm.chat(messages, tools)               │ │
    │   │      if not response.tool_calls: return                       │ │
    │   │      results = await execute_tools(tool_calls)                │ │
    │   │      messages.extend(results)                                 │ │
    │   └───────────────────────────────────────────────────────────────┘ │
    │                                                                      │
    │   Tools: search, read_document, analyze, sil_query, ask_user,       │
    │          legal_search                                                │
    └─────────────────────────────────────────────────────────────────────┘

References:
- SLM Router: services/slm_router/README.md (TOON-based query planning)
- Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval
- Agent Skills: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import redis.asyncio as redis

from app.core.langfuse_config import (
    langfuse_context,
    observe,
    score_emma_result,
    trace_emma_query,
)
from .llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    StreamEvent,
    ToolCall,
    create_llm_client_from_settings,
    get_llm_client,
)
from .domain_router import DomainRouter, DomainType, domain_router
from .dynamic_prompt_loader import (
    DynamicPromptLoader,
    dynamic_prompt_loader,
    get_system_prompt_for_domain,
)
from .skill_loader import SkillLoader, skill_loader, get_skill_instructions

# Knowledge Source Router (2-stage: semantic + ML fallback)
try:
    from .orchestration import (
        KnowledgeSource,
        HybridClassificationResult,
        get_hybrid_knowledge_router,
        _SEMANTIC_ROUTER_AVAILABLE as KNOWLEDGE_ROUTER_AVAILABLE,
    )
except ImportError:
    KNOWLEDGE_ROUTER_AVAILABLE = False
    KnowledgeSource = None
    HybridClassificationResult = None
    get_hybrid_knowledge_router = None
from .emma_v2_tools import (
    EMMA_V2_TOOLS,
    ToolContext,
    ToolResult,
    execute_tool,
    get_emma_v2_tools,
)
from app.services.tenant_knowledge_service import (
    TenantKnowledgeService,
    tenant_knowledge_service,
)

# SLM Router (TOON-based query planning)
try:
    from app.services.slm_router import (
        get_slm_router,
        TOONRoute,
        TOONExecutionResult,
        SLMRouter,
    )
    SLM_ROUTER_AVAILABLE = True
except ImportError:
    SLM_ROUTER_AVAILABLE = False
    get_slm_router = None
    TOONRoute = None
    TOONExecutionResult = None
    SLMRouter = None

logger = logging.getLogger(__name__)

# Configuration
MAX_AGENTIC_ITERATIONS = 10
THREAD_TTL_SECONDS = 3600
THREAD_KEY_PREFIX = "emma:v2:thread:"


@dataclass
class EmmaV2Config:
    """Configuration for Emma v2."""
    max_iterations: int = MAX_AGENTIC_ITERATIONS
    enable_sil_fast_path: bool = True
    enable_slm_router: bool = True  # Use SLM Router for TOON-based query planning (alternative to SIL)
    enable_domain_routing: bool = True
    enable_knowledge_source_routing: bool = True  # Route by knowledge source (tenant/public/hybrid)
    enable_skills: bool = True  # Load procedural knowledge from skills
    enable_streaming: bool = True
    thread_ttl_seconds: int = THREAD_TTL_SECONDS
    max_skill_tokens: int = 2000  # Token budget for skill instructions


@dataclass
class EmmaV2Result:
    """Result from Emma v2 execution."""
    success: bool
    answer: str
    domain: DomainType = DomainType.GENERAL
    knowledge_source: Optional[str] = None  # tenant_documents, public_knowledge, hybrid
    tools_called: List[str] = field(default_factory=list)
    skills_used: List[str] = field(default_factory=list)  # Skills loaded for this query
    iterations: int = 0
    sil_answered: bool = False
    tokens_saved: int = 0
    latency_ms: float = 0.0
    thread_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "answer": self.answer,
            "domain": self.domain.value,
            "knowledge_source": self.knowledge_source,
            "tools_called": self.tools_called,
            "skills_used": self.skills_used,
            "iterations": self.iterations,
            "sil_answered": self.sil_answered,
            "tokens_saved": self.tokens_saved,
            "latency_ms": self.latency_ms,
            "thread_id": self.thread_id,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionContext:
    """Context for Emma v2 execution."""
    tenant_id: str
    user_id: Optional[str] = None
    role_ids: List[str] = field(default_factory=list)
    is_admin: bool = False
    thread_id: Optional[str] = None
    conversation_id: Optional[str] = None


class EmmaV2:
    """
    Emma v2 - Simplified AI Assistant with SIL Integration.

    Key improvements over v1:
    1. Native async (no thread pool workarounds)
    2. SIL fast path for structural queries
    3. Dynamic domain-specific prompts
    4. Consolidated tool set (6 vs 15+)
    5. ~70% reduction in prompt tokens
    """

    def __init__(
        self,
        config: Optional[EmmaV2Config] = None,
        llm_client: Optional[LLMClient] = None,
        redis_client: Optional[redis.Redis] = None,
        knowledge_service: Optional[TenantKnowledgeService] = None,
    ):
        """
        Initialize Emma v2.

        Args:
            config: Configuration options
            llm_client: Optional pre-configured LLM client
            redis_client: Optional Redis client for conversation history
            knowledge_service: Optional TenantKnowledgeService for learned terminology
        """
        self.config = config or EmmaV2Config()
        self._llm_client = llm_client
        self._redis = redis_client
        self._domain_router = domain_router
        self._prompt_loader = dynamic_prompt_loader
        self._skill_loader = skill_loader
        self._knowledge_service = knowledge_service or tenant_knowledge_service
        self._knowledge_router = None  # HybridKnowledgeRouter
        self._sil = None
        self._slm_router = None  # SLM Router for TOON-based query planning
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Emma v2 and its dependencies."""
        if self._initialized:
            return

        # Initialize LLM client
        if self._llm_client is None:
            self._llm_client = await get_llm_client()

        # Validate LLM connection
        is_connected, msg = await self._llm_client.validate_connection()
        if not is_connected:
            logger.warning(f"LLM connection issue: {msg}")

        # Initialize Knowledge Source Router
        if self.config.enable_knowledge_source_routing and KNOWLEDGE_ROUTER_AVAILABLE:
            self._knowledge_router = get_hybrid_knowledge_router()
            await self._knowledge_router.initialize()
            logger.info("✅ Knowledge Source Router enabled (2-stage: semantic + ML)")

        # Initialize SLM Router (TOON-based query planning) - takes priority over SIL
        if self.config.enable_slm_router and SLM_ROUTER_AVAILABLE:
            try:
                self._slm_router = get_slm_router()
                if not self._slm_router._initialized:
                    await self._slm_router.initialize()
                logger.info("✅ SLM Router enabled (TOON-based query planning)")
            except Exception as slm_err:
                logger.warning(f"⚠️ SLM Router initialization failed: {slm_err}")
                self._slm_router = None

        # Initialize SIL (fallback if SLM Router is disabled or unavailable)
        if self.config.enable_sil_fast_path:
            from app.services.sil import pre_llm_engine
            self._sil = pre_llm_engine
            await self._sil.initialize()
            logger.info("✅ SIL fast path enabled")

        # Initialize Redis for conversation history
        if self._redis is None:
            from app.core.config import settings
            self._redis = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )

        # Load agent skills from filesystem
        if self.config.enable_skills:
            num_skills = self._skill_loader.reload_skills()
            logger.info(f"✅ Loaded {num_skills} agent skills")

        self._initialized = True
        logger.info("✅ Emma v2 initialized")

    @observe(name="emma.execute")
    async def execute(
        self,
        query: str,
        context: ExecutionContext,
        ask_user_callback: Optional[Callable] = None,
    ) -> EmmaV2Result:
        """
        Execute a query with Emma v2.

        This is the main entry point. The execution flow:
        1. Try SIL fast path for structural queries
        2. If content needed, detect domain and load prompts
        3. Run agentic loop with tools

        Args:
            query: User's query
            context: Execution context (tenant, user, etc.)
            ask_user_callback: Optional callback for HITL clarification

        Returns:
            EmmaV2Result with answer and metadata
        """
        start_time = time.time()
        await self.initialize()

        # Update Langfuse observation with execution context
        langfuse_context.update_current_observation(
            session_id=context.thread_id,
            user_id=context.user_id,
            metadata={
                "tenant_id": context.tenant_id,
                "is_admin": context.is_admin,
                "sil_enabled": self.config.enable_sil_fast_path,
                "domain_routing_enabled": self.config.enable_domain_routing,
            },
            input={"query": query},
        )

        # Create tool context
        tool_ctx = ToolContext(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            role_ids=context.role_ids,
            is_admin=context.is_admin,
            conversation_id=context.conversation_id,
            ask_user_callback=ask_user_callback,
        )

        # Step 0: Classify Knowledge Source (NEW)
        knowledge_classification = None
        is_follow_up = self._is_follow_up_query(query)
        inherited_knowledge_source = None

        if self._knowledge_router:
            knowledge_classification = await self._knowledge_router.classify(query)

            # For follow-up queries with low confidence, inherit from previous turn
            if knowledge_classification and is_follow_up and knowledge_classification.confidence < 0.85:
                # Get last knowledge_source from Redis to maintain context
                inherited_knowledge_source = await self._get_last_knowledge_source(context.thread_id)
                logger.info(
                    f"🔄 Follow-up query detected (conf={knowledge_classification.confidence:.2f}), "
                    f"inheriting knowledge_source={inherited_knowledge_source}"
                )

                # Inherit routing from previous turn to maintain conversation context
                if inherited_knowledge_source == "public_knowledge":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.PUBLIC_KNOWLEDGE,
                        confidence=0.95,  # High confidence for inherited context
                        stage_used=0,  # Inherited from history
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"📚 Inheriting PUBLIC_KNOWLEDGE routing for follow-up")
                elif inherited_knowledge_source == "hybrid":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.HYBRID,
                        confidence=0.95,
                        stage_used=0,
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"🔀 Inheriting HYBRID routing for follow-up")
                elif inherited_knowledge_source == "tenant_documents":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.TENANT_DOCUMENTS,
                        confidence=0.95,
                        stage_used=0,
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"📁 Inheriting TENANT_DOCUMENTS routing for follow-up")
                else:
                    # No previous context, let agentic loop handle it
                    knowledge_classification = None
                    logger.info(f"❓ No previous knowledge_source, using default routing")
            elif knowledge_classification:
                logger.info(
                    f"🎯 Knowledge Source: {knowledge_classification.source.value} "
                    f"(conf={knowledge_classification.confidence:.2f}, "
                    f"stage={knowledge_classification.stage_used}, "
                    f"ml_used={knowledge_classification.ml_used})"
                )

            # PUBLIC_KNOWLEDGE: Skip SIL, go directly to agentic loop with legal_search hint
            if knowledge_classification and knowledge_classification.source == KnowledgeSource.PUBLIC_KNOWLEDGE:
                logger.info("📚 Routing to PUBLIC_KNOWLEDGE path (skip SIL)")
                result = await self._handle_public_knowledge_query(
                    query, context, tool_ctx, knowledge_classification
                )
                result.latency_ms = (time.time() - start_time) * 1000
                result.thread_id = context.thread_id or ""

                # IMPORTANT: Save to conversation history for context continuity
                if context.thread_id:
                    await self._save_to_history(
                        context.thread_id, query, result.answer,
                        knowledge_source=knowledge_classification.source.value
                    )

                # Auto-collect example for learning
                await self._collect_knowledge_example(
                    query, knowledge_classification, result.tools_called, 0, context.tenant_id
                )
                return result

            # HYBRID: Skip SIL, use both tenant search and legal_search
            if knowledge_classification and knowledge_classification.source == KnowledgeSource.HYBRID:
                logger.info("🔀 Routing to HYBRID path (both sources)")
                result = await self._handle_hybrid_query(
                    query, context, tool_ctx, knowledge_classification
                )
                result.latency_ms = (time.time() - start_time) * 1000
                result.thread_id = context.thread_id or ""

                if context.thread_id:
                    await self._save_to_history(
                        context.thread_id, query, result.answer,
                        knowledge_source=knowledge_classification.source.value
                    )

                await self._collect_knowledge_example(
                    query, knowledge_classification, result.tools_called, 0, context.tenant_id
                )
                return result

        # Step 1: Try fast path routing (SLM Router or SIL)
        # Skip for conversational responses that need conversation context
        sil_doc_count = 0
        is_conversational = self._is_conversational_response(query)

        if is_conversational:
            logger.info(f"💬 Conversational response detected, skipping fast path → agentic loop with history")
        else:
            # Step 1a: Try SLM Router first (TOON-based planning)
            if self.config.enable_slm_router and self._slm_router and SLM_ROUTER_AVAILABLE:
                logger.info(f"🎯 Emma v2: Trying SLM Router for query: '{query[:60]}...'")
                session_id = context.thread_id or context.conversation_id or ""
                slm_result = await self._try_slm_router(query, context.tenant_id, session_id)
                if slm_result:
                    logger.info(f"✅ Emma v2: SLM Router answered (route={slm_result.metadata.get('toon_route')})")
                    slm_result.latency_ms = (time.time() - start_time) * 1000
                    slm_result.thread_id = context.thread_id or ""
                    slm_result.knowledge_source = knowledge_classification.source.value if knowledge_classification else "tenant_documents"

                    # Auto-collect example for learning
                    if knowledge_classification:
                        await self._collect_knowledge_example(
                            query, knowledge_classification, [], 0, context.tenant_id
                        )
                    return slm_result
                else:
                    logger.info(f"➡️ Emma v2: SLM Router declined → trying SIL fallback")

            # Step 1b: Try SIL fast path as fallback
            if self.config.enable_sil_fast_path and self._sil:
                logger.info(f"🧠 Emma v2: Trying SIL fast path for query: '{query[:60]}...'")
                sil_result, sil_doc_count = await self._try_sil_fast_path_with_count(query, context.tenant_id)
                if sil_result:
                    logger.info(f"✅ Emma v2: SIL fast path answered (tokens_saved={sil_result.tokens_saved})")
                    sil_result.latency_ms = (time.time() - start_time) * 1000
                    sil_result.thread_id = context.thread_id or ""
                    sil_result.knowledge_source = knowledge_classification.source.value if knowledge_classification else "tenant_documents"

                    # Auto-collect example for learning
                    if knowledge_classification:
                        await self._collect_knowledge_example(
                            query, knowledge_classification, [], sil_doc_count, context.tenant_id
                        )
                    return sil_result
                else:
                    logger.info(f"➡️ Emma v2: SIL declined (doc_count={sil_doc_count}) → agentic loop")

        # Step 2: Detect domain for dynamic prompt
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain
            logger.info(f"Domain detected: {domain.value} (confidence: {detection.confidence:.2f})")

        # Step 3: Build messages with conversation history and skills
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        # Step 4: Run agentic loop
        result = await self._agentic_loop(messages, tool_ctx, domain)
        result.skills_used = skills_used
        result.knowledge_source = knowledge_classification.source.value if knowledge_classification else "tenant_documents"

        result.latency_ms = (time.time() - start_time) * 1000
        result.thread_id = context.thread_id or ""

        # Auto-collect example for learning (after agentic loop)
        if knowledge_classification:
            await self._collect_knowledge_example(
                query, knowledge_classification, result.tools_called, sil_doc_count, context.tenant_id
            )

        # Step 5: Save to conversation history
        if context.thread_id:
            # Determine knowledge_source: from classification, inheritance, or default
            final_knowledge_source = (
                knowledge_classification.source.value if knowledge_classification
                else inherited_knowledge_source
                or "tenant_documents"
            )
            await self._save_to_history(
                context.thread_id, query, result.answer,
                knowledge_source=final_knowledge_source
            )

        # Step 6: Score the result for Langfuse analytics
        score_emma_result(
            tokens_saved=result.tokens_saved,
            sil_answered=result.sil_answered,
            iterations=result.iterations,
            tools_called=result.tools_called,
            latency_ms=result.latency_ms,
        )

        # Update Langfuse with output
        langfuse_context.update_current_observation(
            output={
                "answer": result.answer[:500] + "..." if len(result.answer) > 500 else result.answer,
                "domain": result.domain.value,
                "sil_answered": result.sil_answered,
                "tokens_saved": result.tokens_saved,
            },
            metadata={
                "domain": result.domain.value,
                "skills_used": result.skills_used,
            },
        )

        return result

    @observe(name="emma.execute_stream")
    async def execute_stream(
        self,
        query: str,
        context: ExecutionContext,
        ask_user_callback: Optional[Callable] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute query with streaming response.

        Yields events:
        - {"type": "thinking", "content": "..."} - Thinking process
        - {"type": "content", "content": "..."} - Answer content
        - {"type": "tool_call", "name": "...", "arguments": {...}} - Tool invocation
        - {"type": "tool_result", "name": "...", "result": {...}} - Tool result
        - {"type": "done", "result": {...}} - Final result

        Args:
            query: User's query
            context: Execution context
            ask_user_callback: Optional callback for HITL

        Yields:
            Event dictionaries
        """
        start_time = time.time()
        await self.initialize()

        # Update Langfuse observation with execution context
        langfuse_context.update_current_observation(
            session_id=context.thread_id,
            user_id=context.user_id,
            metadata={
                "tenant_id": context.tenant_id,
                "streaming": True,
                "sil_enabled": self.config.enable_sil_fast_path,
            },
            input={"query": query},
        )

        tool_ctx = ToolContext(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            role_ids=context.role_ids,
            is_admin=context.is_admin,
            conversation_id=context.conversation_id,
            ask_user_callback=ask_user_callback,
        )

        # Classify Knowledge Source (NEW)
        knowledge_classification = None
        is_follow_up = self._is_follow_up_query(query)
        inherited_knowledge_source = None

        if self._knowledge_router:
            knowledge_classification = await self._knowledge_router.classify(query)

            # For follow-up queries with low confidence, inherit from previous turn
            if knowledge_classification and is_follow_up and knowledge_classification.confidence < 0.85:
                # Get last knowledge_source from Redis to maintain context
                inherited_knowledge_source = await self._get_last_knowledge_source(context.thread_id)
                logger.info(
                    f"🔄 Stream: Follow-up query detected (conf={knowledge_classification.confidence:.2f}), "
                    f"inheriting knowledge_source={inherited_knowledge_source}"
                )

                # Inherit routing from previous turn to maintain conversation context
                if inherited_knowledge_source == "public_knowledge":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.PUBLIC_KNOWLEDGE,
                        confidence=0.95,
                        stage_used=0,
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"📚 Stream: Inheriting PUBLIC_KNOWLEDGE routing for follow-up")
                elif inherited_knowledge_source == "hybrid":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.HYBRID,
                        confidence=0.95,
                        stage_used=0,
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"🔀 Stream: Inheriting HYBRID routing for follow-up")
                elif inherited_knowledge_source == "tenant_documents":
                    knowledge_classification = HybridClassificationResult(
                        source=KnowledgeSource.TENANT_DOCUMENTS,
                        confidence=0.95,
                        stage_used=0,
                        semantic_confidence=0.0,
                        ml_used=False,
                        total_latency_ms=0.0,
                        semantic_latency_ms=0.0,
                        ml_latency_ms=0.0,
                    )
                    logger.info(f"📁 Stream: Inheriting TENANT_DOCUMENTS routing for follow-up")
                else:
                    knowledge_classification = None
                    logger.info(f"❓ Stream: No previous knowledge_source, using default routing")
            elif knowledge_classification:
                logger.info(
                    f"🎯 Stream: Knowledge Source: {knowledge_classification.source.value} "
                    f"(conf={knowledge_classification.confidence:.2f})"
                )

            # PUBLIC_KNOWLEDGE: Skip SIL, stream with legal_search hint
            if knowledge_classification and knowledge_classification.source == KnowledgeSource.PUBLIC_KNOWLEDGE:
                logger.info("📚 Stream: Routing to PUBLIC_KNOWLEDGE path")
                async for event in self._stream_public_knowledge_query(
                    query, context, tool_ctx, knowledge_classification
                ):
                    yield event
                return

            # HYBRID: Skip SIL, stream with both sources hint
            if knowledge_classification and knowledge_classification.source == KnowledgeSource.HYBRID:
                logger.info("🔀 Stream: Routing to HYBRID path")
                async for event in self._stream_hybrid_query(
                    query, context, tool_ctx, knowledge_classification
                ):
                    yield event
                return

        # Try SIL fast path first with real LLM streaming
        # Skip SIL for conversational responses that need conversation context
        is_conversational = self._is_conversational_response(query)

        if is_conversational:
            logger.info(f"💬 Stream: Conversational response detected, skipping SIL → agentic loop with history")
        elif self.config.enable_sil_fast_path and self._sil:
            sil_stream_result = await self._try_sil_fast_path_stream(query, context.tenant_id)
            if sil_stream_result is not None:
                # Stream the SIL response using LLM
                accumulated_content = ""
                async for event in sil_stream_result:
                    if event["type"] == "content":
                        accumulated_content += event["content"]
                        yield event
                    elif event["type"] == "done":
                        # Add process_info to done event
                        event["result"]["process_info"] = {
                            "reasoning_type": event["result"].get("reasoning_type", "STRUCTURAL"),
                            "reasoning_message": "Respuesta desde SIL con interpretación LLM",
                            "tokens_saved": event["result"].get("tokens_saved", 0),
                            "sil_used": True,
                            "active_tools": [],
                        }
                        yield event
                        return
                    else:
                        yield event
                return

        # Detect domain
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain

        # Build messages with skills
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        # Agentic loop with streaming
        tools_called = []
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1

            # Stream LLM response
            accumulated_content = ""
            tool_calls = []

            async for event in self._llm_client.chat_stream(messages, EMMA_V2_TOOLS):
                if event.event_type == "content":
                    accumulated_content += event.content
                    yield {"type": "content", "content": event.content}
                elif event.event_type == "thinking":
                    yield {"type": "thinking", "content": event.thinking}
                elif event.event_type == "tool_call":
                    tool_calls.append(event.tool_call)
                    tools_called.append(event.tool_call.name)
                    yield {
                        "type": "tool_call",
                        "name": event.tool_call.name,
                        "arguments": event.tool_call.arguments,
                        "process_info": {
                            "reasoning_type": "SEMANTIC",
                            "sil_used": self.config.enable_sil_fast_path,
                            "active_tools": [{
                                "name": event.tool_call.name,
                                "status": "running",
                                "message": f"Ejecutando {event.tool_call.name}...",
                            }],
                        },
                    }
                elif event.event_type == "error":
                    yield {"type": "error", "error": event.error}
                    return

            # If no tool calls, we're done
            if not tool_calls:
                latency_ms = (time.time() - start_time) * 1000
                result = EmmaV2Result(
                    success=True,
                    answer=accumulated_content,
                    domain=domain,
                    tools_called=tools_called,
                    skills_used=skills_used,
                    iterations=iterations,
                    latency_ms=latency_ms,
                    thread_id=context.thread_id or "",
                )
                result_dict = result.to_dict()
                # Add process_info to final result
                result_dict["process_info"] = {
                    "reasoning_type": "SEMANTIC" if tools_called else "FULL_RAG",
                    "reasoning_message": f"Razonamiento completado con {len(tools_called)} herramienta(s)",
                    "tokens_saved": 0,
                    "sil_used": self.config.enable_sil_fast_path,
                    "active_tools": [
                        {"name": t, "status": "completed"} for t in tools_called
                    ],
                    "execution_time_ms": latency_ms,
                }
                yield {"type": "done", "result": result_dict}

                # IMPORTANT: Save to conversation history for context continuity
                if context.thread_id:
                    final_knowledge_source = (
                        knowledge_classification.source.value if knowledge_classification
                        else inherited_knowledge_source
                        or "tenant_documents"
                    )
                    await self._save_to_history(
                        context.thread_id, query, accumulated_content,
                        knowledge_source=final_knowledge_source
                    )
                return

            # Execute tool calls
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in tool_calls
                ]
            })

            for tc in tool_calls:
                tool_start = time.time()
                result = await execute_tool(tc.name, tc.arguments, tool_ctx)
                tool_elapsed = (time.time() - tool_start) * 1000

                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "result": result.data if result.success else {"error": result.error},
                    "process_info": {
                        "active_tools": [{
                            "name": tc.name,
                            "status": "completed" if result.success else "error",
                            "message": result.error if not result.success else "Completado",
                            "elapsed_ms": tool_elapsed,
                        }],
                    },
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result.to_json(),
                })

        # Max iterations reached
        yield {
            "type": "error",
            "error": "Maximum iterations reached",
        }

    async def _try_sil_fast_path_stream(
        self,
        query: str,
        tenant_id: str,
    ) -> Optional[AsyncGenerator[Dict[str, Any], None]]:
        """
        Try SIL fast path with real LLM streaming for response formatting.

        Returns an async generator that yields streaming events, or None if
        the query requires RAG (content-based search).
        """
        try:
            from app.services.sil.schemas import ReasoningType

            result = await self._sil.process_query(query, tenant_id)

            # Check if structural
            type_value = result.type.value if hasattr(result.type, 'value') else str(result.type)
            is_structural = type_value in {"structural", "temporal"}

            if not is_structural or result.requires_rag:
                return None

            # Check document count - if 0, let agentic loop handle it
            # This allows legal_search tool to check PublicKnowledge
            doc_count = result.structural_context.document_count if result.structural_context else 0
            if doc_count == 0:
                logger.info(f"🔍 SIL stream: 0 tenant documents → falling back to agentic loop")
                return None

            # Return streaming generator
            return self._stream_sil_response(query, result)

        except Exception as e:
            logger.warning(f"SIL fast path stream error: {e}")
            return None

    async def _stream_sil_response(
        self,
        query: str,
        result,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream SIL response using LLM for natural formatting."""
        ctx = result.structural_context

        # Get dynamic terminology based on entity type
        entity_type = getattr(ctx, 'entity_type', 'document')
        if ctx.details and ctx.details.get('entity_type'):
            entity_type = ctx.details['entity_type']

        # Get tenant-specific container terms if available
        custom_singular = ctx.details.get("container_term_singular") if ctx.details else None
        custom_plural = ctx.details.get("container_term_plural") if ctx.details else None

        # Terminology based on entity type (domain-agnostic)
        # Folders could be: expedientes, proyectos, clientes, obras, pacientes, etc.
        if entity_type == "folder":
            terms = {
                "singular": custom_singular or "carpeta",
                "plural": custom_plural or "carpetas"
            }
        elif entity_type == "both":
            terms = {"singular": "elemento", "plural": "elementos"}
        else:  # document
            terms = {"singular": "documento", "plural": "documentos"}

        # Build structural context for LLM
        context_parts = [
            f"Tipo de consulta: {ctx.query_type}",
            f"Tipo de entidad: {terms['plural']}",
            f"Total de {terms['plural']}: {ctx.document_count}",
        ]

        if ctx.query_result:
            if "count" in ctx.query_result:
                context_parts.append(f"Conteo: {ctx.query_result['count']}")
            if "entity" in ctx.query_result:
                context_parts.append(f"Tipo de entidad consultada: {ctx.query_result['entity']}")

        if ctx.document_titles:
            titles = ctx.document_titles[:10]
            context_parts.append(f"{terms['plural'].capitalize()}:\n" + "\n".join(f"  - {t}" for t in titles))
            if ctx.document_count > 10:
                context_parts.append(f"  ... y {ctx.document_count - 10} más")

        if ctx.folder_hierarchy:
            context_parts.append(f"Ubicación: {' > '.join(ctx.folder_hierarchy)}")

        structural_context = "\n".join(context_parts)

        # Dynamic system prompt based on entity type (domain-agnostic)
        system_prompt = f"""Eres Emma, asistente inteligente de gestión documental. Responde de forma natural, amigable y conversacional.

IMPORTANTE - TIPO DE ENTIDAD:
- El usuario está consultando sobre **{terms['plural']}**.
- Si el tipo es "carpeta" o similar, es una ESTRUCTURA ORGANIZATIVA que agrupa documentos.
- Si el tipo es "documento", es un ARCHIVO individual con contenido.

INSTRUCCIONES:
- Usa SOLO la información estructural proporcionada. NO inventes datos.
- Proporciona respuestas COMPLETAS y DETALLADAS, no solo el número.
- Usa la terminología exacta que aparece en el contexto: "{terms['singular']}" / "{terms['plural']}".
- Incluye contexto relevante: ubicaciones, ejemplos si los hay.
- Ofrece sugerencias de acciones relacionadas.
- Responde en español con tono profesional pero cercano.
- La respuesta debe tener entre 2-4 oraciones como mínimo."""

        user_prompt = f"""Pregunta del usuario: {query}

Información estructural:
{structural_context}

Responde de forma completa y útil usando la terminología del contexto ({terms['plural']}). Sugiere qué más podría interesar al usuario."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        accumulated_content = ""
        tokens_saved = ctx.document_count * 500 if ctx else 0

        try:
            # Use real LLM streaming
            async for event in self._llm_client.chat_stream(messages, max_tokens=500):
                if event.event_type == "content" and event.content:
                    accumulated_content += event.content
                    yield {"type": "content", "content": event.content}
                elif event.event_type == "done":
                    # Streaming complete
                    pass

            # Final done event
            yield {
                "type": "done",
                "result": {
                    "success": True,
                    "answer": accumulated_content,
                    "sil_answered": True,
                    "tokens_saved": tokens_saved,
                    "reasoning_type": result.type.value if hasattr(result.type, 'value') else str(result.type),
                }
            }

        except Exception as e:
            logger.warning(f"SIL LLM streaming failed, using fallback: {e}")
            # Fallback: yield complete response at once
            fallback_answer = self._format_sil_answer_fallback(ctx, result)
            yield {"type": "content", "content": fallback_answer}
            yield {
                "type": "done",
                "result": {
                    "success": True,
                    "answer": fallback_answer,
                    "sil_answered": True,
                    "tokens_saved": tokens_saved,
                    "reasoning_type": "structural",
                }
            }

    @observe(name="emma.slm_router")
    async def _try_slm_router(
        self,
        query: str,
        tenant_id: str,
        session_id: str = "",
    ) -> Optional[EmmaV2Result]:
        """
        Try to route query using SLM Router (TOON-based planning).

        Returns result if SLM Router can handle the query (GRAPH_ONLY or VECTOR_ONLY).
        Returns None for ASK_CLARIFY or if routing fails.

        The SLM Router:
        1. Generates a TOON plan using a Small Language Model
        2. Executes the plan against appropriate data sources
        3. Returns formatted context for LLM response generation
        """
        if not self._slm_router:
            return None

        try:
            langfuse_context.update_current_observation(
                input={"query": query, "tenant_id": tenant_id, "session_id": session_id}
            )

            # Route the query through SLM Router
            result: TOONExecutionResult = await self._slm_router.route(
                query=query,
                tenant_id=tenant_id,
                session_id=session_id
            )

            if not result.success:
                logger.warning(f"SLM Router execution failed: {result.error}")
                return None

            # Handle ASK_CLARIFY - return None to let agentic loop handle
            if result.plan.route == TOONRoute.ASK_CLARIFY:
                logger.info(f"🤔 SLM Router: Query too ambiguous, asking for clarification")
                # Could return clarification question to user here
                # For now, let agentic loop handle it
                return None

            # Check for empty results
            if result.plan.route == TOONRoute.GRAPH_ONLY and result.graph_row_count == 0:
                logger.info(f"🔍 SLM Router: 0 graph results → falling back to agentic loop")
                return None

            if result.plan.route == TOONRoute.VECTOR_ONLY and result.vector_result_count == 0:
                logger.info(f"🔍 SLM Router: 0 vector results → falling back to agentic loop")
                return None

            # Format the answer using LLM
            answer = await self._format_slm_router_answer_with_llm(query, result)

            return EmmaV2Result(
                success=True,
                answer=answer,
                domain=DomainType.GENERAL,
                sil_answered=True,  # Reuse field for "fast path answered"
                tokens_saved=result.plan.confidence * 500,  # Estimate based on confidence
                metadata={
                    "slm_router_used": True,
                    "toon_route": result.plan.route.value,
                    "toon_confidence": result.plan.confidence,
                    "graph_rows": result.graph_row_count,
                    "vector_results": result.vector_result_count,
                    "execution_time_ms": result.total_execution_time_ms,
                },
            )

        except Exception as e:
            logger.warning(f"SLM Router error: {e}")
            return None

    async def _format_slm_router_answer_with_llm(
        self,
        query: str,
        result: TOONExecutionResult,
    ) -> str:
        """
        Use LLM to format SLM Router results into natural response.

        The context_for_llm from the TOON execution result contains
        the formatted structural/vector results ready for interpretation.
        """
        if not result.context_for_llm:
            # Format the context if not already done
            result.format_context()

        if not result.context_for_llm:
            return "Lo siento, no encontré información relevante para tu consulta."

        # Build prompt for LLM
        system_prompt = """Eres un asistente de documentos. Tu tarea es interpretar los resultados de búsqueda y responder de forma clara y concisa.

Reglas:
1. Responde DIRECTAMENTE a la pregunta del usuario
2. Usa la información proporcionada en el contexto
3. Si hay conteos, menciona los números exactos
4. Si hay listas, presenta los items de forma organizada
5. Mantén un tono profesional y amigable
6. NO inventes información que no esté en el contexto"""

        user_prompt = f"""Pregunta del usuario: {query}

Contexto de la búsqueda:
{result.context_for_llm}

Responde a la pregunta del usuario basándote en el contexto proporcionado:"""

        try:
            response = await self._llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            if response and response.content:
                return response.content.strip()

        except Exception as e:
            logger.warning(f"SLM Router LLM formatting failed: {e}")

        # Fallback: return raw context
        return f"Resultados encontrados:\n{result.context_for_llm}"

    @observe(name="emma.sil_fast_path")
    async def _try_sil_fast_path(
        self,
        query: str,
        tenant_id: str,
    ) -> Optional[EmmaV2Result]:
        """
        Try to answer query using SIL (Structural Intelligence Layer).

        Returns result if query is structural (count, list, exists, location).
        Returns None if content-based RAG is needed.
        """
        langfuse_context.update_current_observation(
            input={"query": query, "tenant_id": tenant_id}
        )
        try:
            from app.services.sil.schemas import ReasoningType

            result = await self._sil.process_query(query, tenant_id)

            # Debug logging
            logger.info(f"🔍 SIL result.type = {result.type} (type: {type(result.type).__name__})")
            logger.info(f"🔍 SIL result.requires_rag = {result.requires_rag}")
            logger.info(f"🔍 ReasoningType.STRUCTURAL = {ReasoningType.STRUCTURAL} (type: {type(ReasoningType.STRUCTURAL).__name__})")

            # Compare with string value to handle use_enum_values=True
            type_value = result.type.value if hasattr(result.type, 'value') else str(result.type)
            is_structural = type_value in {"structural", "temporal"}
            logger.info(f"🔍 type_value = {type_value}, is_structural = {is_structural}")

            # Only use SIL fast path for purely structural queries
            if is_structural:
                if not result.requires_rag:
                    # Check document count - if 0, let agentic loop handle it
                    # This allows legal_search tool to check PublicKnowledge
                    doc_count = result.structural_context.document_count if result.structural_context else 0
                    if doc_count == 0:
                        logger.info(f"🔍 SIL found 0 tenant documents → falling back to agentic loop (may search PublicKnowledge)")
                        return None

                    # Format structural answer using LLM for natural response
                    answer = await self._format_sil_answer_with_llm(query, result)

                    return EmmaV2Result(
                        success=True,
                        answer=answer,
                        domain=DomainType.GENERAL,
                        sil_answered=True,
                        tokens_saved=doc_count * 500,
                        metadata={
                            "reasoning_type": result.type.value if hasattr(result.type, 'value') else str(result.type),
                            "cypher_query": result.cypher_result.query if result.cypher_result else None,
                        },
                    )

            return None

        except Exception as e:
            logger.warning(f"SIL fast path error: {e}")
            return None

    async def _format_sil_answer_with_llm(self, query: str, result) -> str:
        """
        Use LLM to interpret structural context into natural response.

        This follows the SIL architecture: LLM receives structural context only,
        not full document content. Typical input: ~200-400 tokens.
        """
        ctx = result.structural_context
        if not ctx:
            return result.reasoning_explanation or "Consulta procesada."

        # Get dynamic terminology based on entity type
        entity_type = getattr(ctx, 'entity_type', 'document')
        if ctx.details and ctx.details.get('entity_type'):
            entity_type = ctx.details['entity_type']

        # Get tenant-specific container terms if available
        custom_singular = ctx.details.get("container_term_singular") if ctx.details else None
        custom_plural = ctx.details.get("container_term_plural") if ctx.details else None

        # Terminology based on entity type (domain-agnostic)
        # Folders could be: expedientes, proyectos, clientes, obras, pacientes, etc.
        if entity_type == "folder":
            singular = custom_singular or "carpeta"
            plural = custom_plural or "carpetas"
            terms = {"singular": singular, "plural": plural, "found": f"{plural.capitalize()} encontrados"}
        elif entity_type == "both":
            terms = {"singular": "elemento", "plural": "elementos", "found": "Elementos encontrados"}
        else:  # document
            terms = {"singular": "documento", "plural": "documentos", "found": "Documentos encontrados"}

        # Build structural context for LLM
        context_parts = [
            f"Tipo de consulta: {ctx.query_type}",
            f"Tipo de entidad: {terms['plural']}",
            f"Total de {terms['plural']} encontrados: {ctx.document_count}",
        ]

        # Add query result details
        if ctx.query_result:
            if "count" in ctx.query_result:
                context_parts.append(f"Conteo exacto: {ctx.query_result['count']}")
            if "exists" in ctx.query_result:
                context_parts.append(f"Existe: {'Sí' if ctx.query_result['exists'] else 'No'}")
            if "entity" in ctx.query_result:
                context_parts.append(f"Tipo de entidad consultada: {ctx.query_result['entity']}")

        # Add titles (max 10)
        if ctx.document_titles:
            titles = ctx.document_titles[:10]
            context_parts.append(f"{terms['found']}:\n" + "\n".join(f"  - {t}" for t in titles))
            if ctx.document_count > 10:
                context_parts.append(f"  ... y {ctx.document_count - 10} más")

        # Add folder info
        if ctx.folder_hierarchy:
            context_parts.append(f"Ubicación: {' > '.join(ctx.folder_hierarchy)}")

        # Add types breakdown if available
        if hasattr(ctx, 'types_breakdown') and ctx.types_breakdown:
            types_str = ", ".join(f"{k}: {v}" for k, v in ctx.types_breakdown.items())
            context_parts.append(f"Tipos: {types_str}")

        structural_context = "\n".join(context_parts)

        # Dynamic system prompt based on entity type (domain-agnostic)
        system_prompt = f"""Eres Emma, asistente inteligente de gestión documental. Responde de forma natural, amigable y conversacional.

IMPORTANTE - TIPO DE ENTIDAD:
- El usuario está consultando sobre **{terms['plural']}**.
- Si el tipo es "carpeta" o similar, es una ESTRUCTURA ORGANIZATIVA que agrupa documentos.
- Si el tipo es "documento", es un ARCHIVO individual con contenido.

INSTRUCCIONES:
- Usa SOLO la información estructural proporcionada. NO inventes datos.
- Proporciona respuestas COMPLETAS y DETALLADAS, no solo el número.
- Usa la terminología exacta que aparece en el contexto: "{terms['singular']}" / "{terms['plural']}".
- Incluye contexto relevante: ubicaciones, fechas si están disponibles.
- Si hay {terms['plural']} listados, menciona algunos ejemplos representativos.
- Ofrece sugerencias de acciones relacionadas.
- Responde en español con tono profesional pero cercano.
- La respuesta debe tener entre 2-4 oraciones como mínimo."""

        user_prompt = f"""Pregunta del usuario: {query}

Información estructural obtenida:
{structural_context}

Responde de forma completa y útil basándote en esta información. Usa la terminología del contexto ({terms['plural']}) y sugiere qué más podría querer saber el usuario."""

        try:
            # Use LLM for natural interpretation
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            response = await self._llm_client.chat(messages, max_tokens=500)

            if response and response.content and response.content.strip():
                logger.info(f"✨ SIL answer formatted by LLM ({len(response.content)} chars)")
                return response.content.strip()

        except Exception as e:
            logger.warning(f"LLM formatting failed, using fallback: {e}")

        # Fallback to simple templates if LLM fails
        return self._format_sil_answer_fallback(ctx, result)

    def _format_sil_answer_fallback(self, ctx, result) -> str:
        """Fallback template-based formatting if LLM fails."""
        # Get dynamic terminology based on entity type
        entity_type = getattr(ctx, 'entity_type', 'document')
        if ctx.details and ctx.details.get('entity_type'):
            entity_type = ctx.details['entity_type']

        # Get tenant-specific container terms if available
        custom_singular = ctx.details.get("container_term_singular") if ctx.details else None
        custom_plural = ctx.details.get("container_term_plural") if ctx.details else None

        # Terminology based on entity type (domain-agnostic)
        if entity_type == "folder":
            singular = custom_singular or "carpeta"
            plural = custom_plural or "carpetas"
        elif entity_type == "both":
            singular, plural = "elemento", "elementos"
        else:  # document
            singular, plural = "documento", "documentos"

        # Handle folder-specific query types
        if ctx.query_type in ("folder_count", "folder_list", "folder_exists", "folder_contents"):
            singular = custom_singular or "carpeta"
            plural = custom_plural or "carpetas"

        if ctx.query_type in ("count", "folder_count"):
            count = ctx.query_result.get("count", ctx.document_count) if ctx.query_result else ctx.document_count
            response = f"Tienes **{count} {plural if count != 1 else singular}** en tu repositorio."

            # Add type breakdown if available
            if hasattr(ctx, 'types_breakdown') and ctx.types_breakdown:
                types_info = ", ".join(f"{v} {k}" for k, v in list(ctx.types_breakdown.items())[:5])
                response += f" Incluyen: {types_info}."

            # Add folder info if available
            if ctx.folder_hierarchy:
                response += f" Están organizados principalmente en: {ctx.folder_hierarchy[0]}."

            response += f" ¿Te gustaría que busque algún tipo específico de {singular}?"
            return response

        if ctx.query_type in ("exists", "folder_exists"):
            exists = ctx.query_result.get("exists", ctx.document_count > 0) if ctx.query_result else ctx.document_count > 0
            if exists:
                response = f"Sí, encontré **{ctx.document_count} {plural if ctx.document_count != 1 else singular}** que coinciden con tu búsqueda."
                if ctx.document_titles:
                    sample = ctx.document_titles[:3]
                    response += f" Por ejemplo: {', '.join(sample)}."
                response += " ¿Necesitas más detalles sobre alguno?"
                return response
            return f"No encontré {plural} que coincidan con tu búsqueda. ¿Podrías reformular la consulta o ser más específico?"

        if ctx.query_type in ("list", "folder_list") and ctx.document_titles:
            titles = ctx.document_titles[:10]
            titles_str = "\n".join(f"• {t}" for t in titles)
            more = f"\n... y **{ctx.document_count - 10} más**" if ctx.document_count > 10 else ""
            response = f"Encontré **{ctx.document_count} {plural if ctx.document_count != 1 else singular}**:\n\n{titles_str}{more}"
            if entity_type == "folder":
                response += f"\n\n¿Te gustaría ver el contenido de alguno de estos {plural}?"
            else:
                response += f"\n\n¿Te gustaría que analice alguno de estos {plural}?"
            return response

        if ctx.query_type == "folder_contents":
            folder_name = ctx.query_result.get("folder_name", "") if ctx.query_result else ""
            response = f"El expediente **{folder_name}** contiene **{ctx.document_count} documento(s)**."
            if ctx.document_titles:
                sample = ctx.document_titles[:5]
                response += f" Incluye: {', '.join(sample)}."
            response += " ¿Necesitas más detalles sobre algún documento?"
            return response

        if ctx.query_type == "location" and ctx.folder_hierarchy:
            path = " → ".join(ctx.folder_hierarchy)
            return f"Los {plural} están ubicados en: **{path}**. ¿Necesitas explorar esta carpeta o buscar algo específico dentro?"

        return result.reasoning_explanation or f"Encontré **{ctx.document_count} {plural if ctx.document_count != 1 else singular}** en tu repositorio. ¿En qué puedo ayudarte?"

    # =========================================================================
    # KNOWLEDGE SOURCE ROUTING METHODS
    # =========================================================================

    def _is_conversational_response(self, query: str) -> bool:
        """
        Detect if query is a short conversational response that should skip SIL.

        Examples: "Si", "No", "Ok", "Dale", "Claro", "Yes", "Sure"

        These require conversation history to understand context, so SIL
        (which is stateless) would not be able to process them correctly.
        """
        query_clean = query.strip().lower()
        query_words = len(query_clean.split())

        # Very short queries (1-2 words) that are conversational
        if query_words <= 2:
            conversational_responses = {
                # Spanish affirmative
                "si", "sí", "ok", "vale", "dale", "claro", "perfecto",
                "bueno", "bien", "de acuerdo", "correcto", "exacto",
                "eso", "asi", "así", "ajá", "aja",
                # Spanish negative
                "no", "nop", "nope", "tampoco", "ninguno",
                # English
                "yes", "yeah", "yep", "sure", "ok", "okay", "right",
                "correct", "exactly", "no", "nope", "not",
                # Requests
                "muéstrame", "muestrame", "dime", "listar", "mostrar",
                "show", "list", "tell me",
            }
            if query_clean in conversational_responses:
                return True

            # Also catch patterns like "si, por favor" or "ok gracias"
            for response in conversational_responses:
                if query_clean.startswith(response + ",") or query_clean.startswith(response + " "):
                    return True

        return False

    def _is_follow_up_query(self, query: str) -> bool:
        """
        Detect if a query is likely a follow-up to previous conversation.

        Follow-up queries are short and contextual, like:
        - "y si es por cambio de trabajo?"
        - "qué más?"
        - "puedes explicar más?"
        - "and if it's voluntary?"

        These should use conversation history for context rather than
        being classified as new standalone queries.
        """
        query_lower = query.strip().lower()
        query_words = len(query_lower.split())

        # Very short queries (< 8 words) are likely follow-ups
        if query_words < 8:
            # Check for follow-up indicators
            follow_up_patterns = [
                # Spanish
                "y si", "y en caso de", "y qué pasa", "y cuando",
                "qué más", "algo más", "puedes explicar", "más detalles",
                "cómo así", "por qué", "en ese caso", "entonces",
                "pero si", "pero qué", "pero cómo", "y cómo",
                "cuál es", "cuáles son", "dime más", "explica",
                # English
                "and if", "what if", "and what", "what about",
                "can you explain", "more details", "tell me more",
                "how so", "why is", "in that case", "then",
                "but if", "but what", "but how", "and how",
                "which is", "which are",
                # Questions referencing previous
                "eso", "esto", "ese", "esta", "lo anterior",
                "that", "this", "the previous",
            ]

            for pattern in follow_up_patterns:
                if query_lower.startswith(pattern) or pattern in query_lower:
                    return True

            # Very short questions without clear topic are likely follow-ups
            if query_words <= 5 and "?" in query:
                return True

        return False

    async def _try_sil_fast_path_with_count(
        self,
        query: str,
        tenant_id: str,
    ) -> tuple[Optional[EmmaV2Result], int]:
        """
        Try SIL fast path and return both result and document count.

        Returns:
            Tuple of (EmmaV2Result or None, document_count)
        """
        try:
            from app.services.sil.schemas import ReasoningType

            result = await self._sil.process_query(query, tenant_id)

            # Get document count
            doc_count = result.structural_context.document_count if result.structural_context else 0

            # Check if structural
            type_value = result.type.value if hasattr(result.type, 'value') else str(result.type)
            is_structural = type_value in {"structural", "temporal"}

            if is_structural and not result.requires_rag:
                # If 0 docs, let agentic loop handle (may search PublicKnowledge)
                if doc_count == 0:
                    logger.info(f"🔍 SIL found 0 tenant documents → agentic loop")
                    return None, doc_count

                # Format structural answer
                answer = await self._format_sil_answer_with_llm(query, result)

                return EmmaV2Result(
                    success=True,
                    answer=answer,
                    domain=DomainType.GENERAL,
                    sil_answered=True,
                    tokens_saved=doc_count * 500,
                    metadata={
                        "reasoning_type": type_value,
                        "cypher_query": result.cypher_result.query if result.cypher_result else None,
                    },
                ), doc_count

            return None, doc_count

        except Exception as e:
            logger.warning(f"SIL fast path error: {e}")
            return None, 0

    async def _handle_public_knowledge_query(
        self,
        query: str,
        context: ExecutionContext,
        tool_ctx: ToolContext,
        knowledge_classification: "HybridClassificationResult",
    ) -> EmmaV2Result:
        """
        Handle queries classified as PUBLIC_KNOWLEDGE.

        Skips SIL and directs the LLM to use legal_search tool directly.
        This is more efficient for legislation/BOE queries.
        """
        # Detect domain for appropriate prompt
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain

        # Build messages with a hint to use legal_search
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        # Add system hint to use legal_search for public knowledge
        legal_hint = (
            "\n\n[INSTRUCCIÓN ESPECIAL]: Esta consulta requiere información de legislación pública "
            "(BOE, estatutos, normativa). Usa la herramienta `legal_search` para buscar en la base "
            "de conocimiento público. NO uses las herramientas de búsqueda de documentos del usuario."
        )
        messages[0]["content"] += legal_hint

        # Run agentic loop
        result = await self._agentic_loop(messages, tool_ctx, domain)
        result.skills_used = skills_used
        result.knowledge_source = knowledge_classification.source.value
        result.metadata["knowledge_routing"] = {
            "source": knowledge_classification.source.value,
            "confidence": knowledge_classification.confidence,
            "stage_used": knowledge_classification.stage_used,
        }

        return result

    async def _handle_hybrid_query(
        self,
        query: str,
        context: ExecutionContext,
        tool_ctx: ToolContext,
        knowledge_classification: "HybridClassificationResult",
    ) -> EmmaV2Result:
        """
        Handle queries classified as HYBRID (need both tenant docs AND public knowledge).

        Examples:
        - "¿Mi contrato cumple con el estatuto de los trabajadores?"
        - "Compara mi nómina con lo que dice la ley"

        Skips SIL and directs the LLM to use BOTH search tools.
        """
        # Detect domain for appropriate prompt
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain

        # Build messages with a hint to use both sources
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        # Add system hint to use both search tools
        hybrid_hint = (
            "\n\n[INSTRUCCIÓN ESPECIAL]: Esta consulta requiere información de AMBAS fuentes:\n"
            "1. Documentos del usuario (usa `search` para buscar en sus documentos)\n"
            "2. Legislación pública (usa `legal_search` para buscar en BOE/normativa)\n\n"
            "IMPORTANTE: Debes consultar AMBAS fuentes para dar una respuesta completa. "
            "Por ejemplo, si el usuario pregunta si su contrato cumple con la ley, "
            "primero busca el contrato del usuario, luego busca la normativa aplicable, "
            "y finalmente compara ambos."
        )
        messages[0]["content"] += hybrid_hint

        # Run agentic loop
        result = await self._agentic_loop(messages, tool_ctx, domain)
        result.skills_used = skills_used
        result.knowledge_source = knowledge_classification.source.value
        result.metadata["knowledge_routing"] = {
            "source": knowledge_classification.source.value,
            "confidence": knowledge_classification.confidence,
            "stage_used": knowledge_classification.stage_used,
        }

        return result

    async def _collect_knowledge_example(
        self,
        query: str,
        classification: "HybridClassificationResult",
        tools_used: List[str],
        sil_doc_count: int,
        tenant_id: str,
    ) -> None:
        """
        Collect training example for knowledge source learning.

        Infers actual source from tool usage:
        - legal_search used + SIL=0 → PUBLIC_KNOWLEDGE
        - search/sil_query used + SIL>0 → TENANT_DOCUMENTS
        - Both sources used → HYBRID
        """
        if not KNOWLEDGE_ROUTER_AVAILABLE:
            return

        try:
            from app.services.nexus_router import get_knowledge_collector

            collector = get_knowledge_collector()
            await collector.collect_from_tool_usage(
                query=query,
                predicted_source=classification.source,
                tools_used=tools_used,
                sil_doc_count=sil_doc_count,
                tenant_id=tenant_id,
                metadata={
                    "confidence": classification.confidence,
                    "stage_used": classification.stage_used,
                    "ml_used": classification.ml_used,
                },
            )
        except Exception as e:
            logger.debug(f"Failed to collect knowledge example: {e}")

    async def _stream_public_knowledge_query(
        self,
        query: str,
        context: ExecutionContext,
        tool_ctx: ToolContext,
        knowledge_classification: "HybridClassificationResult",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response for PUBLIC_KNOWLEDGE queries.

        Skips SIL and directs the LLM to use legal_search tool directly.
        """
        start_time = time.time()

        # Detect domain
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain

        # Build messages with legal_search hint
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        legal_hint = (
            "\n\n[INSTRUCCIÓN ESPECIAL]: Esta consulta requiere información de legislación pública "
            "(BOE, estatutos, normativa). Usa la herramienta `legal_search` para buscar en la base "
            "de conocimiento público. NO uses las herramientas de búsqueda de documentos del usuario."
        )
        messages[0]["content"] += legal_hint

        # Stream agentic loop
        tools_called = []
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1
            accumulated_content = ""
            tool_calls = []

            async for event in self._llm_client.chat_stream(messages, EMMA_V2_TOOLS):
                if event.event_type == "content":
                    accumulated_content += event.content
                    yield {"type": "content", "content": event.content}
                elif event.event_type == "thinking":
                    yield {"type": "thinking", "content": event.thinking}
                elif event.event_type == "tool_call":
                    tool_calls.append(event.tool_call)
                    tools_called.append(event.tool_call.name)
                    yield {
                        "type": "tool_call",
                        "name": event.tool_call.name,
                        "arguments": event.tool_call.arguments,
                        "process_info": {
                            "reasoning_type": "PUBLIC_KNOWLEDGE",
                            "knowledge_source": knowledge_classification.source.value,
                            "active_tools": [{
                                "name": event.tool_call.name,
                                "status": "running",
                            }],
                        },
                    }
                elif event.event_type == "error":
                    yield {"type": "error", "error": event.error}
                    return

            # If no tool calls, we're done
            if not tool_calls:
                latency_ms = (time.time() - start_time) * 1000
                result = EmmaV2Result(
                    success=True,
                    answer=accumulated_content,
                    domain=domain,
                    knowledge_source=knowledge_classification.source.value,
                    tools_called=tools_called,
                    skills_used=skills_used,
                    iterations=iterations,
                    latency_ms=latency_ms,
                    thread_id=context.thread_id or "",
                )
                result_dict = result.to_dict()
                result_dict["process_info"] = {
                    "reasoning_type": "PUBLIC_KNOWLEDGE",
                    "reasoning_message": "Consulta de legislación pública",
                    "knowledge_source": knowledge_classification.source.value,
                    "tokens_saved": 0,
                    "sil_used": False,
                    "active_tools": [{"name": t, "status": "completed"} for t in tools_called],
                }
                yield {"type": "done", "result": result_dict}

                # IMPORTANT: Save to conversation history for context continuity
                if context.thread_id:
                    await self._save_to_history(
                        context.thread_id, query, accumulated_content,
                        knowledge_source=knowledge_classification.source.value
                    )

                # Collect example for learning
                await self._collect_knowledge_example(
                    query, knowledge_classification, tools_called, 0, context.tenant_id
                )
                return

            # Execute tool calls
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in tool_calls
                ]
            })

            for tc in tool_calls:
                tool_start = time.time()
                result = await execute_tool(tc.name, tc.arguments, tool_ctx)
                tool_elapsed = (time.time() - tool_start) * 1000

                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "result": result.data if result.success else {"error": result.error},
                    "process_info": {
                        "active_tools": [{
                            "name": tc.name,
                            "status": "completed" if result.success else "error",
                            "elapsed_ms": tool_elapsed,
                        }],
                    },
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result.to_json(),
                })

        # Max iterations
        yield {"type": "error", "error": "Maximum iterations reached"}

    async def _stream_hybrid_query(
        self,
        query: str,
        context: ExecutionContext,
        tool_ctx: ToolContext,
        knowledge_classification: "HybridClassificationResult",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response for HYBRID queries (need both tenant docs AND public knowledge).

        Examples:
        - "¿Mi contrato cumple con el estatuto de los trabajadores?"
        - "Compara mi nómina con lo que dice la ley"
        """
        start_time = time.time()

        # Detect domain
        domain = DomainType.GENERAL
        if self.config.enable_domain_routing:
            detection = self._domain_router.detect_domain(query)
            domain = detection.domain

        # Build messages with hybrid hint
        skills_used = []
        messages = await self._build_messages(query, context, domain, skills_used)

        hybrid_hint = (
            "\n\n[INSTRUCCIÓN ESPECIAL]: Esta consulta requiere información de AMBAS fuentes:\n"
            "1. Documentos del usuario (usa `search` para buscar en sus documentos)\n"
            "2. Legislación pública (usa `legal_search` para buscar en BOE/normativa)\n\n"
            "IMPORTANTE: Debes consultar AMBAS fuentes para dar una respuesta completa."
        )
        messages[0]["content"] += hybrid_hint

        # Stream agentic loop
        tools_called = []
        iterations = 0

        for iteration in range(self.config.max_iterations):
            iterations = iteration + 1
            accumulated_content = ""
            tool_calls = []

            async for event in self._llm_client.chat_stream(messages, EMMA_V2_TOOLS):
                if event.event_type == "content":
                    accumulated_content += event.content
                    yield {"type": "content", "content": event.content}
                elif event.event_type == "thinking":
                    yield {"type": "thinking", "content": event.thinking}
                elif event.event_type == "tool_call":
                    tool_calls.append(event.tool_call)
                    tools_called.append(event.tool_call.name)
                    yield {
                        "type": "tool_call",
                        "name": event.tool_call.name,
                        "arguments": event.tool_call.arguments,
                        "process_info": {
                            "reasoning_type": "HYBRID",
                            "knowledge_source": knowledge_classification.source.value,
                            "active_tools": [{
                                "name": event.tool_call.name,
                                "status": "running",
                            }],
                        },
                    }
                elif event.event_type == "error":
                    yield {"type": "error", "error": event.error}
                    return

            # If no tool calls, we're done
            if not tool_calls:
                latency_ms = (time.time() - start_time) * 1000
                result = EmmaV2Result(
                    success=True,
                    answer=accumulated_content,
                    domain=domain,
                    knowledge_source=knowledge_classification.source.value,
                    tools_called=tools_called,
                    skills_used=skills_used,
                    iterations=iterations,
                    latency_ms=latency_ms,
                    thread_id=context.thread_id or "",
                )
                result_dict = result.to_dict()
                result_dict["process_info"] = {
                    "reasoning_type": "HYBRID",
                    "reasoning_message": "Consulta híbrida (documentos + legislación)",
                    "knowledge_source": knowledge_classification.source.value,
                    "tokens_saved": 0,
                    "sil_used": False,
                    "active_tools": [{"name": t, "status": "completed"} for t in tools_called],
                }
                yield {"type": "done", "result": result_dict}

                # Save to conversation history
                if context.thread_id:
                    await self._save_to_history(
                        context.thread_id, query, accumulated_content,
                        knowledge_source=knowledge_classification.source.value
                    )

                # Collect example for learning
                await self._collect_knowledge_example(
                    query, knowledge_classification, tools_called, 0, context.tenant_id
                )
                return

            # Execute tool calls
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        }
                    }
                    for tc in tool_calls
                ]
            })

            for tc in tool_calls:
                tool_start = time.time()
                result = await execute_tool(tc.name, tc.arguments, tool_ctx)
                tool_elapsed = (time.time() - tool_start) * 1000

                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "result": result.data if result.success else {"error": result.error},
                    "process_info": {
                        "active_tools": [{
                            "name": tc.name,
                            "status": "completed" if result.success else "error",
                            "elapsed_ms": tool_elapsed,
                        }],
                    },
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result.to_json(),
                })

        # Max iterations
        yield {"type": "error", "error": "Maximum iterations reached"}

    async def _build_messages(
        self,
        query: str,
        context: ExecutionContext,
        domain: DomainType,
        skills_used: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build message list for LLM chat."""
        messages = []

        # System message with domain-specific prompt
        tenant_context = f"[Tenant: {context.tenant_id}]"
        if context.user_id:
            tenant_context += f" [User: {context.user_id}]"

        # Get structural summary from SIL (live query, no duplication)
        learned_terminology = None
        try:
            learned_terminology = await self._knowledge_service.get_structural_summary(
                tenant_id=context.tenant_id
            )
            if learned_terminology:
                logger.debug(f"Loaded structural summary for tenant {context.tenant_id}")
        except Exception as e:
            logger.debug(f"Could not load structural summary: {e}")

        system_prompt = get_system_prompt_for_domain(
            domain=domain,
            tenant_context=tenant_context,
            learned_terminology=learned_terminology,
        )

        # Load matching skills if enabled
        if self.config.enable_skills:
            skill_instructions = self._skill_loader.get_skill_instructions(
                query=query,
                domain=domain.value if domain != DomainType.GENERAL else None,
                max_tokens=self.config.max_skill_tokens,
            )

            if skill_instructions:
                # Track which skills were used
                matches = self._skill_loader.match_skills(query, domain.value if domain != DomainType.GENERAL else None)
                if skills_used is not None:
                    skills_used.extend([m.skill.name for m in matches])

                # Append skill instructions to system prompt
                system_prompt += f"\n\n## Procedimientos y Conocimiento Especializado\n\n{skill_instructions}"

                logger.debug(
                    f"Loaded {len(matches)} skills: {[m.skill.name for m in matches]} "
                    f"({len(skill_instructions)} chars)"
                )

        messages.append({
            "role": "system",
            "content": system_prompt,
        })

        # Load conversation history if thread exists
        if context.thread_id:
            history = await self._load_history(context.thread_id)
            messages.extend(history)

        # Add current query
        messages.append({
            "role": "user",
            "content": query,
        })

        return messages

    @observe(name="emma.agentic_loop")
    async def _agentic_loop(
        self,
        messages: List[Dict[str, Any]],
        tool_ctx: ToolContext,
        domain: DomainType,
    ) -> EmmaV2Result:
        """
        Run the agentic loop with tool execution.

        The loop continues until:
        1. LLM returns a response without tool calls
        2. Maximum iterations reached
        """
        langfuse_context.update_current_observation(
            metadata={
                "domain": domain.value,
                "max_iterations": self.config.max_iterations,
            }
        )
        tools_called = []

        for iteration in range(self.config.max_iterations):
            # Call LLM
            response = await self._llm_client.chat(messages, EMMA_V2_TOOLS)

            # If no tool calls, we're done
            if not response.has_tool_calls:
                # Update Langfuse with final output
                langfuse_context.update_current_observation(
                    output={
                        "answer": response.content[:500] + "..." if len(response.content) > 500 else response.content,
                        "iterations": iteration + 1,
                        "tools_called": tools_called,
                    }
                )
                return EmmaV2Result(
                    success=True,
                    answer=response.content,
                    domain=domain,
                    tools_called=tools_called,
                    iterations=iteration + 1,
                )

            # Execute tool calls (potentially in parallel)
            messages.append(response.to_assistant_message())

            # Execute tools
            tool_results = await self._execute_tools_parallel(
                response.tool_calls,
                tool_ctx,
            )

            for tc, result in zip(response.tool_calls, tool_results):
                tools_called.append(tc.name)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result.to_json(),
                })

        # Max iterations - return last content
        return EmmaV2Result(
            success=True,
            answer=messages[-1].get("content", "Se alcanzó el máximo de iteraciones."),
            domain=domain,
            tools_called=tools_called,
            iterations=self.config.max_iterations,
            metadata={"truncated": True},
        )

    async def _execute_tools_parallel(
        self,
        tool_calls: List[ToolCall],
        ctx: ToolContext,
    ) -> List[ToolResult]:
        """Execute multiple tool calls in parallel."""
        if len(tool_calls) == 1:
            result = await execute_tool(
                tool_calls[0].name,
                tool_calls[0].arguments,
                ctx,
            )
            return [result]

        # Execute in parallel
        tasks = [
            execute_tool(tc.name, tc.arguments, ctx)
            for tc in tool_calls
        ]
        return await asyncio.gather(*tasks)

    async def _load_history(self, thread_id: str, max_messages: int = 20) -> List[Dict[str, Any]]:
        """Load conversation history from Redis."""
        if not self._redis:
            return []

        try:
            key = f"{THREAD_KEY_PREFIX}{thread_id}"
            history_json = await self._redis.get(key)

            if history_json:
                history = json.loads(history_json)
                return history[-max_messages:]

            return []

        except Exception as e:
            logger.warning(f"Failed to load history: {e}")
            return []

    async def _save_to_history(
        self,
        thread_id: str,
        query: str,
        answer: str,
        knowledge_source: Optional[str] = None,
    ) -> None:
        """Save conversation turn to Redis."""
        if not self._redis:
            return

        try:
            key = f"{THREAD_KEY_PREFIX}{thread_id}"

            # Load existing
            history_json = await self._redis.get(key)
            history = json.loads(history_json) if history_json else []

            # Append new turn
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": answer})

            # Keep last N messages
            history = history[-40:]

            # Save with TTL
            await self._redis.setex(
                key,
                self.config.thread_ttl_seconds,
                json.dumps(history),
            )

            # Also save knowledge_source for follow-up context
            if knowledge_source:
                await self._redis.setex(
                    f"{key}:knowledge_source",
                    self.config.thread_ttl_seconds,
                    knowledge_source,
                )
                logger.debug(f"Saved knowledge_source={knowledge_source} for thread {thread_id}")

        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

    async def _get_last_knowledge_source(self, thread_id: str) -> Optional[str]:
        """Get the last knowledge_source from the conversation history."""
        if not self._redis or not thread_id:
            return None

        try:
            key = f"{THREAD_KEY_PREFIX}{thread_id}:knowledge_source"
            return await self._redis.get(key)
        except Exception as e:
            logger.debug(f"Failed to get last knowledge_source: {e}")
            return None


# =============================================================================
# Factory Functions
# =============================================================================

_emma_v2_instance: Optional[EmmaV2] = None


async def get_emma_v2() -> EmmaV2:
    """Get global Emma v2 instance."""
    global _emma_v2_instance
    if _emma_v2_instance is None:
        _emma_v2_instance = EmmaV2()
        await _emma_v2_instance.initialize()
    return _emma_v2_instance


async def reset_emma_v2() -> None:
    """Reset global Emma v2 instance."""
    global _emma_v2_instance
    _emma_v2_instance = None
