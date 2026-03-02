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
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.core.config import settings
from app.core.langfuse_config import observe
from ..state import ReActState
from ..reasoning_tracker import StepType
from ..tools.registry import get_tool_registry

logger = logging.getLogger(__name__)

async def _load_react_system_prompt() -> str:
    """Load the ReAct system prompt from Langfuse (primary) → YAML → fallback.

    Uses the same TTL-cached pattern as swarm prompts via LangfusePromptClient.
    """
    # Try Langfuse first (TTL-cached, ~0ms on hit)
    try:
        from app.services.langfuse_prompt_client import get_langfuse_prompt_client
        client = get_langfuse_prompt_client()
        cached = await client.get_prompt("emma_react_system")
        if cached and cached.content:
            logger.debug(f"📥 ReAct prompt loaded from Langfuse (v{cached.version})")
            return cached.content
    except Exception as e:
        logger.debug(f"Langfuse prompt fetch skipped: {e}")

    # YAML fallback
    candidates = [
        Path("/app/config/prompts/emma_prompts.yaml"),
        Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
    ]
    for p in candidates:
        if p.exists():
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                react_config = data.get("react_agent", {})
                if react_config and "system" in react_config:
                    return react_config["system"]
            except Exception as e:
                logger.warning(f"Failed to load react system prompt from YAML: {e}")

    # Hardcoded fallback
    return _REACT_SYSTEM_FALLBACK


_REACT_SYSTEM_FALLBACK = """\
Eres Emma, la IA del sistema NouxCubeIA (EDMS empresarial).

## Qué haces
Accedes a TODAS las fuentes de información del usuario — documentos indexados, \
bases de datos, conectores externos (SharePoint, Alfresco, Google Drive), \
legislación española (BOE), y búsqueda web — para responder consultas \
con información verificada y citada.

## Tus capacidades
- Buscar y localizar documentos por contenido o metadatos
- Contar, listar y filtrar documentos (expedientes, contratos, facturas...)
- Leer y analizar documentos completos
- Análisis especializado: legal, fiscal, laboral, RGPD, contractual, compliance
- Consultar legislación vigente (BOE: leyes, reglamentos, normativas)
- Generar borradores de documentos basados en contexto y normativa
- Buscar información en internet cuando las fuentes internas no son suficientes
- Descubrir y consultar fuentes externas conectadas al sistema

## Herramientas disponibles
{tools_description}

## Estrategia de razonamiento

### Paso 1: ENTENDER
Antes de actuar, identifica qué necesita el usuario exactamente.

### Paso 2: BUSCAR
- Datos cuantitativos (cuántos, lista de...) → `structural_query`
- Documentos o legislación → `smart_search` (detecta automáticamente qué buscar; usa scope='documents', 'legislation' o 'auto')
- Contenido completo de un documento → `get_document_content`
- Información externa → `web_search`
- Fuentes disponibles → `list_sources`

### Paso 3: EVALUAR resultados (CRÍTICO)
Después de cada búsqueda, EVALÚA antes de responder:
- ¿Los resultados responden REALMENTE a la pregunta del usuario?
- ¿Los documentos/leyes encontrados son los que se pidieron, o son de otra ley/tema?
- ¿La relevancia es suficiente o los resultados son genéricos?

Si los resultados NO son relevantes:
- REFORMULA la búsqueda con términos diferentes o más específicos
- Prueba una herramienta DIFERENTE (ej: si `structural_query` devuelve vacío, usa `smart_search`)
- Si buscas un artículo específico de una ley y no aparece, busca por el nombre completo de la ley
- Si ninguna búsqueda funciona, usa `web_search` como último recurso

### Paso 4: PROFUNDIZAR si es necesario
- Si el usuario pide análisis → usa `analyze_domain` con el contexto ya recopilado
- Si necesitas el texto completo de un documento → usa `get_document_content`
- Si quieres contrastar con legislación → combina resultados de varias herramientas

### Paso 5: RESPONDER
Solo usa `terminate` cuando tengas información RELEVANTE y VERIFICADA.
NO respondas con resultados que no corresponden a lo que se preguntó.

## Reglas OBLIGATORIAS
- Si los resultados de una búsqueda no son relevantes: LLAMA a otra herramienta directamente. NUNCA respondas sugiriendo al usuario que busque él mismo.
- NUNCA escribas una tool call como texto o JSON en tu respuesta. Si quieres usar una herramienta, ÚSALA con function calling.
- Si buscaste legislación y los resultados son de OTRA ley (no la que se pidió), busca de nuevo con el nombre COMPLETO de la ley (ej: "Real Decreto Legislativo 2/2015 Estatuto de los Trabajadores artículo 54").
- SIEMPRE cita las fuentes de tu información
- Distingue entre CONTENEDORES (carpetas/expedientes) y DOCUMENTOS (archivos)
- Si piden MOSTRAR un documento: búscalo y léelo, NUNCA lo inventes
- Si piden GENERAR un documento: créalo con [PLACEHOLDER] para datos faltantes
- Si no encuentras información relevante tras 3+ intentos, dilo honestamente
- Responde en el mismo idioma que el usuario
- Sé DIRECTO y CONCISO
- NUNCA respondas con información de una ley diferente a la que se preguntó
"""


async def _build_system_message(state: ReActState) -> SystemMessage:
    """Build the system message with tools description and sector context."""
    registry = get_tool_registry()
    tools_desc = registry.get_tools_description(
        tenant_id=state.get("tenant_id", ""),
        sector=state.get("sector"),
        features=state.get("features"),
        max_desc_chars=settings.react_tool_description_max_chars,
    )

    prompt = await _load_react_system_prompt()
    prompt = prompt.replace("{tools_description}", tools_desc)

    sector = state.get("sector", "")
    if sector:
        prompt += f"\n\nSector activo: {sector}"

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

    return SystemMessage(content=prompt)


def _build_tool_context(state: ReActState) -> Dict[str, Any]:
    """Build minimal context dict for tool execution (avoids copying full state)."""
    return {
        "tenant_id": state.get("tenant_id", ""),
        "user_id": state.get("user_id"),
        "user_role_ids": state.get("user_role_ids"),
        "is_admin": state.get("is_admin", False),
        "sector": state.get("sector"),
        "features": state.get("features"),
        "query": state.get("query", ""),
        "thread_id": state.get("thread_id", ""),
        "metadata": state.get("metadata"),
    }


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
            tenant_id=state.get("tenant_id", ""),
            sector=state.get("sector"),
            features=state.get("features"),
        )
        tool_schemas = [t.to_openai_param() for t in tools]

    # Build messages for LLM
    # On first step: prepend system message
    # On subsequent steps: messages already contain system + history + tool results
    existing_messages = list(state.get("messages", []))

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

    # Sliding window: keep system messages + last N messages to avoid context overflow.
    # Walk the cut boundary to avoid orphaning tool_call/result pairs.
    max_history = settings.react_max_history_messages
    if len(llm_messages) > max_history:
        # Preserve system messages at the start
        system_msgs = [m for m in llm_messages if m.get("role") == "system"]
        non_system = [m for m in llm_messages if m.get("role") != "system"]

        if len(non_system) > max_history:
            cut = len(non_system) - max_history
            # Walk cut backward past any orphaned tool messages at the boundary
            while cut > 0 and non_system[cut].get("role") == "tool":
                cut -= 1
            non_system = non_system[cut:]

        llm_messages = system_msgs + non_system
        logger.debug(f"Trimmed message history to {len(llm_messages)} messages (max_history={max_history})")

    # Call LLM with tools
    try:
        from app.agents.llm_router import get_llm_router
        router = await get_llm_router()
        response = await router.chat(
            messages=llm_messages,
            tools=tool_schemas if tool_schemas else None,
            max_tokens=settings.react_max_completion_tokens,
        )
    except Exception as e:
        logger.error(f"ReAct loop: LLM call failed at step {step}: {e}")
        return {
            "is_complete": True,
            "current_step": step + 1,
            "success": False,
            "final_answer": f"Lo siento, hubo un error procesando tu consulta: {e}",
            "reasoning_steps": [{
                "type": StepType.ERROR.value,
                "content": f"LLM error at step {step}: {e}",
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

    # Also capture explicit thinking from LLMResponse
    if response.thinking and response.thinking != thinking:
        reasoning_steps.append({
            "type": StepType.THINKING.value,
            "content": response.thinking[:500],
        })

    latency_ms = (time.time() - start) * 1000

    # ─── No tool calls → agent wants to respond directly ───
    if not response.has_tool_calls:
        intent = (state.get("metadata") or {}).get("classify_intent", "")
        if step == 0 and intent in ("document_query", "legal_query", "analysis"):
            # SILENT FAILURE: LLM skipped tool calling on first step for a query
            # that should have triggered a search. Log as warning for observability.
            logger.warning(
                f"⚠️ ReAct step 0 — NO tool calls for intent '{intent}'. "
                f"LLM responded directly without searching. "
                f"Query: '{state.get('query', '')[:80]}'"
            )
        else:
            logger.info(f"ReAct loop: step {step} — no tool calls, completing")

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
    # Build AIMessage with tool_calls for the message history
    ai_tool_calls = [
        {
            "id": tc.id,
            "name": tc.name,
            "args": tc.arguments,
        }
        for tc in response.tool_calls
    ]
    ai_message = AIMessage(
        content=content,
        tool_calls=ai_tool_calls,
    )

    new_messages = [ai_message]
    new_sources: List[Dict[str, Any]] = []

    # Separate terminate from non-terminate tool calls
    terminate_tc = None
    regular_tcs = []
    for tc in response.tool_calls:
        reasoning_steps.append({
            "type": StepType.TOOL_CALL.value,
            "content": f"{tc.name}({_summarize_args(tc.arguments)})",
        })
        # Track for stuck detection
        tool_calls_history.append({
            "name": tc.name,
            "args": tc.arguments,
            "step": step,
        })

        if tc.name == "terminate":
            terminate_tc = tc
        else:
            regular_tcs.append(tc)

    tool_context = _build_tool_context(state)
    registry = get_tool_registry()

    # If terminate found, execute it and return immediately
    if terminate_tc:
        answer = terminate_tc.arguments.get("answer", "")

        result = await registry.execute(terminate_tc.name, terminate_tc.arguments, context=tool_context)

        new_messages.append(ToolMessage(
            content=result.output,
            tool_call_id=terminate_tc.id,
        ))

        reasoning_steps.append({
            "type": StepType.RESPONSE.value,
            "content": "Terminate: agent produced final answer",
        })

        # Prefer tool-accumulated sources (from state) over LLM-constructed ones.
        # The LLM often misattributes metadata (e.g., assigns boe_id from legislation
        # to tenant documents). Tool results have correct source_type/boe_id.
        accumulated_sources = state.get("sources", [])
        terminate_sources = terminate_tc.arguments.get("sources", []) or result.sources
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
        return tc, await registry.execute(tc.name, tc.arguments, context=tool_context)

    results = await asyncio.gather(*[_run_tool(tc) for tc in regular_tcs])

    # Process results in order
    for tc, result in results:
        # Truncate large observations (OpenManus max_observe pattern)
        observation = result.output
        max_observe = settings.react_max_observe_length
        if len(observation) > max_observe:
            observation = observation[:max_observe] + "\n[... truncado]"

        new_messages.append(ToolMessage(
            content=observation,
            tool_call_id=tc.id,
        ))

        # Collect sources
        if result.sources:
            new_sources.extend(result.sources)

        reasoning_steps.append({
            "type": StepType.OBSERVATION.value,
            "content": observation[:300],
            "source": tc.name,
        })

    # Return updated state — is_complete=False triggers another react_loop iteration
    return {
        "messages": new_messages,
        "current_step": step + 1,
        "is_complete": False,
        "tool_calls_history": tool_calls_history,
        "sources": new_sources,
        "reasoning_steps": reasoning_steps,
        "metadata": {
            f"react_step_{step}_latency_ms": latency_ms,
            "_tool_schemas_cache": tool_schemas,
            "_system_message_cache": cached_sys_content,
        },
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
