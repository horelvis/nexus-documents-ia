"""
Emma ReAct Agent — React Loop Node

The central node of the ReAct graph. Implements the Think-Act-Observe cycle
inspired by OpenManus ToolCallAgent:

    ┌─────────────────────────────────────────────────┐
    │  react_loop (max_steps=10, max_observe=8000)    │
    │                                                  │
    │  1. THINK: LLM with tools → decides action       │
    │  2. ACT: Execute selected tool(s) in parallel    │
    │  3. OBSERVE: Add result to messages              │
    │  4. DECIDE: tool_calls empty or Terminate?       │
    │     → Yes: exit to synthesize                    │
    │     → No: loop back to THINK                     │
    │                                                  │
    │  Stuck detection: 3 identical tool_calls → exit  │
    │  Safety: max_steps + timeout (60s)               │
    └─────────────────────────────────────────────────┘

Each iteration is ONE graph node execution. The graph's conditional edge
routes back to react_loop (continue) or forward to synthesize.
This avoids blocking the event loop with long internal loops and enables
SSE event emission between steps.
"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.core.config import settings
from app.core.langfuse_config import observe
from ..state import ReActState
from ..reasoning_tracker import StepType
from ..tools.registry import get_tool_registry
from ..quality_gate import assess_step0_no_tools, assess_terminate_quality
from ..context_compressor import compress_tool_observations, estimate_message_tokens, trim_messages_to_token_budget

logger = logging.getLogger(__name__)

async def _load_react_system_prompt() -> str:
    """Load the ReAct system prompt from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    cached = await client.get_prompt("emma_react_system")
    return cached.content


# ── Email action detection ───────────────────────────────────────────
_EMAIL_ADDR_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SEND_KEYWORDS = re.compile(
    r"\b(enviar?|mandar?|send|remitir?|enví[ao]|manda)\b", re.IGNORECASE
)


def _detect_email_action(query: str) -> Tuple[bool, str]:
    """Detect if the query is an email-sending action.

    Returns (is_email_action, email_address).
    Matches patterns like "enviar a user@domain.com" or "send to user@domain.com".
    """
    email_match = _EMAIL_ADDR_RE.search(query)
    if email_match and _SEND_KEYWORDS.search(query):
        return True, email_match.group(0)
    return False, ""


# ── Relationship query detection (→ graph_rag hint) ───────────────────
_RELATIONSHIP_PATTERNS = re.compile(
    r"\b(represent[ae]|vinculad[oa]s?|relacion(es|ados?)?|conect[ae]|"
    r"trabaja.*(para|en)|emplea(do|da)|pertenece|asociad[oa]|"
    r"regula(do)?|aplica(ble)?|qué ley|qué normativa|"
    r"quién.*(representa|trabaja|dirige|gestiona)|"
    r"relación entre|conexión entre|vínculo)\b",
    re.IGNORECASE,
)


def _detect_relationship_query(query: str) -> bool:
    """Detect if the query asks about relationships between entities."""
    return bool(_RELATIONSHIP_PATTERNS.search(query))


async def _build_system_message(state: ReActState) -> SystemMessage:
    """Build the system message with tools description and sector context."""
    registry = get_tool_registry()
    tools_desc = registry.get_tools_description(
        sector=state.get("sector"),
        features=state.get("features"),
        max_desc_chars=settings.react_tool_description_max_chars,
    )

    prompt = await _load_react_system_prompt()
    prompt = prompt.replace("{tools_description}", tools_desc)
    prompt = prompt.replace("{current_date}", date.today().isoformat())

    # Inject the admin-curated agents catalog so the LLM knows which slugs
    # are valid targets for invoke_agent. Uses a 60s Redis cache to avoid
    # hammering the Main API on every request. If the Langfuse prompt
    # contains a placeholder, replace it; otherwise append the block.
    agents_block = await _build_active_agents_block()
    if "{{ available_agents_block }}" in prompt:
        prompt = prompt.replace("{{ available_agents_block }}", agents_block)
    elif "{available_agents_block}" in prompt:
        prompt = prompt.replace("{available_agents_block}", agents_block)
    else:
        prompt += (
            "\n\n<available_agents>\n"
            f"{agents_block}\n"
            "</available_agents>\n"
            "Si el usuario menciona @<slug>, usa invoke_agent(agent_slug=<slug>, ...). "
            "En otro caso, responde como Emma general sin invocar agentes."
        )

    # If the user explicitly invoked @<slug>, force the agent to call
    # invoke_agent exactly once with that slug.
    requested_slug = state.get("agent_slug")
    if requested_slug:
        prompt += (
            f"\n\n## INVOCACIÓN DE AGENTE FORZADA"
            f"\nEl usuario mencionó @{requested_slug}. DEBES llamar a "
            f"invoke_agent(agent_slug='{requested_slug}', question=<la pregunta>) "
            f"como tu PRIMERA acción. No uses otros tools antes."
        )

    # Forward classify intent to system prompt
    intent = (state.get("metadata") or {}).get("classify_intent", "")
    if intent and intent not in ("conversational", "identity"):
        prompt += f"\n\nIntención detectada: {intent}"

    # Add document context if focused on a specific document
    doc_id = (state.get("metadata") or {}).get("document_id")
    if doc_id:
        prompt += f"\n\nDocumento en contexto: {doc_id}"

    # Inject persistent user memory (cross-session facts)
    user_memory = state.get("user_memory")
    if user_memory:
        prompt += f"\n\n{user_memory}"

    # Inject memory recall clues (MemoRAG — document memory scan results)
    memory_clues = state.get("memory_clues")
    if memory_clues and memory_clues.strip():
        prompt += f"\n\n## Pistas de memoria documental\nBasándote en los documentos del usuario, estas pistas pueden ayudarte a buscar mejor:\n{memory_clues}"

    # Inject structural graph context (knowledge graph grounding)
    graph_context = state.get("graph_context")
    if graph_context and graph_context.strip():
        prompt += f"\n\n{graph_context}"

    # Detect email-sending action and inject strong hint for small models
    query = state.get("query", "")
    is_email_action, email_addr = _detect_email_action(query)
    if is_email_action:
        prompt += (
            f"\n\n## ACCIÓN DETECTADA: ENVIAR EMAIL"
            f"\nEl usuario quiere enviar un email a {email_addr}."
            f"\nUSA `send_email` directamente con confirmed=false."
            f"\nNO busques documentos — usa la conversación previa para componer "
            f"el asunto y cuerpo del email."
            f"\nSi en la conversación se generó un documento con generate_document, "
            f"incluye su attachment_id."
        )

    # Detect relationship queries → force graph_rag as first tool
    if _detect_relationship_query(query):
        prompt += (
            "\n\n## CONSULTA DE RELACIONES DETECTADA"
            "\nEl usuario pregunta sobre relaciones entre entidades (personas, "
            "empresas, leyes, conceptos)."
            "\nUSA `graph_rag` como PRIMERA herramienta para buscar en el grafo "
            "de conocimiento. NO uses smart_search primero."
            "\nSi graph_rag no devuelve resultados suficientes, complementa con smart_search."
        )

    return SystemMessage(content=prompt)


def _build_tool_context(state: ReActState, emit_sse=None) -> Dict[str, Any]:
    """Build minimal context dict for tool execution (avoids copying full state)."""
    ctx = {
        "user_id": state.get("user_id"),
        "user_roles": state.get("user_roles", []),
        "is_admin": state.get("is_admin", False),
        "sector": state.get("sector"),
        "features": state.get("features"),
        "query": state.get("query", ""),
        "thread_id": state.get("thread_id", ""),
        "metadata": state.get("metadata"),
    }
    if emit_sse is not None:
        ctx["emit_sse"] = emit_sse
    return ctx


def _parse_thinking(content: str) -> tuple:
    """Extract thinking tags from LLM response."""
    patterns = [
        (r"<think>(.*?)</think>", re.DOTALL),
        (r"<thinking>(.*?)</thinking>", re.DOTALL),
        (r"<pensamiento>(.*?)</pensamiento>", re.DOTALL),
    ]
    for pattern, flags in patterns:
        match = re.search(pattern, content, flags)
        if match:
            thinking = match.group(1).strip()
            remaining = re.sub(pattern, "", content, flags=flags).strip()
            return thinking, remaining
    return None, content


def _compress_prior_turns(messages: list) -> list:
    """Remove tool data from prior turns to prevent cross-turn hallucination.

    The LangGraph checkpointer restores ALL messages from previous turns,
    including ToolMessages with raw search results (document titles, entity
    names, amounts).  When the LLM sees this data in context it may skip
    tool calling and fabricate answers from stale turn-1 observations.

    This function identifies the boundary of the **current turn** (the last
    HumanMessage) and for all prior messages:
    - Drops ToolMessages (raw tool output — the main hallucination source)
    - Drops AIMessages that only contain tool_calls (intermediate steps)
    - Keeps AIMessages with actual content (final answers for conversation context)
    - Keeps HumanMessages (conversation flow)

    Current-turn messages are left untouched so the ReAct loop works normally.
    """
    from langchain_core.messages import HumanMessage

    # Find index of last HumanMessage (start of current turn)
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    if last_human_idx <= 0:
        return messages  # No prior turns to compress

    prior = messages[:last_human_idx]
    current = messages[last_human_idx:]

    compressed: list = []
    dropped = 0
    for msg in prior:
        if isinstance(msg, ToolMessage):
            dropped += 1
            continue
        if isinstance(msg, AIMessage):
            has_tool_calls = hasattr(msg, "tool_calls") and msg.tool_calls
            has_content = bool(msg.content and msg.content.strip())
            if has_tool_calls and not has_content:
                # Pure tool-calling step (no user-facing content) — drop
                dropped += 1
                continue
            if has_tool_calls and has_content:
                # Keep the response text but strip tool_calls so the LLM
                # doesn't see stale function calls from prior turns
                compressed.append(AIMessage(content=msg.content, id=msg.id))
                dropped += 1  # counts as partial compression
                continue
            # Content-only AI message (final answer) — keep as-is
            compressed.append(msg)
        else:
            # HumanMessage, SystemMessage, etc.
            compressed.append(msg)

    if dropped:
        logger.info(
            f"Cross-turn compression: removed {dropped} tool/intermediate messages "
            f"from prior turns ({len(prior)} → {len(compressed)} prior messages)"
        )

    return compressed + list(current)


def _detect_stuck(tool_calls_history: List[Dict[str, Any]], window: int = settings.react_stuck_detection_window) -> bool:
    """Detect if the agent is stuck in a loop.

    Two heuristics:
    1. Exact match: last `window` entries have identical tool name + args.
    2. Near-stuck: last `window` entries call the same tool with different args
       (e.g., search_documents with slightly varied queries).
    """
    if len(tool_calls_history) < window:
        return False

    recent = tool_calls_history[-window:]

    # Check 1: exact match (existing behavior)
    signatures = []
    for entry in recent:
        sig = f"{entry.get('name', '')}:{sorted(entry.get('args', {}).items())}"
        signatures.append(sig)

    if len(set(signatures)) == 1:
        return True

    # Check 2: same tool called repeatedly with different args (near-stuck)
    names = [e.get("name", "") for e in recent]
    if len(set(names)) == 1 and names[0] != "terminate":
        return True

    return False


@observe(as_type="span", name="react_loop_node")
async def react_loop_node(state: ReActState) -> Dict[str, Any]:
    """Execute one iteration of the ReAct Think-Act-Observe cycle.

    This node is called repeatedly by the graph's conditional edge.
    Each invocation:
    1. Builds messages (system + history + prior tool results)
    2. Calls LLM with available tools
    3. If tool_calls: executes them in parallel, returns updated state (is_complete=False)
    4. If no tool_calls or terminate: returns with is_complete=True

    Returns:
        State updates: messages, current_step, is_complete, reasoning_steps,
        possibly final_answer and sources.
    """
    start = time.time()
    step = state.get("current_step", 0)
    max_steps = state.get("max_steps", 10)
    tool_calls_history = list(state.get("tool_calls_history", []))

    # Obtain stream writer for real-time SSE from tools (report.*, claim_*, etc.)
    _stream_writer = None
    try:
        from langgraph.config import get_stream_writer
        _stream_writer = get_stream_writer()
    except Exception:
        pass

    # Safety: max steps reached
    if step >= max_steps:
        logger.warning(f"ReAct loop: max steps ({max_steps}) reached, forcing exit")
        return {
            "is_complete": True,
            "current_step": step,
            "success": True,
            "reasoning_steps": [{
                "type": StepType.ERROR.value,
                "content": f"Max steps ({max_steps}) reached — responding with available information",
            }],
            "metadata": {"react_forced_exit": "max_steps"},
        }

    # Stuck detection
    if _detect_stuck(tool_calls_history):
        logger.warning("ReAct loop: stuck detection triggered, forcing exit")
        return {
            "is_complete": True,
            "current_step": step,
            "success": True,
            "reasoning_steps": [{
                "type": StepType.ERROR.value,
                "content": "Agent stuck in loop — responding with available information",
            }],
            "metadata": {"react_forced_exit": "stuck_detection"},
        }

    # Build tool schemas — use cache from metadata if available
    cached_schemas = (state.get("metadata") or {}).get("_tool_schemas_cache")
    if cached_schemas is not None:
        tool_schemas = cached_schemas
    else:
        registry = get_tool_registry()
        tools = registry.get_tools_for_context(
            sector=state.get("sector"),
            features=state.get("features"),
        )
        tool_schemas = [t.to_openai_param() for t in tools]

    # Build messages for LLM
    # On first step: prepend system message
    # On subsequent steps: messages already contain system + history + tool results
    existing_messages = list(state.get("messages", []))

    # Cross-turn anti-hallucination: remove ToolMessages and intermediate
    # AI tool_call messages from prior turns so the LLM cannot fabricate
    # answers from stale observations (e.g., inventing company names from
    # a previous structural_query result).  Only applied on step 0 of a
    # new turn — subsequent steps within the same turn need their tools.
    if step == 0:
        existing_messages = _compress_prior_turns(existing_messages)

    # Ensure system message is present
    has_system = any(
        isinstance(m, SystemMessage)
        for m in existing_messages
    )

    llm_messages: List[Dict[str, Any]] = []

    # Use cached system message if available, otherwise build and cache
    cached_sys_content = (state.get("metadata") or {}).get("_system_message_cache")
    if not has_system and cached_sys_content:
        llm_messages.append({"role": "system", "content": cached_sys_content})
    elif not has_system:
        sys_msg = await _build_system_message(state)
        cached_sys_content = sys_msg.content
        llm_messages.append({"role": "system", "content": cached_sys_content})

    # Convert LangChain messages to dict format for LLM client
    for msg in existing_messages:
        if isinstance(msg, SystemMessage):
            llm_messages.append({"role": "system", "content": msg.content})
        elif isinstance(msg, AIMessage):
            msg_dict: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            # Preserve tool_calls if present
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.get("id", tc.get("tool_call_id", "")),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": tc.get("args", tc.get("arguments", "")),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                # Ensure function arguments are strings
                for tc_dict in msg_dict["tool_calls"]:
                    args = tc_dict["function"]["arguments"]
                    if isinstance(args, dict):
                        tc_dict["function"]["arguments"] = json.dumps(args)
            llm_messages.append(msg_dict)
        elif isinstance(msg, ToolMessage):
            llm_messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id,
                "content": msg.content or "",
            })
        else:
            # HumanMessage or other
            llm_messages.append({"role": "user", "content": msg.content or ""})

    # Token-budget sliding window: trim messages to fit within model context.
    # This replaces the old message-count window, which could still overflow
    # when tool observations (e.g., get_document_content) are large.
    # Reserve tokens for: system prompt overhead, completion, and safety margin.
    MODEL_CONTEXT_BUDGET = int(os.getenv("SGLANG_MAX_MODEL_LEN", os.getenv("VLLM_MAX_MODEL_LEN", "32768")))
    # Leave room for completion tokens + safety margin
    input_token_budget = MODEL_CONTEXT_BUDGET - settings.react_max_completion_tokens - 512
    llm_messages = trim_messages_to_token_budget(
        llm_messages,
        token_budget=input_token_budget,
        preserve_recent=max(4, settings.react_context_compress_preserve_recent),
    )

    # Call LLM with tools
    # Per-request thinking override: when user enables deep_reasoning in UI,
    # pass enable_thinking to override the PLANNER default (no thinking)
    #
    # Dynamic max_tokens: estimate input tokens and cap completion to avoid
    # exceeding the 16K context. PLANNER needs ~500 tokens max for tool calls.
    MODEL_CONTEXT_LIMIT = int(os.getenv("SGLANG_MAX_MODEL_LEN", os.getenv("VLLM_MAX_MODEL_LEN", "32768")))
    # Count ALL content: message content + tool_calls JSON structures + overhead
    _est_chars = 0
    for m in llm_messages:
        _est_chars += len(m.get("content", "") or "")
        # tool_calls JSON adds significant tokens (name, arguments, structure)
        if m.get("tool_calls"):
            for tc in m["tool_calls"]:
                _est_chars += len(json.dumps(tc.get("function", {}), default=str))
                _est_chars += 20  # role/structure overhead per tool_call
        _est_chars += 10  # per-message overhead (role tokens, separators)
    estimated_input_tokens = _est_chars // 3 + 100  # ~3 chars/token for multilingual
    desired_max = settings.react_max_completion_tokens
    safe_max = max(512, MODEL_CONTEXT_LIMIT - estimated_input_tokens - 200)
    effective_max_tokens = min(desired_max, safe_max)
    if effective_max_tokens < desired_max:
        logger.info(
            f"ReAct step {step}: capping max_tokens {desired_max}→{effective_max_tokens} "
            f"(~{estimated_input_tokens} input tokens, {MODEL_CONTEXT_LIMIT} context)"
        )

    # Pre-call safety: if input alone would exceed context, force-compress tool observations
    if estimated_input_tokens > MODEL_CONTEXT_LIMIT - 512:
        logger.warning(
            f"ReAct step {step}: estimated {estimated_input_tokens} input tokens exceeds "
            f"safe limit — force-compressing tool observations"
        )
        # Compress BaseMessage list from state, then rebuild llm_messages
        all_base_messages = list(state.get("messages", []))
        compressed = compress_tool_observations(
            all_base_messages,
            budget=2000,  # aggressive compression
            preserve_recent=1,
        )
        if compressed is not None:
            # Rebuild llm_messages from compressed BaseMessages
            llm_messages_new: List[Dict[str, Any]] = []
            if cached_sys_content:
                llm_messages_new.append({"role": "system", "content": cached_sys_content})
            for msg in compressed:
                if isinstance(msg, SystemMessage):
                    llm_messages_new.append({"role": "system", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    msg_d: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        msg_d["tool_calls"] = [
                            {
                                "id": tc.get("id", tc.get("tool_call_id", "")),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(tc.get("args", tc.get("arguments", "")))
                                        if isinstance(tc.get("args", tc.get("arguments", "")), dict)
                                        else tc.get("args", tc.get("arguments", "")),
                                },
                            }
                            for tc in msg.tool_calls
                        ]
                    llm_messages_new.append(msg_d)
                elif isinstance(msg, ToolMessage):
                    llm_messages_new.append({
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content or "",
                    })
                else:
                    llm_messages_new.append({"role": "user", "content": msg.content or ""})
            llm_messages = llm_messages_new
            # Recalculate tokens after compression
            _est_chars2 = sum(len(m.get("content", "") or "") for m in llm_messages)
            estimated_input_tokens = _est_chars2 // 3 + 100
            safe_max = max(512, MODEL_CONTEXT_LIMIT - estimated_input_tokens - 200)
            effective_max_tokens = min(desired_max, safe_max)
            logger.info(
                f"ReAct step {step}: after compression ~{estimated_input_tokens} input tokens, "
                f"max_tokens={effective_max_tokens}"
            )

    try:
        from app.agents.llm_models import get_planner_model

        model = get_planner_model()
        if tool_schemas:
            model = model.bind_tools(tool_schemas)
        model = model.bind(max_tokens=effective_max_tokens)

        tool_names = [t["function"]["name"] for t in tool_schemas] if tool_schemas else []
        logger.info(
            f"ReAct step {step}: {len(llm_messages)} msgs, {len(tool_schemas)} tools "
            f"({', '.join(tool_names[:5])}{'...' if len(tool_names) > 5 else ''}), "
            f"max_tokens={effective_max_tokens}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            for i, m in enumerate(llm_messages):
                role = m.get("role", "?")
                content = (m.get("content") or "")[:150]
                logger.debug(f"  msg[{i}] role={role}: {content!r}")

        per_request_thinking = state.get("enable_thinking")
        if per_request_thinking:
            model = model.bind(extra_body={
                "repetition_penalty": 1.15,
                "chat_template_kwargs": {"enable_thinking": True},
            })

        response = await model.ainvoke(llm_messages)
    except Exception as e:
        error_str = str(e)
        logger.error(f"ReAct loop: LLM call failed at step {step}: {error_str}")

        # ── Context overflow recovery: trim history and retry once ──
        _is_context_overflow = (
            "context length" in error_str.lower()
            or "token" in error_str.lower() and ("exceed" in error_str.lower() or "limit" in error_str.lower())
        )
        if _is_context_overflow and not state.get("metadata", {}).get("_context_overflow_retried"):
            logger.warning(
                f"ReAct step {step}: context overflow detected, trimming history and retrying"
            )
            # Aggressively trim: keep system + last 6 messages
            system_msgs = [m for m in llm_messages if m.get("role") == "system"]
            non_system = [m for m in llm_messages if m.get("role") != "system"]
            # Walk cut boundary to avoid orphaning tool messages
            keep = min(6, len(non_system))
            cut = len(non_system) - keep
            while cut > 0 and cut < len(non_system) and non_system[cut].get("role") == "tool":
                cut -= 1
            trimmed = system_msgs + non_system[cut:]
            # Retry with trimmed messages and minimum completion tokens
            try:
                from app.agents.llm_models import get_planner_model as _get_planner
                retry_model = _get_planner()
                if tool_schemas:
                    retry_model = retry_model.bind_tools(tool_schemas)
                retry_model = retry_model.bind(max_tokens=512)
                if per_request_thinking:
                    retry_model = retry_model.bind(extra_body={
                        "repetition_penalty": 1.15,
                        "chat_template_kwargs": {"enable_thinking": True},
                    })
                response = await retry_model.ainvoke(trimmed)
                logger.info(
                    f"ReAct step {step}: retry succeeded after trimming "
                    f"({len(llm_messages)}→{len(trimmed)} messages)"
                )
                # Fall through to normal processing below
            except Exception as retry_err:
                logger.error(f"ReAct loop: retry also failed: {retry_err}")
                return {
                    "is_complete": True,
                    "current_step": step + 1,
                    "success": False,
                    "final_answer": (
                        "Lo siento, la conversación se ha vuelto demasiado larga para procesar. "
                        "Por favor, inicia una nueva conversación para continuar."
                    ),
                    "reasoning_steps": [{
                        "type": StepType.ERROR.value,
                        "content": f"Context overflow at step {step} — retry failed",
                    }],
                    "metadata": {"_context_overflow_retried": True},
                }
        else:
            # Non-overflow error or already retried: return user-friendly message
            # Log full technical detail but never expose to user
            return {
                "is_complete": True,
                "current_step": step + 1,
                "success": False,
                "final_answer": (
                    "Lo siento, hubo un problema temporal procesando tu consulta. "
                    "Por favor, inténtalo de nuevo en unos segundos."
                ),
                "reasoning_steps": [{
                    "type": StepType.ERROR.value,
                    "content": f"LLM error at step {step}: {error_str}",
                }],
            }

    # Track thinking/reasoning
    reasoning_steps: List[Dict[str, Any]] = []
    content = response.content or ""

    # Extract thinking from response
    thinking, content = _parse_thinking(content)
    if thinking:
        reasoning_steps.append({
            "type": StepType.THINKING.value,
            "content": thinking[:500],
        })

    # Also capture explicit thinking from response (if available)
    resp_thinking = getattr(response, "thinking", None)
    if resp_thinking and resp_thinking != thinking:
        reasoning_steps.append({
            "type": StepType.THINKING.value,
            "content": resp_thinking[:500],
        })

    latency_ms = (time.time() - start) * 1000

    # ─── No tool calls → agent wants to respond directly ───
    if not response.tool_calls:
        intent = (state.get("metadata") or {}).get("classify_intent", "")
        metadata = state.get("metadata") or {}

        # Gate 1: Step-0 no-tools retry (CRAG quality gate)
        if settings.react_quality_gate_enabled:
            should_retry, corrective_msg = await assess_step0_no_tools(
                intent=intent, step=step, has_tool_calls=False, metadata=metadata,
            )
            if should_retry:
                from langchain_core.messages import HumanMessage
                return {
                    "is_complete": False,
                    "current_step": step + 1,
                    "messages": [
                        AIMessage(content=content),
                        HumanMessage(content=corrective_msg),
                    ],
                    "reasoning_steps": reasoning_steps + [{
                        "type": StepType.ERROR.value,
                        "content": "Quality Gate: step 0 no-tools — injecting retry",
                    }],
                    "metadata": {
                        f"react_step_{step}_latency_ms": latency_ms,
                        "quality_gate_step0_retried": True,
                        "_tool_schemas_cache": tool_schemas,
                        "_system_message_cache": cached_sys_content,
                    },
                }

        if step == 0 and intent in ("document_query", "legal_query", "analysis"):
            logger.warning(
                f"⚠️ ReAct step 0 — NO tool calls for intent '{intent}'. "
                f"LLM responded directly without searching. "
                f"Query: '{state.get('query', '')[:80]}'. "
                f"Response preview: '{content[:200]}'"
            )
        else:
            logger.info(
                f"ReAct loop: step {step} — no tool calls, completing. "
                f"Response preview: '{content[:200]}'"
            )

        # Clean content of any raw tool_call tags from small models
        content = re.sub(r"</?tool_call>", "", content).strip()

        return {
            "is_complete": True,
            "final_answer": content,
            "current_step": step + 1,
            "success": True,
            "messages": [AIMessage(content=content)],
            "reasoning_steps": reasoning_steps,
            "metadata": {
                f"react_step_{step}_latency_ms": latency_ms,
                "react_total_steps": step + 1,
                "react_no_tools_step0": step == 0,
                "_tool_schemas_cache": tool_schemas,
                "_system_message_cache": cached_sys_content,
            },
        }

    # ─── Execute tools ───
    # response is an AIMessage with .tool_calls (list of dicts: name/args/id)
    ai_message = AIMessage(
        content=content,
        tool_calls=response.tool_calls,
    )

    new_messages = [ai_message]
    new_sources: List[Dict[str, Any]] = []

    # Separate terminate from non-terminate tool calls
    terminate_tc = None
    regular_tcs = []
    for tc in response.tool_calls:
        tc_name = tc["name"]
        tc_args = tc["args"]
        tc_id = tc.get("id", "")

        reasoning_steps.append({
            "type": StepType.TOOL_CALL.value,
            "content": f"{tc_name}({_summarize_args(tc_args)})",
            "summary": _humanize_tool_call(tc_name, tc_args),
        })
        # Track for stuck detection
        tool_calls_history.append({
            "name": tc_name,
            "args": tc_args,
            "step": step,
        })

        if tc_name == "terminate":
            terminate_tc = tc
        else:
            regular_tcs.append(tc)

    def _emit_sse_via_writer(event: dict):
        """Bridge: tool emit_sse callback -> LangGraph stream writer."""
        if _stream_writer:
            _stream_writer({"type": event.get("event_type", "custom_event"), "data": event.get("payload", event)})

    tool_context = _build_tool_context(state, emit_sse=_emit_sse_via_writer if _stream_writer else None)
    registry = get_tool_registry()

    # If terminate found, execute it and return immediately
    if terminate_tc:
        t_name = terminate_tc["name"]
        t_args = terminate_tc["args"]
        t_id = terminate_tc.get("id", "")
        answer = t_args.get("answer", "")

        # Gate 2: Low-quality terminate retry (CRAG quality gate)
        if settings.react_quality_gate_enabled:
            metadata = state.get("metadata") or {}
            intent = metadata.get("classify_intent", "")
            accumulated_sources = state.get("sources", [])

            should_retry, corrective_msg = await assess_terminate_quality(
                answer=answer,
                sources=accumulated_sources,
                intent=intent,
                step=step,
                max_steps=max_steps,
                metadata=metadata,
                tool_calls_history=tool_calls_history,
                messages=state.get("messages", []),
            )
            if should_retry:
                from langchain_core.messages import HumanMessage
                logger.info(f"Quality Gate 2: blocking terminate at step {step}, injecting retry")
                return {
                    "is_complete": False,
                    "current_step": step + 1,
                    "messages": [
                        ai_message,
                        ToolMessage(content="[Terminate bloqueado por quality gate]", tool_call_id=t_id),
                        HumanMessage(content=corrective_msg),
                    ],
                    "tool_calls_history": tool_calls_history,
                    "reasoning_steps": reasoning_steps + [{
                        "type": StepType.ERROR.value,
                        "content": "Quality Gate: low-quality terminate — injecting retry",
                    }],
                    "metadata": {
                        f"react_step_{step}_latency_ms": latency_ms,
                        "quality_gate_terminate_retried": True,
                        "quality_gate_retrieval_retried": True,
                        "quality_gate_faithfulness_retried": True,
                        "_tool_schemas_cache": tool_schemas,
                        "_system_message_cache": cached_sys_content,
                    },
                }

        result = await registry.execute(t_name, t_args, context=tool_context)

        new_messages.append(ToolMessage(
            content=result.output,
            tool_call_id=t_id,
        ))

        reasoning_steps.append({
            "type": StepType.RESPONSE.value,
            "content": "Terminate: agent produced final answer",
        })

        # Prefer tool-accumulated sources (from state) over LLM-constructed ones.
        # The LLM often misattributes metadata (e.g., assigns boe_id from legislation
        # to tenant documents). Tool results have correct source_type/boe_id.
        accumulated_sources = state.get("sources", [])
        terminate_sources = t_args.get("sources", []) or result.sources
        final_sources = accumulated_sources if accumulated_sources else terminate_sources

        return {
            "is_complete": True,
            "final_answer": answer or result.output,
            "sources": final_sources,
            "messages": new_messages,
            "current_step": step + 1,
            "tool_calls_history": tool_calls_history,
            "success": True,
            "reasoning_steps": reasoning_steps,
            "metadata": {
                f"react_step_{step}_latency_ms": latency_ms,
                "react_total_steps": step + 1,
                "react_terminated": True,
                "_tool_schemas_cache": tool_schemas,
                "_system_message_cache": cached_sys_content,
            },
        }

    # Execute non-terminate tools in parallel
    async def _run_tool(tc):
        return tc, await registry.execute(tc["name"], tc["args"], context=tool_context)

    # Emit SSE heartbeats while tools run. Long tools (generate_document,
    # forge_document, verified_generation) can block for 60–90s. Without
    # intermediate events the browser / proxy / ISP NAT can close the
    # stream — users see "API network error" even though the backend
    # eventually finishes. The watchdog emits a reasoning_step every
    # KEEPALIVE_INTERVAL seconds after KEEPALIVE_INITIAL_DELAY so fast
    # tools (sub-second smart_search etc.) do not add noise.
    KEEPALIVE_INITIAL_DELAY = 5
    KEEPALIVE_INTERVAL = 15

    async def _emit_tool_keepalive(writer, tool_names: List[str]):
        try:
            await asyncio.sleep(KEEPALIVE_INITIAL_DELAY)
            elapsed = KEEPALIVE_INITIAL_DELAY
            label = ", ".join(tool_names[:3]) + ("..." if len(tool_names) > 3 else "")
            while True:
                try:
                    writer({
                        "type": "reasoning_step",
                        "data": {
                            "step_type": "tool_running",
                            "content": f"Ejecutando {label} ({elapsed}s transcurridos)",
                        },
                    })
                except Exception:
                    pass  # never let keepalive kill the tool loop
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                elapsed += KEEPALIVE_INTERVAL
        except asyncio.CancelledError:
            raise

    keepalive_task = None
    if _stream_writer and regular_tcs:
        keepalive_task = asyncio.create_task(
            _emit_tool_keepalive(_stream_writer, [tc["name"] for tc in regular_tcs])
        )
    try:
        results = await asyncio.gather(*[_run_tool(tc) for tc in regular_tcs])
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except asyncio.CancelledError:
                pass

    # Process results in order
    last_retrieval_quality = None
    email_preview_pending = None  # Track email preview for HITL interrupt
    for tc, result in results:
        tc_name = tc["name"]
        tc_id = tc.get("id", "")

        # Truncate large observations (OpenManus max_observe pattern)
        observation = result.output
        max_observe = settings.react_max_observe_length
        if len(observation) > max_observe:
            observation = observation[:max_observe] + "\n[... truncado]"

        new_messages.append(ToolMessage(
            content=observation,
            tool_call_id=tc_id,
        ))

        # Collect sources
        if result.sources:
            new_sources.extend(result.sources)

        # Extract retrieval quality from smart_search for Quality Gate 4
        if tc_name == "smart_search" and result.data and result.data.get("retrieval_quality"):
            last_retrieval_quality = result.data["retrieval_quality"]

        # Detect send_email preview → will trigger HITL interrupt
        if tc_name == "send_email" and result.data and result.data.get("preview"):
            email_preview_pending = {
                "tool_call": tc,
                "result": result,
            }

        reasoning_steps.append({
            "type": StepType.OBSERVATION.value,
            "content": observation[:300],
            "source": tc_name,
            "summary": _humanize_tool_result(tc_name, tc["args"], result),
        })

        # Emit source_evidence from graph_rag
        if tc_name == "graph_rag" and result.data and result.data.get("source_evidence"):
            reasoning_steps.append({
                "type": "source_evidence",
                "content": json.dumps(result.data["source_evidence"], ensure_ascii=False),
                "source": "graph_rag",
            })

    # ─── HITL: Email confirmation interrupt ────────────────────────────
    # When send_email returns a preview, pause the graph and show
    # confirmation buttons to the user. On resume, re-invoke send_email
    # with confirmed=true automatically.
    if email_preview_pending:
        from langgraph.types import interrupt
        tc = email_preview_pending["tool_call"]
        tc_args = tc["args"]
        tc_id = tc.get("id", "")
        result = email_preview_pending["result"]
        to_addr = result.data.get("to", "")

        logger.info(f"ReAct loop: email preview detected → HITL interrupt (to={to_addr})")

        # Return current state with messages so far, then interrupt.
        # Uses HITLReviewRequest schema so frontend can render the review card.
        decision = interrupt({
            "type": "hitl_review",
            "action_request": {
                "name": "send_email",
                "args": tc_args,
                "description": f"Enviar email a {to_addr}",
            },
            "review_config": {
                "allowed_decisions": ["approve", "edit", "reject"],
                "editable_fields": ["to", "subject", "body"],
            },
        })

        # After resume: determine decision type.
        # Backwards compat: old frontend sends "confirm_send"/"cancel_send" strings
        if isinstance(decision, str):
            decision_type = "approve" if decision == "confirm_send" else "reject"
        elif isinstance(decision, dict):
            decision_type = decision.get("type", "approve")
        else:
            decision_type = "approve"

        if decision_type == "approve":
            logger.info(f"ReAct loop: email approved by user → sending to {to_addr}")
            registry = await get_tool_registry()
            send_result = await registry.execute(
                "send_email",
                {**tc_args, "confirmed": True},
                context=tool_context,
            )
            # Replace the preview ToolMessage with the send result
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(
                        content=send_result.output,
                        tool_call_id=tc_id,
                    )
                    break
            logger.info(f"ReAct loop: email sent successfully to {to_addr}")

        elif decision_type == "edit":
            # User edited the email args before approving
            edited_args = decision.get("edited_args", tc_args) if isinstance(decision, dict) else tc_args
            logger.info(f"ReAct loop: email edited by user → sending to {edited_args.get('to', to_addr)}")
            registry = await get_tool_registry()
            send_result = await registry.execute(
                "send_email",
                {**edited_args, "confirmed": True},
                context=tool_context,
            )
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(
                        content=send_result.output,
                        tool_call_id=tc_id,
                    )
                    break
            logger.info(f"ReAct loop: edited email sent successfully")

        else:
            # reject (or any unknown decision type)
            feedback = decision.get("message", "") if isinstance(decision, dict) else ""
            rejection_msg = "El usuario ha cancelado el envío del email."
            if feedback:
                rejection_msg += f" Motivo: {feedback}"
            logger.info(f"ReAct loop: email rejected by user")
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(
                        content=rejection_msg,
                        tool_call_id=tc_id,
                    )
                    break

    # ─── Context compression: compress old ToolMessages if context overflows ───
    if settings.react_context_compress_enabled:
        all_messages = list(state.get("messages", [])) + new_messages
        compressed = compress_tool_observations(
            all_messages,
            budget=settings.react_context_compress_threshold,
            preserve_recent=settings.react_context_compress_preserve_recent,
        )
        if compressed is not None:
            # Replace entire message list with compressed version
            # Return compressed as the full messages list (overwrite, not append)
            reasoning_steps.append({
                "type": StepType.OBSERVATION.value,
                "content": "Context compressed to fit token budget",
            })
            _compressed_meta = {
                f"react_step_{step}_latency_ms": latency_ms,
                "_tool_schemas_cache": tool_schemas,
                "_system_message_cache": cached_sys_content,
                "context_compressed": True,
            }
            if last_retrieval_quality:
                _compressed_meta["last_retrieval_quality"] = last_retrieval_quality
            return {
                "messages": compressed,
                "current_step": step + 1,
                "is_complete": False,
                "tool_calls_history": tool_calls_history,
                "sources": new_sources,
                "reasoning_steps": reasoning_steps,
                "metadata": _compressed_meta,
            }

    # Return updated state — is_complete=False triggers another react_loop iteration
    _step_meta = {
        f"react_step_{step}_latency_ms": latency_ms,
        "_tool_schemas_cache": tool_schemas,
        "_system_message_cache": cached_sys_content,
    }
    if last_retrieval_quality:
        _step_meta["last_retrieval_quality"] = last_retrieval_quality
    return {
        "messages": new_messages,
        "current_step": step + 1,
        "is_complete": False,
        "tool_calls_history": tool_calls_history,
        "sources": new_sources,
        "reasoning_steps": reasoning_steps,
        "metadata": _step_meta,
    }


def _summarize_args(args: Dict[str, Any], max_length: int = 100) -> str:
    """Create a short summary of tool arguments for logging."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 50:
            v_str = v_str[:47] + "..."
        parts.append(f"{k}={v_str}")
    result = ", ".join(parts)
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    return result


# ─── Humanized summaries for ActivityTimeline ─────────────────────────────────
# These are short, user-facing labels shown in the frontend timeline.
# Built from structured data (ToolResult.data, tool args), NOT regex on output text.

_TOOL_CALL_LABELS = {
    "smart_search": lambda args: f"Buscando \"{args.get('query', '')[:40]}\"...",
    "get_document_content": lambda args: "Leyendo documento...",
    "structural_query": lambda args: "Consultando el grafo...",
    "web_search": lambda args: f"Buscando en internet \"{args.get('query', '')[:40]}\"...",
    "search_jurisprudence": lambda args: f"Buscando jurisprudencia: \"{args.get('query', '')[:40]}\"...",
    "analyze_domain": lambda args: "Realizando análisis especializado...",
    "verified_generation": lambda args: "Ejecutando generación verificada...",
    "predictive_analysis": lambda args: "Ejecutando análisis predictivo...",
    "list_sources": lambda args: "Explorando fuentes disponibles...",
    "query_connector": lambda args: "Consultando conector externo...",
    "generate_document": lambda args: "Generando documento...",
    "forge_document": lambda args: "Creando documento PDF...",
    "send_email": lambda args: f"Enviando email a {args.get('to', '...')}...",
    "generate_knowledge_report": lambda args: f"Generando informe de {args.get('entity_uri', '').split('/')[-1].replace('-', ' ')}...",
}


def _humanize_tool_call(name: str, args: Dict[str, Any]) -> str:
    """User-facing label for a tool call (active/in-progress)."""
    fn = _TOOL_CALL_LABELS.get(name)
    if fn:
        try:
            return fn(args)
        except Exception:
            pass
    return "Procesando..."


def _humanize_tool_result(name: str, args: Dict[str, Any], result) -> str:
    """User-facing label for a completed tool result.

    Uses ToolResult.data (structured) and args — never parses output text.
    """
    data = result.data if result.data else {}

    if name == "smart_search":
        count = data.get("result_count")
        if count is not None:
            return f"{count} resultados encontrados"
        if not result.success:
            return "Sin resultados"
        return "Búsqueda completada"

    if name == "get_document_content":
        title = data.get("title") or ""
        if not title and result.sources:
            title = result.sources[0].get("title", "")
        return f"Leí \"{title}\"" if title else "Documento leído"

    if name == "structural_query":
        raw = data.get("raw_data") or {}
        count = raw.get("count") or raw.get("total")
        if count is not None:
            return f"{count} documentos en el grafo"
        return "Consulta al grafo completada"

    if name == "web_search":
        return "Resultados de internet obtenidos"

    if name == "search_jurisprudence":
        count = data.get("result_count")
        return f"{count} sentencias encontradas" if count else "Jurisprudencia encontrada"

    if name == "analyze_domain":
        return "Análisis especializado completado"

    if name == "send_email":
        return f"Email preparado para {args.get('to', '...')}"

    if name == "generate_document":
        return "Documento generado"

    if name == "forge_document":
        return "PDF creado"

    if name == "generate_knowledge_report":
        entity = args.get("entity_uri", "").split("/")[-1].replace("-", " ").title()
        return f"Informe generado: {entity}" if entity else "Informe de conocimiento generado"

    return "Paso completado"


# ---------------------------------------------------------------------------
# Admin-curated agents catalog injection
# ---------------------------------------------------------------------------

_AGENTS_BLOCK_CACHE_KEY = "emma_react:active_agents_block"
_AGENTS_BLOCK_TTL = 60


async def _build_active_agents_block(limit: int = 50) -> str:
    """Render the active agents catalog as the ``<available_agents>`` block.

    Cache 60s in Redis to avoid hitting the Main API on every request.
    Falls back to "(no agents currently active)" if the catalog is empty
    or unreachable.
    """
    redis_client = None
    try:
        from app.core.redis_client import get_redis  # type: ignore
        redis_client = get_redis()
    except Exception:
        redis_client = None

    if redis_client is not None:
        try:
            cached = await redis_client.get(_AGENTS_BLOCK_CACHE_KEY)
            if cached:
                return cached if isinstance(cached, str) else cached.decode("utf-8")
        except Exception:
            pass

    try:
        from app.services.main_api_client import MainAPIClient
        rows = await MainAPIClient().list_active_agents(limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to load active agents catalog: {exc}")
        return "(no agents currently active)"

    if not rows:
        block = "(no agents currently active)"
    else:
        lines = []
        for row in rows:
            slug = row.get("slug", "?")
            description = (row.get("description") or "").strip()
            if len(description) > 80:
                description = description[:77] + "..."
            lines.append(f"- {slug}: {description}" if description else f"- {slug}")
        block = "\n".join(lines)

    if redis_client is not None:
        try:
            await redis_client.set(_AGENTS_BLOCK_CACHE_KEY, block, ex=_AGENTS_BLOCK_TTL)
        except Exception:
            pass
    return block
