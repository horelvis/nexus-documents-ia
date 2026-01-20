"""
Emma Coordinator Agent - Main AI Assistant with Multi-Pattern Orchestration

This module implements Emma as a Qwen-Agent Assistant that supports multiple
orchestration patterns based on the query type:

ORCHESTRATION PATTERNS:
1. HANDOFF (default): LLM decides via tool calls - natural delegation
2. SEQUENTIAL: Pipeline A → B → C - for step-by-step analysis
3. CONCURRENT: Parallel A | B | C - for multi-perspective analysis
4. RLM_LONG: Recursive decomposition for documents >50K tokens (arXiv:2512.24601)

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                     EMMA COORDINATOR AGENT                           │
    │                                                                      │
    │   User Query → Pattern Detection (LLM or keywords)                  │
    │                        │                                             │
    │         ┌──────────────┼──────────────┬──────────────┐              │
    │         ▼              ▼              ▼              │              │
    │     HANDOFF       SEQUENTIAL      CONCURRENT        │              │
    │  (tool calls)      (A→B→C)        (A|B|C)           │              │
    │                                                      │              │
    │         ┌──────────────┼──────────────┬──────────────┤              │
    │         ▼              ▼              ▼              ▼              │
    │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
    │   │ Search   │  │ Contract │  │ Compliance│  │ Labor    │          │
    │   │ Agent    │  │ Agent    │  │ Agent     │  │ Agent    │          │
    │   └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
    │                                                                      │
    │   Custom message history with Redis persistence                      │
    └─────────────────────────────────────────────────────────────────────┘

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework ChatAgent + AgentThread pattern
- Now uses Qwen-Agent's Assistant class with custom message history
- Delegation is handled via registered tools instead of .as_tool()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator, TYPE_CHECKING

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

if TYPE_CHECKING:
    from qwen_agent.agents import Assistant

from app.agents.config import agent_config
from app.agents.model_client import get_llm_config

# Timeout for LLM inference (seconds)
# vLLM can take 30-60s for complex analysis with tool calling
LLM_TIMEOUT_SECONDS = 120.0
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
    create_search_agent_with_sharing,
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
    should_use_rlm,
    estimate_tokens,
)
from app.agents.rlm_orchestrator import rlm_orchestrator, RLMResult
from app.services.rag.prompt_loader import get_agent_system_message, get_context_root

logger = logging.getLogger(__name__)

# Redis configuration
EMMA_THREAD_KEY_PREFIX = "emma:coordinator:thread:"
EMMA_THREAD_TTL_SECONDS = 3600  # 1 hour (longer for better context retention)


def clean_thinking_tags(text: str) -> str:
    """
    Remove Qwen3 thinking tags from LLM output.

    Qwen3 uses <think>...</think> tags for chain-of-thought reasoning
    when enable_thinking=True. This function removes these tags and
    returns only the final answer.

    Note: When using vLLM with chat_template_kwargs: {enable_thinking: false},
    the model should not produce thinking tags. This function is a fallback
    for cases where thinking mode is enabled or for compatibility.

    Args:
        text: Raw LLM output that may contain thinking tags

    Returns:
        Cleaned text with thinking content removed
    """
    import re

    # Remove content inside <think>...</think> tags using regex
    # This handles multiline content within thinking tags
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

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

    Uses Qwen-Agent framework with custom orchestration:
    - Assistant as the main coordinator agent
    - Custom delegation tools to route to specialist agents
    - Manual message history management with Redis persistence
    - Multiple orchestration patterns (handoff, sequential, concurrent)

    This implementation manages conversation state through Redis-persisted
    message history, allowing Emma to maintain context across turns.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        Initialize EmmaCoordinator.

        Args:
            redis_client: Redis client for message history persistence (creates one if None)
        """
        self._redis = redis_client
        self._llm_cfg: Optional[dict] = None
        self._emma: Optional["Assistant"] = None
        self._subagents: Dict[str, "Assistant"] = {}
        self._initialized = False

        # Orchestration patterns
        self._sequential = None
        self._concurrent = None

    async def initialize(self) -> None:
        """Initialize Emma and all subagents."""
        if self._initialized:
            return

        # Get Qwen-Agent LLM configuration (uses vLLM backend)
        self._llm_cfg = get_llm_config()
        logger.info(f"✅ LLM config created for {self._llm_cfg.get('model', 'unknown')}")

        # Initialize Redis using shared connection pool (not individual connection)
        # This prevents connection exhaustion under load
        if self._redis is None:
            pool = get_redis_pool()
            self._redis = redis.Redis(connection_pool=pool)

        # Create all specialist subagents
        self._create_subagents()

        # Create Emma coordinator with delegation tools
        self._create_emma_coordinator()

        # Initialize orchestration patterns
        self._sequential = get_sequential_orchestration()
        self._concurrent = get_concurrent_orchestration()

        # Set aggregator for concurrent (uses summarizer agent)
        if "summarizer_agent" in self._subagents:
            self._concurrent.set_aggregator(self._subagents["summarizer_agent"])

        self._initialized = True
        logger.info(f"✅ EmmaCoordinator initialized with {len(self._subagents)} subagents + orchestration patterns")

    def _create_subagents(self) -> None:
        """Create all specialist subagents using Qwen-Agent Assistant."""
        self._subagents = {
            "search_agent": create_search_agent_with_sharing(self._llm_cfg),
            "contract_agent": create_contract_agent(self._llm_cfg),
            "compliance_agent": create_compliance_agent(self._llm_cfg),
            "analyst_agent": create_analyst_agent(self._llm_cfg),
            "summarizer_agent": create_summarizer_agent(self._llm_cfg),
            "labor_agent": create_labor_agent(self._llm_cfg),
            "fiscal_agent": create_fiscal_agent(self._llm_cfg),
            "privacy_agent": create_privacy_agent(self._llm_cfg),
        }

        logger.info(f"Created {len(self._subagents)} specialist subagents")

    def _create_emma_coordinator(self) -> None:
        """
        Create Emma as the main coordinator agent using Qwen-Agent.

        In Qwen-Agent, we use function_list with registered tool names
        instead of .as_tool() pattern. The tools are registered globally
        via @register_tool decorator and can be referenced by name.
        """
        from qwen_agent.agents import Assistant

        # Build list of tool names Emma can use
        # IMPORTANT: Keep this list minimal to stay within vLLM context limits
        # Each tool adds ~400 tokens to context. With 8640 max tokens and
        # ~2000 system prompt, we can afford ~16 tools max. Keeping to 5-6 essential.
        # Specialized tools (sharing insights) are delegated to subagents.
        emma_tools = [
            # Core search (semantic covers keyword/hybrid cases)
            'nexus_semantic_search',
            # Core RAG - fetch and analyze documents
            'get_document_content',
            'analyze_document',
            # HITL clarification (essential for user interaction)
            'ask_user_clarification',
            'ask_confirmation',
        ]

        logger.info(f"Emma will use {len(emma_tools)} tools: {emma_tools}")

        # Load context root (global document management context based on ISO 15489)
        context_root = get_context_root()

        # Load Emma's agent-specific instructions from YAML or use default
        agent_instructions = get_agent_system_message(
            "EmmaCoordinator",
            DEFAULT_EMMA_INSTRUCTIONS
        )

        # Combine context root with agent-specific instructions
        # This ensures Emma always has the document management domain context
        if context_root:
            full_instructions = f"{context_root}\n\n{agent_instructions}"
            logger.info(f"Loaded context_root ({len(context_root)} chars) + agent instructions")
        else:
            full_instructions = agent_instructions
            logger.warning("No context_root found, using agent instructions only")

        # Add /no_think directive if thinking mode is disabled
        # This is the soft switch method for Qwen3 models to disable chain-of-thought
        if not agent_config.vllm_enable_thinking:
            full_instructions = f"/no_think\n\n{full_instructions}"
            logger.info("Added /no_think directive to disable Qwen3 thinking mode")

        # Create Emma coordinator using Qwen-Agent Assistant
        self._emma = Assistant(
            llm=self._llm_cfg,
            name="Emma",
            system_message=full_instructions,
            function_list=emma_tools,
        )

        logger.info(f"Created Emma coordinator (Qwen-Agent Assistant) with {len(emma_tools)} tools")

    def _get_agent_description(self, agent_name: str) -> str:
        """Get description for each subagent tool."""
        descriptions = {
            # SearchAgent: handles document search AND sharing queries (site guests, document shares)
            "search_agent": (
                "Busca documentos y consulta información de COMPARTICIÓN. "
                "OBLIGATORIO usar para: 'compartido', 'usuarios compartidos', 'con quién he compartido', "
                "'qué he compartido', 'invitados', 'guests', 'portal', 'acceso externo', "
                "'quién tiene acceso', 'estadísticas de compartir', 'documentos compartidos'. "
                "También para: 'busca', 'encuentra documentos'"
            ),
            "contract_agent": "Analiza contratos, cláusulas y obligaciones legales. Usa para: 'contrato', 'cláusula', 'términos'",
            "compliance_agent": "Verifica cumplimiento GDPR/RGPD y normativo. Usa para: 'gdpr', 'rgpd', 'cumplimiento'",
            # AnalystAgent: deep document analysis (NOT for sharing queries)
            "analyst_agent": (
                "Realiza análisis profundo de CONTENIDO de documentos específicos. "
                "Usa para: 'analiza este documento', 'evalúa el contenido', 'examina riesgos del documento'. "
                "NO usar para consultas sobre compartición o usuarios."
            ),
            "summarizer_agent": "Crea resúmenes ejecutivos. Usa para: 'resume', 'resumen', 'sintetiza', 'puntos clave'",
            "labor_agent": "Especialista en derecho laboral español. Usa para: 'laboral', 'despido', 'nómina', 'convenio'",
            "fiscal_agent": "Especialista en temas fiscales e impuestos. Usa para: 'impuesto', 'iva', 'irpf', 'fiscal'",
            "privacy_agent": "Especialista en protección de datos (LOPDGDD). Usa para: 'lopdgdd', 'protección de datos'",
        }
        return descriptions.get(agent_name, f"Specialist agent: {agent_name}")

    def _get_thread_key(self, tenant_id: str, session_id: str) -> str:
        """Get Redis key for message history storage."""
        return f"{EMMA_THREAD_KEY_PREFIX}{tenant_id}:{session_id}"

    async def _load_message_history(
        self,
        tenant_id: str,
        session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Load existing message history from Redis or return empty list.

        Message history format compatible with Qwen-Agent:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        messages, _ = await self._load_message_history_with_status(tenant_id, session_id)
        return messages

    async def _load_message_history_with_status(
        self,
        tenant_id: str,
        session_id: str
    ) -> tuple[List[Dict[str, Any]], bool]:
        """
        Load existing message history from Redis or return empty list.
        Returns (messages, is_new_session) tuple.

        is_new_session=True means this is the first message in the session,
        useful for injecting user context and Emma's introduction.
        """
        key = self._get_thread_key(tenant_id, session_id)

        try:
            serialized_json = await self._redis.get(key)

            if serialized_json:
                logger.info(f"📜 Loading existing message history: {session_id[:16]}...")
                messages = json.loads(serialized_json)
                return messages, False  # Existing session

        except Exception as e:
            logger.warning(f"⚠️ Failed to load message history from Redis: {e}")

        # Return empty list for new session
        logger.info(f"🆕 Creating new message history: {session_id[:16]}...")
        return [], True  # New session

    async def _save_message_history(
        self,
        messages: List[Dict[str, Any]],
        tenant_id: str,
        session_id: str
    ) -> None:
        """
        Save message history to Redis for persistence.

        Implements safeguards to prevent excessive memory usage:
        - Max 20 messages retained (10 conversation turns)
        - Max 50KB per message content
        - Max 500KB total history size
        """
        key = self._get_thread_key(tenant_id, session_id)

        # Safeguard: Limit message content size
        MAX_CONTENT_SIZE = 50000  # 50KB per message
        MAX_HISTORY_SIZE = 500000  # 500KB total
        MAX_MESSAGES = 20  # Keep last 20 messages (10 turns)

        # Truncate individual messages if too long
        truncated_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content', '')
                if isinstance(content, str) and len(content) > MAX_CONTENT_SIZE:
                    logger.warning(f"⚠️ Truncating large message ({len(content)} chars)")
                    msg = {**msg, 'content': content[:MAX_CONTENT_SIZE] + '... [truncated]'}
                truncated_messages.append(msg)
            else:
                truncated_messages.append(msg)

        # Keep only last N messages
        if len(truncated_messages) > MAX_MESSAGES:
            logger.info(f"📦 Pruning history from {len(truncated_messages)} to {MAX_MESSAGES} messages")
            truncated_messages = truncated_messages[-MAX_MESSAGES:]

        try:
            serialized_json = json.dumps(truncated_messages, default=str)

            # Final size check
            if len(serialized_json) > MAX_HISTORY_SIZE:
                logger.error(f"❌ History too large ({len(serialized_json)} bytes), clearing old messages")
                # Keep only the last 4 messages if still too large
                truncated_messages = truncated_messages[-4:]
                serialized_json = json.dumps(truncated_messages, default=str)

            await self._redis.setex(key, EMMA_THREAD_TTL_SECONDS, serialized_json)
            logger.debug(f"💾 Saved message history ({len(truncated_messages)} messages, {len(serialized_json)} bytes): {session_id[:16]}...")

        except Exception as e:
            logger.warning(f"⚠️ Failed to save message history to Redis: {e}")

    async def execute(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        user_context: Optional[Dict[str, Any]] = None,
        orchestration_hint: Optional[str] = None,
        deep_reasoning: bool = True
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
            user_role_ids: Optional list of role IDs for ACL filtering
            is_admin: Whether user is admin (bypasses ACL checks)
            user_context: Optional user context (name, preferences)
            orchestration_hint: Optional explicit pattern ("sequential", "concurrent", "handoff")

        Returns:
            EmmaCoordinatorResult with answer and orchestration metadata
        """
        start_time = time.perf_counter()

        if not self._initialized:
            await self.initialize()

        # Extract document_id from user_context if present
        focus_document_id = user_context.get("document_id") if user_context else None

        # Set execution context for @ai_function tools
        # This ensures tenant_id, ACL context, and document focus are available via contextvars,
        # eliminating dependency on LLM to extract them correctly
        set_execution_context(
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            session_id=session_id,
            document_id=focus_document_id
        )

        try:
            # Determine orchestration pattern
            if orchestration_hint:
                pattern = OrchestrationPattern(orchestration_hint.lower())
                logger.info(f"📋 Using explicit orchestration hint: {pattern.value}")
            else:
                # Check if RLM is needed based on document content size
                document_content = user_context.get("document_content", "") if user_context else ""
                context_tokens = estimate_tokens(document_content)

                if should_use_rlm(context_tokens):
                    pattern = OrchestrationPattern.RLM_LONG
                    logger.info(
                        f"🔄 RLM activated: {context_tokens} tokens > threshold, "
                        f"using recursive processing"
                    )
                else:
                    pattern = await detect_orchestration_pattern(
                        query,
                        use_llm=True,
                        vllm_base_url=agent_config.vllm_base_url,
                        vllm_model=agent_config.vllm_model
                    )
                    logger.info(f"🔍 Detected orchestration pattern: {pattern.value}")

            # Route to appropriate orchestration
            if pattern == OrchestrationPattern.RLM_LONG:
                return await self._execute_rlm(
                    query, tenant_id, session_id, user_context, start_time
                )

            elif pattern == OrchestrationPattern.SEQUENTIAL:
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
            tuple: (message_history, full_query, is_new_session)
        """
        # Load or create message history (this is where context lives!)
        message_history, is_new_session = await self._load_message_history_with_status(tenant_id, session_id)

        # Build context-aware query with user info for new sessions
        full_query = self._build_query_with_context(
            query, tenant_id, user_context, is_new_session=is_new_session
        )

        logger.info(f"🤖 Emma processing: {query[:50]}...")
        logger.info(f"📝 Full query: {full_query[:200]}...")

        return message_history, full_query, is_new_session

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
        message_history, full_query, _ = await self._prepare_execution(
            query, tenant_id, session_id, user_context
        )

        # Add current query to message history
        messages = message_history + [{'role': 'user', 'content': full_query}]

        # Execute with Emma using Qwen-Agent's run() generator pattern
        all_responses = []
        tools_called = []

        try:
            for response_messages in self._emma.run(messages):
                all_responses.extend(response_messages)
                # Track tool calls
                for msg in response_messages:
                    if isinstance(msg, dict) and msg.get('function_call'):
                        tools_called.append(msg['function_call'].get('name', 'unknown'))
        except Exception as e:
            logger.error(f"Error running Emma: {e}")
            raise

        # Extract final answer from responses
        answer = ""
        for msg in all_responses:
            if isinstance(msg, dict):
                content = msg.get('content', '')
                role = msg.get('role', '')
                if role == 'assistant' and content:
                    answer = content

        # Clean Qwen thinking tags if present
        answer = clean_thinking_tags(answer)

        # Build updated message history with assistant response
        updated_history = messages + [{'role': 'assistant', 'content': answer}]

        # Save updated message history
        await self._save_message_history(updated_history, tenant_id, session_id)

        execution_time = (time.perf_counter() - start_time) * 1000

        logger.info(f"📤 HANDOFF COMPLETE: tools={tools_called}, time={execution_time:.0f}ms")

        return EmmaCoordinatorResult(
            success=True,
            answer=answer,
            agents_delegated=[],  # In Qwen-Agent, we use tools directly, not subagent delegation
            tools_called=list(set(tools_called)),
            execution_time_ms=execution_time,
            thread_id=session_id,
            metadata={
                "framework": "qwen_agent",
                "pattern": "handoff",
                "context_maintained": True,
                "tenant_id": tenant_id,
                "message_count": len(updated_history)
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
                "framework": "qwen_agent",
                "pattern": "sequential",
                "pipeline": [getattr(a, 'name', str(a)) for a in agents],
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
                "framework": "qwen_agent",
                "pattern": "concurrent",
                "parallel_agents": [getattr(a, 'name', str(a)) for a in agents],
                "aggregated": result.metadata.get("aggregated", False),
                "successful_agents": result.metadata.get("successful_agents", 0),
                "tenant_id": tenant_id
            }
        )

    async def _execute_rlm(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]],
        start_time: float
    ) -> EmmaCoordinatorResult:
        """
        Execute using RLM (Recursive Language Model) pattern for long documents.

        RLM decomposes the query into sub-tasks, processes each section,
        and aggregates results - enabling processing of documents >50K tokens.

        Reference: arXiv:2512.24601 (RLM paper)
        """
        logger.info(f"🔄 RLM: Processing long context query")

        # Get document content from user_context
        document_content = ""
        if user_context:
            document_content = user_context.get("document_content", "")

        # If no document content, fall back to HANDOFF
        if not document_content:
            logger.warning("⚠️ RLM: No document content, falling back to HANDOFF")
            return await self._execute_handoff(
                query, tenant_id, session_id, user_context, start_time
            )

        context_tokens = estimate_tokens(document_content)
        logger.info(f"🔄 RLM: Context size: {context_tokens} tokens")

        try:
            # Initialize RLM orchestrator
            await rlm_orchestrator.initialize()

            # Process with RLM
            rlm_result: RLMResult = await rlm_orchestrator.process(
                query=query,
                context=document_content,
                tenant_id=tenant_id,
                metadata={
                    "session_id": session_id,
                    "user_context": user_context,
                }
            )

            execution_time = (time.perf_counter() - start_time) * 1000

            return EmmaCoordinatorResult(
                success=rlm_result.success,
                answer=rlm_result.final_answer,
                agents_delegated=[],  # RLM doesn't use sub-agents
                tools_called=[],
                execution_time_ms=execution_time,
                thread_id=session_id,
                metadata={
                    "framework": "rlm_recursive",
                    "pattern": "rlm_long",
                    "original_context_tokens": rlm_result.original_context_tokens,
                    "total_tokens_processed": rlm_result.total_tokens_processed,
                    "recursion_depth": rlm_result.recursion_depth_reached,
                    "sub_tasks_count": len(rlm_result.sub_tasks),
                    "rlm_execution_time_ms": rlm_result.execution_time_ms,
                    "tenant_id": tenant_id
                }
            )

        except Exception as e:
            logger.error(f"❌ RLM execution failed: {e}")
            # Fallback to HANDOFF on error
            return await self._execute_handoff(
                query, tenant_id, session_id, user_context, start_time
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
        user_role_ids: Optional[List[str]] = None,
        is_admin: bool = False,
        user_context: Optional[Dict[str, Any]] = None,
        deep_reasoning: bool = True
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

        # Extract document_id from user_context if present
        focus_document_id = user_context.get("document_id") if user_context else None

        # Set execution context for @ai_function tools (includes ACL context and document focus)
        set_execution_context(
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            session_id=session_id,
            document_id=focus_document_id
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
            await asyncio.sleep(0)  # Force flush

            # Use shared preparation logic
            message_history, full_query, _ = await self._prepare_execution(
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
            await asyncio.sleep(0)  # Force flush

            yield {
                "event": "start",
                "data": {
                    "message": "Generando respuesta...",
                    "agent": "Emma"
                }
            }
            await asyncio.sleep(0)  # Force flush

            # Apply thinking mode soft switch based on deep_reasoning flag
            # /think enables extended reasoning, /no_think disables it
            if deep_reasoning:
                reasoning_query = f"/think\n{full_query}"
                logger.info("🧠 Deep reasoning ENABLED (/think)")
            else:
                reasoning_query = f"/no_think\n{full_query}"
                logger.info("⚡ Fast mode ENABLED (/no_think)")

            # Build messages for Qwen-Agent
            messages = message_history + [{'role': 'user', 'content': reasoning_query}]

            # Process Emma's response using Qwen-Agent's run() generator
            # IMPORTANT: Qwen-Agent's run() is SYNCHRONOUS and blocks the event loop.
            # We must run it in a thread executor to allow async SSE streaming.
            import queue
            import threading

            tools_used = []
            first_token_emitted = False
            previous_clean_content = ""
            final_answer = ""

            # Thread-safe queue for passing events from sync generator to async generator
            event_queue: queue.Queue = queue.Queue()

            def run_emma_sync():
                """Run Emma's sync generator in a separate thread."""
                nonlocal previous_clean_content, final_answer
                logger.info("🧵 Emma sync thread STARTED")
                batch_count = 0
                try:
                    for response_batch in self._emma.run(messages):
                        batch_count += 1
                        logger.info(f"🧵 Thread received batch #{batch_count}: {len(response_batch)} messages")
                        for msg in response_batch:
                            if not isinstance(msg, dict):
                                continue
                            logger.info(f"🧵 Thread queueing message: role={msg.get('role')}, has_content={bool(msg.get('content'))}")
                            event_queue.put(("message", msg))
                    logger.info(f"🧵 Thread completed after {batch_count} batches, sending done")
                    event_queue.put(("done", None))
                except Exception as e:
                    logger.error(f"❌ Emma sync thread error: {e}")
                    import traceback
                    traceback.print_exc()
                    event_queue.put(("error", str(e)))

            # Start Emma in a background thread
            emma_thread = threading.Thread(target=run_emma_sync, daemon=True)
            emma_thread.start()

            # Tool descriptions for UI
            tool_descriptions = {
                "nexus_semantic_search": "Buscando documentos...",
                "nexus_hybrid_search": "Buscando documentos...",
                "nexus_keyword_search": "Buscando documentos...",
                "get_document_content": "Obteniendo documento...",
                "analyze_document": "Analizando documento...",
                "query_recent_shares": "Consultando comparticiones...",
                "query_site_guests": "Consultando invitados...",
                "query_sharing_statistics": "Consultando estadísticas...",
                "query_guest_documents": "Consultando documentos de invitado...",
                "query_guest_activity": "Consultando actividad de invitado...",
                "query_sharing_overview": "Obteniendo resumen de comparticiones...",
                "ask_user_clarification": "Necesito tu ayuda para aclarar algo...",
                "ask_confirmation": "Esperando confirmación...",
                "suggest_follow_up": "Preparando sugerencias...",
            }

            # Process events from the queue asynchronously
            logger.info("🔄 Starting async event loop for queue processing")
            loop_iterations = 0
            last_heartbeat = time.time()
            HEARTBEAT_INTERVAL = 5.0  # Send progress event every 5 seconds
            had_error = False  # Track if an error occurred to avoid sending complete after error

            while True:
                loop_iterations += 1
                # Non-blocking poll with small sleep to yield to event loop
                try:
                    event_type, data = event_queue.get(timeout=0.1)
                    logger.info(f"🔄 Queue got event: {event_type}")
                except queue.Empty:
                    # Send heartbeat to keep connection alive during LLM processing
                    current_time = time.time()
                    if current_time - last_heartbeat >= HEARTBEAT_INTERVAL:
                        last_heartbeat = current_time
                        elapsed_ms = int((current_time - start_time) * 1000)
                        logger.info(f"💓 Sending heartbeat (elapsed: {elapsed_ms}ms)")
                        yield {
                            "event": "progress",
                            "data": {
                                "message": "Emma está procesando...",
                                "stage": "thinking",
                                "elapsed_ms": elapsed_ms,
                                "agent": "Emma"
                            }
                        }
                        await asyncio.sleep(0)  # Force flush heartbeat
                    # Allow other async tasks to run
                    await asyncio.sleep(0.01)
                    continue

                if event_type == "done":
                    logger.info("🔄 Received DONE signal from thread")
                    break
                elif event_type == "error":
                    had_error = True
                    yield {
                        "event": "error",
                        "data": {"error": data, "message": f"Error: {data}"}
                    }
                    break
                elif event_type == "message":
                    msg = data

                    # Track tool calls (delegations)
                    if msg.get('function_call'):
                        tool_name = msg['function_call'].get('name', 'unknown')
                        logger.info(f"🔧 STREAM TOOL CALL: {tool_name}")
                        tools_used.append(tool_name)
                        delegation_message = tool_descriptions.get(tool_name, f"Consultando {tool_name}...")

                        elapsed_ms = int((time.time() - start_time) * 1000)
                        yield {
                            "event": "delegation",
                            "data": {
                                "agent": tool_name,
                                "message": delegation_message,
                                "elapsed_ms": elapsed_ms
                            }
                        }
                        await asyncio.sleep(0)  # Force flush delegation
                        continue

                    # Process assistant content
                    raw_content = msg.get('content', '')
                    role = msg.get('role', '')

                    if role == 'assistant' and raw_content:
                        # Check if we're still inside a thinking block
                        # Don't emit tokens until thinking is complete
                        is_thinking = '<think>' in raw_content and '</think>' not in raw_content

                        if is_thinking:
                            # Still thinking - don't emit tokens yet
                            continue

                        clean_content = clean_thinking_tags(raw_content)

                        # Calculate delta (what's new since last batch)
                        if len(clean_content) > len(previous_clean_content):
                            if clean_content.startswith(previous_clean_content):
                                delta = clean_content[len(previous_clean_content):]
                            else:
                                delta = clean_content

                            if delta.strip():
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
                                    await asyncio.sleep(0)  # Force flush first_token

                                yield {
                                    "event": "token",
                                    "data": {
                                        "text": delta,
                                        "agent": "Emma"
                                    }
                                }
                                await asyncio.sleep(0)  # Force flush token

                            previous_clean_content = clean_content

                        final_answer = clean_content

            # Wait for thread to finish (with timeout)
            emma_thread.join(timeout=5.0)

            # Skip completion events if there was an error
            if had_error:
                logger.info("🚫 Skipping completion - error already sent")
                return

            # Build updated message history with assistant response
            updated_history = messages + [{'role': 'assistant', 'content': final_answer}]

            # Save updated message history
            await self._save_message_history(updated_history, tenant_id, session_id)

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            logger.info(f"🎬 STREAM COMPLETE: tools_used={tools_used}, time={execution_time_ms}ms")
            logger.info(f"🎬 STREAM ANSWER preview: {final_answer[:200] if final_answer else 'EMPTY'}...")

            # Check if the answer contains a clarification request (Human-in-the-Loop)
            # This happens when Emma called ask_user_clarification, ask_confirmation, etc.
            from app.agents.tools.clarification_tools import parse_clarification_response
            clarification_data = parse_clarification_response(final_answer.strip())

            if clarification_data:
                # This is a clarification request - emit special event
                request_type = clarification_data.get("_type", "clarification_request")
                event_name = {
                    "clarification_request": "clarification_needed",
                    "confirmation_request": "confirmation_needed",
                    "follow_up_suggestions": "suggestions_available",
                }.get(request_type, "clarification_needed")

                logger.info(f"🤔 HITL: Emitting {event_name} event with options: {len(clarification_data.get('options', []))} options")

                yield {
                    "event": event_name,
                    "data": {
                        "question": clarification_data.get("question", ""),
                        "header": clarification_data.get("header", "Opción"),
                        "options": clarification_data.get("options", []),
                        "multi_select": clarification_data.get("multi_select", False),
                        "severity": clarification_data.get("severity"),
                        "suggestions": clarification_data.get("suggestions"),
                        "context": clarification_data.get("context"),
                        "session_id": session_id,
                        "execution_time_ms": execution_time_ms,
                        # Include raw data for frontend flexibility
                        "_raw": clarification_data,
                    }
                }
                await asyncio.sleep(0)  # Force flush
            else:
                # Normal completion - send complete event with the accumulated answer
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
                await asyncio.sleep(0)  # Force flush

        except Exception as e:
            logger.error(f"❌ Emma stream failed: {e}")
            yield {
                "event": "error",
                "data": {
                    "error": str(e),
                    "message": f"Error: {str(e)}"
                }
            }
            await asyncio.sleep(0)  # Force flush

        finally:
            # Always clear execution context to prevent leaking to other requests
            clear_execution_context()

    async def clear_context(self, tenant_id: str, session_id: str) -> bool:
        """Clear conversation context for a session."""
        key = self._get_thread_key(tenant_id, session_id)
        try:
            await self._redis.delete(key)
            logger.info(f"🗑️ Cleared Emma message history: {session_id[:16]}...")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear message history: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get coordinator status."""
        return {
            "initialized": self._initialized,
            "subagents": list(self._subagents.keys()) if self._subagents else [],
            "subagent_count": len(self._subagents) if self._subagents else 0,
            "framework": "qwen_agent",
            "context_management": "message_history",
            "persistence": "Redis",
            "delegation_method": "function_list",
            "orchestration_patterns": {
                "handoff": True,  # Default: LLM decides via tools
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
