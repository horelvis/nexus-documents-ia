"""
Emma Coordinator Agent - Main AI Assistant with Multi-Pattern Orchestration

This module implements Emma as a ChatAgent that supports multiple orchestration
patterns based on the query type:

ORCHESTRATION PATTERNS:
1. HANDOFF (default): LLM decides via .as_tool() - natural delegation
2. SEQUENTIAL: Pipeline A → B → C - for step-by-step analysis
3. CONCURRENT: Parallel A | B | C - for multi-perspective analysis

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                     EMMA COORDINATOR AGENT                           │
    │                                                                      │
    │   User Query → Pattern Detection (LLM or keywords)                  │
    │                        │                                             │
    │         ┌──────────────┼──────────────┬──────────────┐              │
    │         ▼              ▼              ▼              │              │
    │     HANDOFF       SEQUENTIAL      CONCURRENT        │              │
    │   (.as_tool())     (A→B→C)        (A|B|C)           │              │
    │                                                      │              │
    │         ┌──────────────┼──────────────┬──────────────┤              │
    │         ▼              ▼              ▼              ▼              │
    │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
    │   │ Search   │  │ Contract │  │ Compliance│  │ Labor    │          │
    │   │ Agent    │  │ Agent    │  │ Agent     │  │ Agent    │          │
    │   └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
    │                                                                      │
    │   AgentThread manages full conversation context automatically        │
    │   Redis persistence via serialize()/deserialize()                    │
    └─────────────────────────────────────────────────────────────────────┘

FRAMEWORK: Microsoft Agent Framework
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from agent_framework import ChatAgent, AgentThread
from agent_framework.openai import OpenAIChatClient

from app.agents.config import agent_config
from app.core.execution_context import set_execution_context, clear_execution_context


# Shared Redis connection pool (singleton)
# This prevents creating new connections for each EmmaCoordinator instance
_redis_pool: Optional[ConnectionPool] = None


def get_redis_pool() -> ConnectionPool:
    """
    Get or create shared Redis connection pool.

    Using a connection pool instead of individual connections:
    1. Reduces connection overhead under load
    2. Prevents exhaustion of Redis connections
    3. Reuses connections across requests

    Returns:
        Shared ConnectionPool instance
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool(
            host=agent_config.redis_host,
            port=agent_config.redis_port,
            db=agent_config.redis_db,
            decode_responses=True,
            max_connections=20,  # Limit concurrent connections
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
        logger.info(f"✅ Created Redis connection pool (max_connections=20)")
    return _redis_pool


from app.agents.agents import (
    create_search_agent,
    create_contract_agent,
    create_compliance_agent,
    create_summarizer_agent,
    create_analyst_agent,
    create_labor_agent,
    create_fiscal_agent,
    create_privacy_agent,
)
from app.agents.orchestration import (
    OrchestrationPattern,
    OrchestrationResult,
    detect_orchestration_pattern,
    get_agents_for_pattern,
    get_sequential_orchestration,
    get_concurrent_orchestration,
)
from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Redis configuration
EMMA_THREAD_KEY_PREFIX = "emma:coordinator:thread:"
EMMA_THREAD_TTL_SECONDS = 3600  # 1 hour (longer for better context retention)


def clean_thinking_tags(text: str) -> str:
    """
    Remove Qwen3 thinking tags from LLM output.

    Qwen3 uses <think>...</think> tags for chain-of-thought reasoning.
    This function removes these tags and returns only the final answer.

    Args:
        text: Raw LLM output that may contain thinking tags

    Returns:
        Cleaned text with thinking content removed
    """
    if "</think>" in text:
        return text.split("</think>")[-1].strip()
    return text


# Default Emma system message (FALLBACK ONLY - Edit emma_prompts.yaml instead)
# This is used only if the YAML file is not available or fails to load.
# The primary source of truth is: config/prompts/emma_prompts.yaml -> autogen_agents.EmmaCoordinator
DEFAULT_EMMA_INSTRUCTIONS = """You are Emma, an intelligent document management assistant.
Respond in the same language the user writes in.
Use the available tools (search_agent, contract_agent, compliance_agent, etc.) to help users.
Always use the exact tenant_id from [Tenant: xxx] when calling tools.
"""


@dataclass
class EmmaCoordinatorResult:
    """Result from EmmaCoordinator execution."""
    success: bool
    answer: str
    agents_delegated: List[str]
    tools_called: List[str]
    execution_time_ms: float
    thread_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmmaCoordinator:
    """
    Emma Coordinator Agent - Main entry point for all queries.

    Uses Microsoft Agent Framework's native capabilities:
    - ChatAgent as the main coordinator
    - .as_tool() to convert specialist agents into callable tools
    - AgentThread for automatic conversation context management
    - serialize()/deserialize() for Redis persistence

    This solves the context loss problem by letting the framework
    manage conversation state instead of manual prompt engineering.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        Initialize EmmaCoordinator.

        Args:
            redis_client: Redis client for thread persistence (creates one if None)
        """
        self._redis = redis_client
        self._client: Optional[OpenAIChatClient] = None
        self._emma: Optional[ChatAgent] = None
        self._subagents: Dict[str, ChatAgent] = {}
        self._initialized = False

        # Orchestration patterns
        self._sequential = None
        self._concurrent = None

    async def initialize(self) -> None:
        """Initialize Emma and all subagents."""
        if self._initialized:
            return

        # Create OpenAI-compatible client pointing to vLLM
        self._client = OpenAIChatClient(
            api_key="dummy",  # vLLM doesn't need a real key
            base_url=agent_config.vllm_base_url,
            model_id=agent_config.vllm_model
        )

        # Initialize Redis using shared connection pool (not individual connection)
        # This prevents connection exhaustion under load
        if self._redis is None:
            pool = get_redis_pool()
            self._redis = redis.Redis(connection_pool=pool)

        # Create all specialist subagents
        self._create_subagents()

        # Create Emma coordinator with subagents as tools
        self._create_emma_coordinator()

        # Initialize orchestration patterns
        self._sequential = get_sequential_orchestration()
        self._concurrent = get_concurrent_orchestration()

        # Set aggregator for concurrent (uses summarizer agent)
        if "summarizer_agent" in self._subagents:
            self._concurrent.set_aggregator(self._subagents["summarizer_agent"])

        self._initialized = True
        logger.info(f"✅ EmmaCoordinator initialized with {len(self._subagents)} subagent tools + orchestration patterns")

    def _create_subagents(self) -> None:
        """Create all specialist subagents."""
        self._subagents = {
            "search_agent": create_search_agent(self._client),
            "contract_agent": create_contract_agent(self._client),
            "compliance_agent": create_compliance_agent(self._client),
            "analyst_agent": create_analyst_agent(self._client),
            "summarizer_agent": create_summarizer_agent(self._client),
            "labor_agent": create_labor_agent(self._client),
            "fiscal_agent": create_fiscal_agent(self._client),
            "privacy_agent": create_privacy_agent(self._client),
        }

        logger.info(f"Created {len(self._subagents)} specialist subagents")

    def _create_emma_coordinator(self) -> None:
        """
        Create Emma as the main coordinator agent.

        Uses .as_tool() to convert each subagent into a callable tool,
        enabling natural LLM-based delegation without external routing.
        """
        # Convert subagents to tools using .as_tool()
        subagent_tools = []
        for name, agent in self._subagents.items():
            # .as_tool() creates a tool that lets Emma delegate to this agent
            tool = agent.as_tool(
                name=name,
                description=self._get_agent_description(name)
            )
            subagent_tools.append(tool)
            logger.debug(f"Converted {name} to tool")

        # Load Emma's instructions from YAML or use default
        instructions = get_agent_system_message(
            "EmmaCoordinator",
            DEFAULT_EMMA_INSTRUCTIONS
        )

        # Create Emma coordinator with all subagent tools
        self._emma = ChatAgent(
            name="Emma",
            chat_client=self._client,
            instructions=instructions,
            tools=subagent_tools,
        )

        logger.info(f"Created Emma coordinator with {len(subagent_tools)} subagent tools")

    def _get_agent_description(self, agent_name: str) -> str:
        """Get description for each subagent tool."""
        descriptions = {
            "search_agent": "Busca documentos, archivos y correos electrónicos. Usa para: 'busca', 'encuentra', 'muéstrame documentos'",
            "contract_agent": "Analiza contratos, cláusulas y obligaciones legales. Usa para: 'contrato', 'cláusula', 'términos'",
            "compliance_agent": "Verifica cumplimiento GDPR/RGPD y normativo. Usa para: 'gdpr', 'rgpd', 'cumplimiento'",
            "analyst_agent": "Realiza análisis profundo de documentos. Usa para: 'analiza', 'evalúa', 'examina', 'riesgos'",
            "summarizer_agent": "Crea resúmenes ejecutivos. Usa para: 'resume', 'resumen', 'sintetiza', 'puntos clave'",
            "labor_agent": "Especialista en derecho laboral español. Usa para: 'laboral', 'despido', 'nómina', 'convenio'",
            "fiscal_agent": "Especialista en temas fiscales e impuestos. Usa para: 'impuesto', 'iva', 'irpf', 'fiscal'",
            "privacy_agent": "Especialista en protección de datos (LOPDGDD). Usa para: 'lopdgdd', 'protección de datos'",
        }
        return descriptions.get(agent_name, f"Specialist agent: {agent_name}")

    def _get_thread_key(self, tenant_id: str, session_id: str) -> str:
        """Get Redis key for thread storage."""
        return f"{EMMA_THREAD_KEY_PREFIX}{tenant_id}:{session_id}"

    async def _load_thread(
        self,
        tenant_id: str,
        session_id: str
    ) -> AgentThread:
        """
        Load existing thread from Redis or create new one.

        AgentThread automatically maintains full conversation history,
        solving the context loss problem.
        """
        thread, _ = await self._load_thread_with_status(tenant_id, session_id)
        return thread

    async def _load_thread_with_status(
        self,
        tenant_id: str,
        session_id: str
    ) -> tuple[AgentThread, bool]:
        """
        Load existing thread from Redis or create new one.
        Returns (thread, is_new_session) tuple.

        is_new_session=True means this is the first message in the session,
        useful for injecting user context and Emma's introduction.
        """
        key = self._get_thread_key(tenant_id, session_id)

        try:
            serialized_json = await self._redis.get(key)

            if serialized_json:
                logger.info(f"📜 Loading existing Emma thread: {session_id[:16]}...")
                serialized_dict = json.loads(serialized_json)
                thread = await AgentThread.deserialize(serialized_dict)
                return thread, False  # Existing session

        except Exception as e:
            logger.warning(f"⚠️ Failed to load thread from Redis: {e}")

        # Create new thread
        logger.info(f"🆕 Creating new Emma thread: {session_id[:16]}...")
        return self._emma.get_new_thread(), True  # New session

    async def _save_thread(
        self,
        thread: AgentThread,
        tenant_id: str,
        session_id: str
    ) -> None:
        """Save thread to Redis for persistence."""
        key = self._get_thread_key(tenant_id, session_id)

        try:
            serialized_dict = await thread.serialize()
            serialized_json = json.dumps(serialized_dict, default=str)
            await self._redis.setex(key, EMMA_THREAD_TTL_SECONDS, serialized_json)
            logger.debug(f"💾 Saved Emma thread: {session_id[:16]}...")

        except Exception as e:
            logger.warning(f"⚠️ Failed to save thread to Redis: {e}")

    async def execute(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        orchestration_hint: Optional[str] = None
    ) -> EmmaCoordinatorResult:
        """
        Execute a query using the optimal orchestration pattern.

        Pattern selection:
        1. If orchestration_hint provided, use that pattern
        2. Otherwise, detect pattern from query (keywords + LLM)
        3. Execute using appropriate orchestration:
           - HANDOFF: LLM decides via .as_tool() (default)
           - SEQUENTIAL: Pipeline execution A → B → C
           - CONCURRENT: Parallel execution A | B | C

        Args:
            query: User's question/task
            tenant_id: Tenant identifier
            session_id: Session identifier for thread persistence
            user_id: Optional user identifier
            user_context: Optional user context (name, preferences)
            orchestration_hint: Optional explicit pattern ("sequential", "concurrent", "handoff")

        Returns:
            EmmaCoordinatorResult with answer and orchestration metadata
        """
        start_time = time.perf_counter()

        if not self._initialized:
            await self.initialize()

        # Set execution context for @ai_function tools
        # This ensures tenant_id is available via contextvars, eliminating
        # dependency on LLM to extract it from the prompt correctly
        set_execution_context(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id
        )

        try:
            # Determine orchestration pattern
            if orchestration_hint:
                pattern = OrchestrationPattern(orchestration_hint.lower())
                logger.info(f"📋 Using explicit orchestration hint: {pattern.value}")
            else:
                pattern = await detect_orchestration_pattern(
                    query,
                    use_llm=True,
                    vllm_base_url=agent_config.vllm_base_url,
                    vllm_model=agent_config.vllm_model
                )
                logger.info(f"🔍 Detected orchestration pattern: {pattern.value}")

            # Route to appropriate orchestration
            if pattern == OrchestrationPattern.SEQUENTIAL:
                return await self._execute_sequential(
                    query, tenant_id, session_id, user_context, start_time
                )

            elif pattern == OrchestrationPattern.CONCURRENT:
                return await self._execute_concurrent(
                    query, tenant_id, session_id, user_context, start_time
                )

            else:  # HANDOFF (default)
                return await self._execute_handoff(
                    query, tenant_id, session_id, user_context, start_time
                )

        except Exception as e:
            logger.error(f"❌ EmmaCoordinator execution failed: {e}")
            import traceback
            traceback.print_exc()

            execution_time = (time.perf_counter() - start_time) * 1000

            return EmmaCoordinatorResult(
                success=False,
                answer=f"Error procesando la consulta: {str(e)}",
                agents_delegated=[],
                tools_called=[],
                execution_time_ms=execution_time,
                thread_id=session_id,
                metadata={"error": str(e)}
            )

        finally:
            # Always clear execution context to prevent leaking to other requests
            clear_execution_context()

    async def _prepare_execution(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]]
    ) -> tuple:
        """
        Prepare execution context - shared by execute and execute_stream.

        Returns:
            tuple: (thread, full_query, is_new_session)
        """
        # Load or create thread (this is where context lives!)
        thread, is_new_session = await self._load_thread_with_status(tenant_id, session_id)

        # Build context-aware query with user info for new sessions
        full_query = self._build_query_with_context(
            query, tenant_id, user_context, is_new_session=is_new_session
        )

        logger.info(f"🤖 Emma processing: {query[:50]}...")
        logger.info(f"📝 Full query: {full_query[:200]}...")

        return thread, full_query, is_new_session

    def _extract_tool_calls(self, response) -> tuple:
        """
        Extract tool calls from Emma response - shared by execute and execute_stream.

        Returns:
            tuple: (agents_delegated, tools_called)
        """
        agents_delegated = []
        tools_called = []

        if hasattr(response, 'messages'):
            logger.info(f"📤 Emma response messages count: {len(response.messages)}")
            for i, msg in enumerate(response.messages):
                msg_type = type(msg).__name__
                has_tools = hasattr(msg, 'tool_calls') and msg.tool_calls
                logger.info(f"  📤 Message[{i}]: type={msg_type}, has_tool_calls={has_tools}")
                if has_tools:
                    for tc in msg.tool_calls:
                        tool_name = tc.function.name if hasattr(tc, 'function') else str(tc)
                        logger.info(f"    🔧 Tool call: {tool_name}")
                        tools_called.append(tool_name)
                        if tool_name in self._subagents:
                            agents_delegated.append(tool_name)

        return list(set(agents_delegated)), list(set(tools_called))

    async def _execute_handoff(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]],
        start_time: float
    ) -> EmmaCoordinatorResult:
        """
        Execute using HANDOFF pattern (default).

        The LLM (Emma) naturally decides when to delegate to specialists
        based on the query content and her instructions.
        """
        # Use shared preparation logic
        thread, full_query, _ = await self._prepare_execution(
            query, tenant_id, session_id, user_context
        )

        # Execute with Emma - she'll delegate to subagents as needed
        response = await self._emma.run(full_query, thread=thread)

        # Extract answer and clean thinking tags
        answer = response.text if hasattr(response, 'text') else str(response)
        answer = clean_thinking_tags(answer)

        # Use shared tool extraction logic
        agents_delegated, tools_called = self._extract_tool_calls(response)

        # Save thread with updated context
        await self._save_thread(thread, tenant_id, session_id)

        execution_time = (time.perf_counter() - start_time) * 1000

        logger.info(f"📤 HANDOFF COMPLETE: agents={agents_delegated}, tools={tools_called}, time={execution_time:.0f}ms")

        return EmmaCoordinatorResult(
            success=True,
            answer=answer,
            agents_delegated=agents_delegated,
            tools_called=tools_called,
            execution_time_ms=execution_time,
            thread_id=session_id,
            metadata={
                "framework": "microsoft_agent_framework",
                "pattern": "handoff",
                "context_maintained": True,
                "tenant_id": tenant_id
            }
        )

    async def _execute_sequential(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]],
        start_time: float
    ) -> EmmaCoordinatorResult:
        """
        Execute using SEQUENTIAL pattern.

        Agents execute in pipeline: A → B → C, each receiving
        the output of the previous agent.
        """
        # Get agents for sequential execution based on query
        agents = get_agents_for_pattern(
            OrchestrationPattern.SEQUENTIAL,
            query,
            self._subagents
        )

        if not agents:
            logger.warning("⚠️ No agents selected for SEQUENTIAL, falling back to HANDOFF")
            return await self._execute_handoff(
                query, tenant_id, session_id, user_context, start_time
            )

        logger.info(f"🔗 SEQUENTIAL: {' → '.join([a.name for a in agents])}")

        # Execute sequential orchestration
        result: OrchestrationResult = await self._sequential.execute(
            task=query,
            tenant_id=tenant_id,
            session_id=session_id,
            agents=agents
        )

        return EmmaCoordinatorResult(
            success=result.success,
            answer=result.answer,
            agents_delegated=result.agents_executed,
            tools_called=result.tools_called,
            execution_time_ms=result.execution_time_ms,
            thread_id=session_id,
            metadata={
                "framework": "microsoft_agent_framework",
                "pattern": "sequential",
                "pipeline": [a.name for a in agents],
                "intermediate_results_count": len(result.intermediate_results),
                "tenant_id": tenant_id,
                **result.metadata
            }
        )

    async def _execute_concurrent(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]],
        start_time: float
    ) -> EmmaCoordinatorResult:
        """
        Execute using CONCURRENT pattern.

        Multiple agents execute in parallel, results are aggregated.
        """
        # Get agents for concurrent execution based on query
        agents = get_agents_for_pattern(
            OrchestrationPattern.CONCURRENT,
            query,
            self._subagents
        )

        if not agents:
            logger.warning("⚠️ No agents selected for CONCURRENT, falling back to HANDOFF")
            return await self._execute_handoff(
                query, tenant_id, session_id, user_context, start_time
            )

        logger.info(f"🔀 CONCURRENT: {' | '.join([a.name for a in agents])}")

        # Execute concurrent orchestration
        result: OrchestrationResult = await self._concurrent.execute(
            task=query,
            tenant_id=tenant_id,
            session_id=session_id,
            agents=agents
        )

        return EmmaCoordinatorResult(
            success=result.success,
            answer=result.answer,
            agents_delegated=result.agents_executed,
            tools_called=result.tools_called,
            execution_time_ms=result.execution_time_ms,
            thread_id=session_id,
            metadata={
                "framework": "microsoft_agent_framework",
                "pattern": "concurrent",
                "parallel_agents": [a.name for a in agents],
                "aggregated": result.metadata.get("aggregated", False),
                "successful_agents": result.metadata.get("successful_agents", 0),
                "tenant_id": tenant_id
            }
        )

    def _build_query_with_context(
        self,
        query: str,
        tenant_id: str,
        user_context: Optional[Dict[str, Any]] = None,
        is_new_session: bool = False
    ) -> str:
        """
        Build query with tenant and user context.

        For new sessions, injects user information so Emma can:
        1. Greet the user by name
        2. Remember their profession/role
        3. Personalize her introduction
        """
        context_parts = []

        # Add tenant context (required for all tool calls)
        context_parts.append(f"[Tenant: {tenant_id}]")

        # Add document context if user is asking about a specific document
        if user_context and user_context.get("document_id"):
            doc_id = user_context.get("document_id")
            context_parts.append(f"[Focus Document ID: {doc_id}]")

            # Include document content for direct analysis (avoids extra LLM calls)
            if user_context.get("document_content"):
                doc_content = user_context.get("document_content")
                doc_title = user_context.get("document_title", "Document")
                # Truncate if too long (max 4000 chars for context)
                if len(doc_content) > 4000:
                    doc_content = doc_content[:4000] + "... [truncated]"
                context_parts.append(f"[Document: {doc_title}]\n{doc_content}")
            else:
                # Fallback instruction for tools
                context_parts.append(f"[IMPORTANT: When analyzing this document, use document_id='{doc_id}']")

        # Add user personalization
        if user_context:
            user_info_parts = []
            if user_context.get("name"):
                user_info_parts.append(f"Name: {user_context['name']}")
            if user_context.get("email"):
                user_info_parts.append(f"Email: {user_context['email']}")
            if user_context.get("role"):
                user_info_parts.append(f"Role: {user_context['role']}")
            if user_context.get("profession"):
                user_info_parts.append(f"Profession: {user_context['profession']}")

            if user_info_parts:
                context_parts.append(f"[User: {', '.join(user_info_parts)}]")

        context_prefix = " ".join(context_parts)
        logger.info(f"🔧 Built context prefix: {context_prefix}")

        # For new sessions, add instruction to introduce herself
        if is_new_session and user_context:
            user_name = user_context.get("name", "").split()[0] if user_context.get("name") else ""
            if user_name:
                intro_hint = f"\n[SYSTEM: This is a new conversation. The user's name is {user_name}. Greet them warmly and introduce yourself briefly.]"
                return f"{context_prefix}{intro_hint}\n\n{query}"

        return f"{context_prefix}\n\n{query}"

    async def execute_stream(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute query with aggressive streaming responses.

        Yields events as Emma processes and delegates to subagents.
        For new sessions, Emma will introduce herself and greet the user by name.

        AGGRESSIVE STREAMING:
        - Emits progress events immediately at each stage
        - Shows "thinking" indicator during LLM inference
        - Sends partial tokens as soon as available
        - Provides real-time feedback on tool delegation
        """
        if not self._initialized:
            await self.initialize()

        # Set execution context for @ai_function tools
        set_execution_context(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id
        )

        try:
            # Track execution time for performance metrics
            start_time = time.time()

            # AGGRESSIVE STREAMING: Emit context preparation event
            yield {
                "event": "progress",
                "data": {
                    "message": "Preparando contexto...",
                    "stage": "context_preparation",
                    "agent": "Emma"
                }
            }

            # Use shared preparation logic
            thread, full_query, _ = await self._prepare_execution(
                query, tenant_id, session_id, user_context
            )

            # AGGRESSIVE STREAMING: Emit thinking event before LLM call
            yield {
                "event": "progress",
                "data": {
                    "message": "Emma está pensando...",
                    "stage": "thinking",
                    "agent": "Emma"
                }
            }

            yield {
                "event": "start",
                "data": {
                    "message": "Generando respuesta...",
                    "agent": "Emma"
                }
            }

            # Stream Emma's response
            # Note: Streaming requires stateful handling of thinking tags since they
            # may span multiple chunks. For non-streaming, use clean_thinking_tags()
            thinking_buffer = ""
            in_thinking_mode = False  # Track if we're inside <think>...</think>
            final_answer = ""  # Accumulate the actual response for the complete event
            tools_used = []
            first_token_emitted = False  # Track first real token for UX feedback

            async for chunk in self._emma.run_stream(full_query, thread=thread):
                if hasattr(chunk, 'text') and chunk.text:
                    text = chunk.text

                    # Handle Qwen3 thinking tags properly for streaming
                    # Tags may be split across multiple chunks

                    # Check if thinking mode starts
                    if "<think>" in text:
                        in_thinking_mode = True
                        # Keep text before <think> (if any)
                        before_think = text.split("<think>")[0]
                        # Store the rest in buffer
                        thinking_buffer = "<think>" + text.split("<think>", 1)[1] if "<think>" in text else ""

                        if before_think.strip():
                            final_answer += before_think
                            yield {
                                "event": "token",
                                "data": {"text": before_think, "agent": "Emma"}
                            }

                        # Check if thinking also ends in same chunk
                        if "</think>" in thinking_buffer:
                            text = thinking_buffer.split("</think>")[-1]
                            thinking_buffer = ""
                            in_thinking_mode = False
                            if text.strip():
                                final_answer += text
                                yield {
                                    "event": "token",
                                    "data": {"text": text, "agent": "Emma"}
                                }
                        continue

                    # If we're in thinking mode, accumulate and check for end
                    if in_thinking_mode:
                        thinking_buffer += text
                        if "</think>" in thinking_buffer:
                            # Thinking ended, extract text after </think>
                            text = thinking_buffer.split("</think>")[-1]
                            thinking_buffer = ""
                            in_thinking_mode = False
                            if text.strip():
                                final_answer += text
                                yield {
                                    "event": "token",
                                    "data": {"text": text, "agent": "Emma"}
                                }
                        continue  # Don't yield thinking content

                    # Normal text (not in thinking mode)
                    if text.strip():
                        final_answer += text

                        # AGGRESSIVE STREAMING: Emit first_token event once
                        if not first_token_emitted:
                            first_token_emitted = True
                            elapsed_ms = int((time.time() - start_time) * 1000)
                            yield {
                                "event": "first_token",
                                "data": {
                                    "message": "Escribiendo respuesta...",
                                    "elapsed_ms": elapsed_ms,
                                    "agent": "Emma"
                                }
                            }

                    yield {
                        "event": "token",
                        "data": {
                            "text": text,
                            "agent": "Emma"
                        }
                    }

                # Track tool calls (delegations) - AGGRESSIVE STREAMING
                if hasattr(chunk, 'tool_call') and chunk.tool_call:
                    tool_name = chunk.tool_call.function.name if hasattr(chunk.tool_call, 'function') else str(chunk.tool_call)
                    logger.info(f"🔧 STREAM TOOL CALL: {tool_name}")
                    tools_used.append(tool_name)

                    # Get human-readable description for the tool
                    tool_descriptions = {
                        "search_agent": "Buscando documentos...",
                        "contract_agent": "Analizando contrato...",
                        "compliance_agent": "Verificando cumplimiento...",
                        "analyst_agent": "Analizando documento...",
                        "summarizer_agent": "Generando resumen...",
                        "labor_agent": "Consultando normativa laboral...",
                        "fiscal_agent": "Consultando normativa fiscal...",
                        "privacy_agent": "Verificando protección de datos...",
                    }
                    delegation_message = tool_descriptions.get(tool_name, f"Consultando {tool_name}...")

                    # Emit delegation event with elapsed time
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    yield {
                        "event": "delegation",
                        "data": {
                            "agent": tool_name,
                            "message": delegation_message,
                            "elapsed_ms": elapsed_ms
                        }
                    }

            # Save thread after streaming
            await self._save_thread(thread, tenant_id, session_id)

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            logger.info(f"🎬 STREAM COMPLETE: tools_used={tools_used}, time={execution_time_ms}ms")
            logger.info(f"🎬 STREAM ANSWER preview: {final_answer[:200] if final_answer else 'EMPTY'}...")

            # Send complete event with the accumulated answer
            yield {
                "event": "complete",
                "data": {
                    "success": True,
                    "agent": "Emma",
                    "answer": final_answer.strip(),
                    "tools_used": tools_used,
                    "session_id": session_id,
                    "execution_time_ms": execution_time_ms
                }
            }

        except Exception as e:
            logger.error(f"❌ Emma stream failed: {e}")
            yield {
                "event": "error",
                "data": {
                    "error": str(e),
                    "message": f"Error: {str(e)}"
                }
            }

        finally:
            # Always clear execution context to prevent leaking to other requests
            clear_execution_context()

    async def clear_context(self, tenant_id: str, session_id: str) -> bool:
        """Clear conversation context for a session."""
        key = self._get_thread_key(tenant_id, session_id)
        try:
            await self._redis.delete(key)
            logger.info(f"🗑️ Cleared Emma thread: {session_id[:16]}...")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear thread: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get coordinator status."""
        return {
            "initialized": self._initialized,
            "subagents": list(self._subagents.keys()) if self._subagents else [],
            "subagent_count": len(self._subagents) if self._subagents else 0,
            "framework": "microsoft_agent_framework",
            "context_management": "AgentThread",
            "persistence": "Redis",
            "delegation_method": ".as_tool()",
            "orchestration_patterns": {
                "handoff": True,  # Default: LLM decides via .as_tool()
                "sequential": self._sequential is not None,
                "concurrent": self._concurrent is not None,
                "detection": "keywords + LLM"
            }
        }


# Singleton instance management
_emma_coordinator: Optional[EmmaCoordinator] = None


def get_emma_coordinator() -> EmmaCoordinator:
    """Get or create the EmmaCoordinator singleton."""
    global _emma_coordinator
    if _emma_coordinator is None:
        _emma_coordinator = EmmaCoordinator()
    return _emma_coordinator


async def initialize_emma_coordinator() -> EmmaCoordinator:
    """Initialize and return the EmmaCoordinator singleton."""
    coordinator = get_emma_coordinator()
    await coordinator.initialize()
    return coordinator


def reset_emma_coordinator() -> None:
    """Reset the EmmaCoordinator singleton (for testing)."""
    global _emma_coordinator
    _emma_coordinator = None
