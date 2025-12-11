"""
Emma GroupChat Workflow - Multi-Agent Orchestration with GroupChatBuilder.

This module implements Emma AI using the Microsoft Agent Framework's GroupChatBuilder
for intelligent routing between specialized agents using a manager-directed approach.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      EmmaGroupChatWorkflow                       │
    │                                                                  │
    │   User Query                                                     │
    │       │                                                          │
    │       ▼                                                          │
    │   ┌────────────────────────────────────────┐                    │
    │   │          Manager (LLM-based)           │                    │
    │   │   • Analyzes user intent               │                    │
    │   │   • Selects which specialist speaks    │                    │
    │   │   • Uses classifier logic              │                    │
    │   └────────────────────┬───────────────────┘                    │
    │                        │ select_speaker                         │
    │   ┌────────────────────┼────────────────────────┐              │
    │   │                    │                        │              │
    │   ▼                    ▼                        ▼              │
    │ ┌─────────┐     ┌───────────┐          ┌────────────┐          │
    │ │ Search  │     │ Contract  │   ...    │ Compliance │          │
    │ │ Agent   │     │  Agent    │          │   Agent    │          │
    │ │(search) │     │(contracts)│          │(GDPR/RGPD) │          │
    │ └────┬────┘     └─────┬─────┘          └──────┬─────┘          │
    │      │                │                       │                 │
    │      └────────────────┴───────────────────────┘                 │
    │                        │                                        │
    │                        ▼                                        │
    │               Final Response to User                            │
    └─────────────────────────────────────────────────────────────────┘

Key Features:
- Manager-directed speaker selection (LLM or function-based)
- Round-based execution without user interaction needed
- Full conversation history preserved across rounds
- AgentThread integration for session persistence
- Redis storage for cross-request context

Usage:
    from app.agents.handoff_workflow import get_emma_handoff_workflow

    workflow = await get_emma_handoff_workflow()
    result = await workflow.execute(
        query="Analiza este contrato por riesgos legales",
        tenant_id="tenant-123",
        session_id="session-456"
    )
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncIterator

import httpx
import redis.asyncio as redis

from agent_framework import GroupChatBuilder, ChatAgent
from agent_framework.openai import OpenAIChatClient

from app.agents.config import agent_config
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
from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)


# Redis key prefix for workflow threads
WORKFLOW_THREAD_KEY_PREFIX = "emma:groupchat:thread:"
WORKFLOW_THREAD_TTL_SECONDS = 1800  # 30 minutes


# Query classification patterns for deterministic speaker selection
SEARCH_PATTERNS = [
    r'\bbusca\b', r'\bencuentra\b', r'\bmuéstrame\b', r'\blocaliza\b',
    r'\bdame los\b', r'\bqué documentos\b', r'\bcuáles son\b',
    r'\bbuscame\b', r'\bencontrar\b', r'\bcorreos?\b', r'\bemails?\b'
]

CONTRACT_PATTERNS = [
    r'\bcontrato(s)?\b', r'\bcláusula(s)?\b', r'\btérmino(s)?\b',
    r'\bcondicion(es)?\b', r'\bpenalidad(es)?\b', r'\brescisión\b',
    r'\bvencimiento(s)?\b', r'\bfirma(s)?\b', r'\bpartes?\b'
]

COMPLIANCE_PATTERNS = [
    r'\bgdpr\b', r'\brgpd\b', r'\bcumplimiento\b', r'\bprivacidad\b',
    r'\bdatos personales\b', r'\bconsentimiento\b', r'\bregulación\b'
]

LABOR_PATTERNS = [
    r'\bdespido\b', r'\bnómina\b', r'\bconvenio\b', r'\blaboral(es)?\b',
    r'\btrabajador(es)?\b', r'\bempleado(s)?\b', r'\bcontratación\b', r'\bvacaciones\b',
    r'\bestatuto\b', r'\bsindic', r'\bderechos\s+\w+\s+laborales\b',
    r'\bderechos\s+laborales\b', r'\bderecho\s+laboral\b'
]

FISCAL_PATTERNS = [
    r'\bimpuesto(s)?\b', r'\biva\b', r'\birpf\b', r'\bfiscal(es)?\b',
    r'\bdeclaración(es)?\b', r'\btributari', r'\bhacienda\b', r'\bfactura(s)?\b'
]

PRIVACY_PATTERNS = [
    r'\blopdgdd\b', r'\bprotección de datos\b', r'\bconsentimiento\b',
    r'\bderechos arco\b', r'\bdelegado de protección\b', r'\bdpo\b'
]

SUMMARIZE_PATTERNS = [
    r'\bresumen\b', r'\bresume\b', r'\bsintetiza\b', r'\bbrevement\b',
    r'\bpuntos clave\b', r'\bextrae los puntos\b'
]

ANALYZE_PATTERNS = [
    r'\banaliza\b', r'\banálisis\b', r'\brevisar?\b', r'\bevalua\b',
    r'\bexamina\b', r'\bidentifica\b', r'\briesgo\b'
]


def classify_query_for_agent(query: str) -> str:
    """
    Classify a query to determine the best agent.

    Uses regex pattern matching for fast, deterministic routing.
    Priority order: Search action words first, then specific domain patterns.

    Args:
        query: User's query text

    Returns:
        Agent name to use
    """
    query_lower = query.lower()

    # FIRST: Check for explicit search action words (highest priority)
    # This ensures "busca contratos" goes to SearchAgent, not ContractAgent
    search_action_words = [r'\bbusca\b', r'\bbuscame\b', r'\bencuentra\b', r'\bmuéstrame\b', r'\blocaliza\b']
    for pattern in search_action_words:
        if re.search(pattern, query_lower):
            return "SearchAgent"

    # THEN: Check specialized legal domains (high specificity)
    for pattern in LABOR_PATTERNS:
        if re.search(pattern, query_lower):
            return "LaborAgent"

    for pattern in FISCAL_PATTERNS:
        if re.search(pattern, query_lower):
            return "FiscalAgent"

    for pattern in PRIVACY_PATTERNS:
        if re.search(pattern, query_lower):
            return "PrivacyAgent"

    for pattern in COMPLIANCE_PATTERNS:
        if re.search(pattern, query_lower):
            return "ComplianceAgent"

    # Document type patterns (medium specificity)
    for pattern in CONTRACT_PATTERNS:
        if re.search(pattern, query_lower):
            return "ContractAgent"

    for pattern in SUMMARIZE_PATTERNS:
        if re.search(pattern, query_lower):
            return "SummarizerAgent"

    for pattern in ANALYZE_PATTERNS:
        if re.search(pattern, query_lower):
            return "AnalystAgent"

    # Other search patterns (low priority)
    for pattern in SEARCH_PATTERNS:
        if re.search(pattern, query_lower):
            return "SearchAgent"

    # Default to SearchAgent if no pattern matches
    return "SearchAgent"


async def classify_agent_with_llm(query: str) -> str:
    """
    Use LLM to classify which specialized agent should handle the query.

    This provides more robust classification than regex patterns,
    handling paraphrasing, synonyms, and complex queries naturally.

    Args:
        query: User's query text

    Returns:
        Agent name: SearchAgent, ContractAgent, LaborAgent, FiscalAgent,
                   ComplianceAgent, PrivacyAgent, SummarizerAgent, AnalystAgent
    """
    try:
        # System message for classification - very strict to avoid thinking tags
        system_msg = """Clasificador de consultas. Responde ÚNICAMENTE con una palabra: el nombre del agente.
Sin explicaciones. Sin etiquetas. Sin pensamientos. Solo el nombre del agente."""

        # Classification prompt with /no_think suffix to disable Qwen3 thinking mode
        classification_prompt = """AGENTES:
- SearchAgent: buscar documentos, archivos, correos ("busca", "encuentra")
- ContractAgent: contratos, cláusulas, términos
- LaborAgent: laboral, despido, nómina, convenio, trabajador
- FiscalAgent: impuestos, IVA, IRPF, facturas
- ComplianceAgent: cumplimiento, auditoría
- PrivacyAgent: RGPD, LOPDGDD, datos personales
- SummarizerAgent: resumen, resume, sintetiza, puntos clave
- AnalystAgent: analiza, evalúa, riesgos, examina

REGLAS:
1. "busca" o "encuentra" → SearchAgent
2. "resume" o "resumen" → SummarizerAgent
3. "analiza" o "evalúa" → AnalystAgent
4. Dominio legal específico → agente del dominio

Consulta: {query}

Responde SOLO con el nombre del agente. /no_think"""

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{agent_config.vllm_base_url}/chat/completions",
                json={
                    "model": agent_config.vllm_model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": classification_prompt.format(query=query)}
                    ],
                    "max_tokens": 50,
                    "temperature": 0.0
                }
            )

            if response.status_code == 200:
                data = response.json()
                raw_response = data["choices"][0]["message"]["content"].strip()

                # Handle Qwen3 thinking tags
                # Case 1: Complete thinking (has both tags)
                if "</think>" in raw_response:
                    raw_response = raw_response.split("</think>")[-1].strip()
                # Case 2: Incomplete thinking (truncated by max_tokens) - use regex fallback
                elif "<think>" in raw_response:
                    logger.debug(f"🤔 LLM started thinking but was truncated, using regex fallback")
                    return classify_query_for_agent(query)

                # Normalize response - extract agent name
                agent_text = raw_response.upper()

                valid_agents = [
                    "SEARCHAGENT", "CONTRACTAGENT", "LABORAGENT", "FISCALAGENT",
                    "COMPLIANCEAGENT", "PRIVACYAGENT", "SUMMARIZERAGENT", "ANALYSTAGENT"
                ]

                for agent in valid_agents:
                    if agent in agent_text:
                        # Convert back to proper case: "SEARCHAGENT" → "SearchAgent"
                        base_name = agent.replace("AGENT", "")  # "SEARCH"
                        agent_name = base_name.capitalize() + "Agent"  # "SearchAgent"
                        logger.info(f"🤖 LLM classified agent: {agent_name} for '{query[:40]}...'")
                        return agent_name

                # If no valid agent found in response, use regex fallback
                logger.warning(f"⚠️ LLM returned invalid agent '{raw_response}', using regex fallback")
                return classify_query_for_agent(query)
            else:
                logger.warning(f"⚠️ vLLM agent classification failed: {response.status_code}")
                return classify_query_for_agent(query)

    except Exception as e:
        logger.warning(f"⚠️ Agent classification failed: {e}, using regex fallback")
        return classify_query_for_agent(query)


def _extract_task_text(task: Any) -> str:
    """Extract text from task, which can be a string or ChatMessage."""
    if isinstance(task, str):
        return task
    # ChatMessage has 'text' or 'content' attribute
    if hasattr(task, 'text') and task.text:
        return task.text
    if hasattr(task, 'content') and task.content:
        return task.content
    # Fallback to string representation
    return str(task)


def create_speaker_selector():
    """
    Create the speaker selection function for GroupChat.

    This function is called by GroupChatBuilder to determine
    which agent speaks next based on the current state.
    """
    def select_speaker(state: Dict[str, Any]) -> Optional[str]:
        """
        Select the next speaker based on conversation state.

        Args:
            state: GroupChatStateSnapshot with:
                - task: The initial task/query (ChatMessage or str)
                - participants: List of participant names
                - conversation: Current conversation messages
                - history: Full history including metadata
                - round_index: Current round (0-indexed)

        Returns:
            Agent name to speak next, or None to terminate
        """
        round_idx = state.get("round_index", 0)
        task_raw = state.get("task", "")
        history = state.get("history", [])

        # Extract text from task (handles both str and ChatMessage)
        task_text = _extract_task_text(task_raw)

        # Round 0: Classify and route to appropriate agent
        if round_idx == 0:
            agent = classify_query_for_agent(task_text)
            logger.info(f"🎯 Query classified → {agent}")
            return agent

        # Round 1+: Check if we have a response, terminate
        if len(history) >= 1:
            # We have a response, terminate
            return None

        # Safety limit
        if round_idx >= 3:
            return None

        # Continue with the same agent
        if history:
            last_speaker = getattr(history[-1], 'speaker', None)
            return last_speaker

        return None

    return select_speaker


@dataclass
class HandoffWorkflowResult:
    """Result from EmmaHandoffWorkflow execution."""
    success: bool
    answer: str
    agents_used: List[str]
    handoffs: List[Dict[str, str]]  # [{from: "coordinator", to: "search_agent"}, ...]
    execution_time_ms: float
    thread_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmmaHandoffWorkflow:
    """
    Emma GroupChat Workflow using Microsoft Agent Framework's GroupChatBuilder.

    This workflow implements intelligent routing between specialized agents:
    - A speaker selector function classifies queries and routes to agents
    - The selected agent processes and returns result
    - Single-shot execution (no user interaction between rounds)

    Architecture uses multiple specialized ChatAgents with deterministic routing.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None
    ):
        """
        Initialize EmmaHandoffWorkflow.

        Args:
            redis_client: Redis client for thread persistence
        """
        self._redis = redis_client
        self._client: Optional[OpenAIChatClient] = None
        self._workflow = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the workflow, client, and Redis connection."""
        if self._initialized:
            return

        # Create OpenAI client pointing to vLLM
        self._client = OpenAIChatClient(
            api_key="dummy",  # vLLM doesn't need a real key
            base_url=agent_config.vllm_base_url,
            model_id=agent_config.vllm_model
        )

        # Initialize Redis if not provided
        if self._redis is None:
            self._redis = redis.Redis(
                host=agent_config.redis_host,
                port=agent_config.redis_port,
                db=agent_config.redis_db,
                decode_responses=True
            )

        self._initialized = True
        logger.info("✅ EmmaHandoffWorkflow (GroupChat) initialized")

    def _create_specialists(self) -> Dict[str, ChatAgent]:
        """
        Create all specialist agents as a name-to-agent mapping.

        Returns:
            Dict mapping agent names to ChatAgent instances
        """
        specialists = {}

        # Core specialists
        specialists["SearchAgent"] = create_search_agent(self._client)
        specialists["ContractAgent"] = create_contract_agent(self._client)
        specialists["ComplianceAgent"] = create_compliance_agent(self._client)
        specialists["AnalystAgent"] = create_analyst_agent(self._client)
        specialists["SummarizerAgent"] = create_summarizer_agent(self._client)

        # Spanish legal domain specialists
        specialists["LaborAgent"] = create_labor_agent(self._client)
        specialists["FiscalAgent"] = create_fiscal_agent(self._client)
        specialists["PrivacyAgent"] = create_privacy_agent(self._client)

        return specialists

    def _build_workflow(self, tenant_id: str) -> Any:
        """
        Build the GroupChat workflow with specialized agents.

        Args:
            tenant_id: Tenant identifier (for potential customization)

        Returns:
            Configured Workflow from GroupChatBuilder
        """
        # Create specialists
        specialists = self._create_specialists()

        # Build workflow using GroupChatBuilder with function-based speaker selection
        workflow = (
            GroupChatBuilder()
            .participants(specialists)  # Dict of name -> agent
            .set_select_speakers_func(
                create_speaker_selector(),
                display_name="EmmaRouter"
            )
            .with_max_rounds(2)  # Route once, respond once
            .with_termination_condition(
                # Terminate after first non-empty response
                lambda msgs: len(msgs) >= 1 and any(
                    hasattr(m, 'content') and m.content
                    for m in msgs
                )
            )
            .build()
        )

        return workflow

    def _get_thread_key(self, tenant_id: str, session_id: str) -> str:
        """Get Redis key for thread storage."""
        return f"{WORKFLOW_THREAD_KEY_PREFIX}{tenant_id}:{session_id}"

    async def _load_conversation_history(
        self,
        tenant_id: str,
        session_id: str
    ) -> List[Dict[str, str]]:
        """
        Load conversation history from Redis.

        For GroupChat workflows, we store conversation as a simple list of
        {role: "user"|"assistant", content: str} messages rather than AgentThread.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            List of conversation messages
        """
        key = self._get_thread_key(tenant_id, session_id)

        try:
            history_json = await self._redis.get(key)

            if history_json:
                logger.info(f"📜 Loading conversation history: {session_id[:16]}...")
                return json.loads(history_json)

        except Exception as e:
            logger.warning(f"⚠️ Failed to load conversation history: {e}")

        return []

    async def _save_conversation_history(
        self,
        tenant_id: str,
        session_id: str,
        history: List[Dict[str, str]]
    ) -> None:
        """
        Save conversation history to Redis.

        Keeps only the last 10 exchanges to prevent context from growing too large.

        Args:
            tenant_id: Tenant identifier
            session_id: Session identifier
            history: List of conversation messages
        """
        key = self._get_thread_key(tenant_id, session_id)

        try:
            # Keep only last 10 exchanges (20 messages)
            trimmed_history = history[-20:]
            history_json = json.dumps(trimmed_history, ensure_ascii=False)
            await self._redis.setex(key, WORKFLOW_THREAD_TTL_SECONDS, history_json)
            logger.debug(f"💾 Saved conversation history: {session_id[:16]}...")

        except Exception as e:
            logger.warning(f"⚠️ Failed to save conversation history: {e}")

    def _format_history_context(self, history: List[Dict[str, str]]) -> str:
        """
        Format conversation history as context for the query.

        Args:
            history: List of conversation messages

        Returns:
            Formatted context string
        """
        if not history:
            return ""

        # Take last 4 messages for immediate context
        recent = history[-4:]
        lines = []
        for msg in recent:
            role = "Usuario" if msg.get("role") == "user" else "Emma"
            content = msg.get("content", "")[:200]  # Truncate long messages
            lines.append(f"[{role}]: {content}")

        return "CONTEXTO DE CONVERSACIÓN RECIENTE:\n" + "\n".join(lines) + "\n\n"

    async def execute(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> HandoffWorkflowResult:
        """
        Execute a query using the handoff workflow with conversation context.

        Args:
            query: User's question/task
            tenant_id: Tenant identifier
            session_id: Session identifier for context
            user_context: Optional user context (name, preferences)

        Returns:
            HandoffWorkflowResult with answer and metadata
        """
        start_time = time.perf_counter()

        if not self._initialized:
            await self.initialize()

        # Use query classifier to determine agent
        selected_agent = classify_query_for_agent(query)
        agents_used = [selected_agent]
        handoffs = [{"from": "EmmaRouter", "to": selected_agent}]

        try:
            # Build workflow for this execution
            workflow = self._build_workflow(tenant_id)

            # Load conversation history for context
            history = await self._load_conversation_history(tenant_id, session_id)
            history_context = self._format_history_context(history)

            # Prepare context-aware query with user name and history
            context_parts = []

            if user_context and user_context.get("name"):
                user_name = user_context["name"].split()[0]
                context_parts.append(f"[Usuario: {user_name}]")

            if history_context:
                context_parts.append(history_context)

            context_prefix = " ".join(context_parts)
            full_query = f"{context_prefix}{query}" if context_prefix else query

            # Run workflow
            logger.info(f"🔄 Running GroupChat workflow → {selected_agent}: {query[:50]}...")
            if history:
                logger.info(f"📜 Using conversation context ({len(history)} messages)")

            # GroupChatBuilder returns a Workflow that runs with run_stream
            # Collect all events and final response
            final_response = ""
            async for event in workflow.run_stream(full_query):
                # Track agents and responses from events
                if hasattr(event, 'data'):
                    # Track speaker changes
                    if hasattr(event.data, 'speaker') and event.data.speaker:
                        agent_name = event.data.speaker
                        if agent_name not in agents_used and agent_name != "EmmaRouter":
                            agents_used.append(agent_name)

                    # Extract text responses
                    if hasattr(event.data, 'text') and event.data.text:
                        final_response = event.data.text
                    elif hasattr(event.data, 'content') and event.data.content:
                        final_response = event.data.content

            # Handle Qwen3 thinking tags
            if "</think>" in final_response:
                final_response = final_response.split("</think>")[-1].strip()

            # Save updated conversation history
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": final_response[:500]})  # Truncate long responses
            await self._save_conversation_history(tenant_id, session_id, history)

            execution_time = (time.perf_counter() - start_time) * 1000

            return HandoffWorkflowResult(
                success=True,
                answer=final_response or "Consulta procesada",
                agents_used=agents_used,
                handoffs=handoffs,
                execution_time_ms=execution_time,
                thread_id=session_id,
                metadata={
                    "workflow_type": "groupchat",
                    "tenant_id": tenant_id,
                    "context_maintained": len(history) > 2,
                    "history_messages": len(history),
                    "router": "EmmaRouter"
                }
            )

        except Exception as e:
            logger.error(f"❌ EmmaHandoffWorkflow execution failed: {e}")
            import traceback
            traceback.print_exc()

            execution_time = (time.perf_counter() - start_time) * 1000

            return HandoffWorkflowResult(
                success=False,
                answer=f"Error procesando la consulta: {str(e)}",
                agents_used=agents_used,
                handoffs=handoffs,
                execution_time_ms=execution_time,
                thread_id=session_id,
                metadata={"error": str(e)}
            )

    async def execute_stream(
        self,
        query: str,
        tenant_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute a query with streaming events.

        Yields events as the workflow progresses through agents.

        Args:
            query: User's question/task
            tenant_id: Tenant identifier
            session_id: Session identifier
            user_context: Optional user context

        Yields:
            Dict events with type, agent, and content
        """
        if not self._initialized:
            await self.initialize()

        # Classify query to determine agent
        selected_agent = classify_query_for_agent(query)

        try:
            workflow = self._build_workflow(tenant_id)

            context_prefix = ""
            if user_context and user_context.get("name"):
                user_name = user_context["name"].split()[0]
                context_prefix = f"[Usuario: {user_name}] "

            full_query = f"{context_prefix}{query}"

            yield {
                "event": "workflow_started",
                "agent": "EmmaRouter",
                "message": f"Analizando tu consulta → {selected_agent}..."
            }

            yield {
                "event": "routing",
                "from_agent": "EmmaRouter",
                "to_agent": selected_agent,
                "message": f"Delegando a {selected_agent}..."
            }

            current_agent = selected_agent
            async for event in workflow.run_stream(full_query):
                if hasattr(event, 'data'):
                    # Track speaker changes
                    if hasattr(event.data, 'speaker') and event.data.speaker:
                        new_agent = event.data.speaker
                        if new_agent != current_agent and new_agent != "EmmaRouter":
                            yield {
                                "event": "speaker_change",
                                "from_agent": current_agent,
                                "to_agent": new_agent,
                                "message": f"Cambiando a {new_agent}..."
                            }
                            current_agent = new_agent

                    # Response chunk
                    text = None
                    if hasattr(event.data, 'text') and event.data.text:
                        text = event.data.text
                    elif hasattr(event.data, 'content') and event.data.content:
                        text = event.data.content

                    if text:
                        if "</think>" in text:
                            text = text.split("</think>")[-1].strip()

                        yield {
                            "event": "response_chunk",
                            "agent": current_agent,
                            "content": text
                        }

            yield {
                "event": "workflow_complete",
                "agent": current_agent,
                "message": "Consulta procesada"
            }

        except Exception as e:
            yield {
                "event": "error",
                "error": str(e),
                "message": f"Error: {str(e)}"
            }


# Singleton instance
_handoff_workflow: Optional[EmmaHandoffWorkflow] = None


def get_emma_handoff_workflow() -> EmmaHandoffWorkflow:
    """Get the global EmmaHandoffWorkflow singleton."""
    global _handoff_workflow
    if _handoff_workflow is None:
        _handoff_workflow = EmmaHandoffWorkflow()
    return _handoff_workflow


async def initialize_handoff_workflow() -> EmmaHandoffWorkflow:
    """Initialize and return the global EmmaHandoffWorkflow."""
    workflow = get_emma_handoff_workflow()
    await workflow.initialize()
    return workflow
