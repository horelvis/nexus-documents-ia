"""
Base Specialist Agent Node

Factory for creating specialist agent nodes with:
- Domain-specific system prompts
- Domain-specific tools
- Consistent error handling
- Result tracking in state
- **Interleaved Thinking**: Reasoning between tool calls (like Claude Extended Thinking)

Design Decisions:
1. Use existing LLMClient for consistency
2. Tools are LangChain-compatible (can use with create_react_agent)
3. Each agent operates on retrieved_docs context
4. Results stored in agent_results dict
5. Interleaved thinking captures: THINKING → TOOL_CALL → OBSERVATION → REFLECTION

Interleaved Thinking Pattern:
┌─────────────────────────────────────────────────────────────────────────────┐
│  For each LLM iteration:                                                     │
│  1. THINKING - Extract reasoning from LLM response content                   │
│  2. TOOL_CALL - Capture decision to use specific tool                        │
│  3. TOOL_EXECUTION - Run the tool                                            │
│  4. OBSERVATION - What the LLM sees (tool result summary)                    │
│  5. REFLECTION - LLM reasons about results before next action                │
└─────────────────────────────────────────────────────────────────────────────┘
"""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from pathlib import Path

from ...state import RAGState, AgentResult

logger = logging.getLogger(__name__)

# ─── Sector prompt loader (cached) ───────────────────────────────────────────
_SECTOR_PROMPTS_CACHE: Optional[Dict[str, Any]] = None


def _load_sector_prompts() -> Dict[str, Any]:
    """Load sector prompts from emma_prompts.yaml (cached)."""
    global _SECTOR_PROMPTS_CACHE
    if _SECTOR_PROMPTS_CACHE is not None:
        return _SECTOR_PROMPTS_CACHE

    # specialists/ → nodes/ → langgraph/ → agents/ → app/ → emma-agent-service/
    candidates = [
        Path("/app/config/prompts/emma_prompts.yaml"),
        Path(__file__).parent.parent.parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
    ]
    for p in candidates:
        if p.exists():
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _SECTOR_PROMPTS_CACHE = data.get("sectors", {})
                return _SECTOR_PROMPTS_CACHE
            except Exception as e:
                logger.warning(f"Failed to load sector prompts: {e}")

    _SECTOR_PROMPTS_CACHE = {}
    return _SECTOR_PROMPTS_CACHE


def _get_sector_system_prompt(state: RAGState) -> str:
    """Get the sector system prompt from state's sector_config, if available."""
    sector_config = state.get("sector_config")
    if not sector_config:
        return ""

    # system_prompt_key is like "sectors.legal" → extract "legal"
    prompt_key = sector_config.get("system_prompt_key", "")
    if not prompt_key:
        return ""

    sector_key = prompt_key.replace("sectors.", "")
    prompts = _load_sector_prompts()
    return prompts.get(sector_key, {}).get("system_prompt", "")

# Explicit thinking tag patterns (Qwen3, DeepSeek R1, etc.)
# These are the most reliable - models output thinking in these tags
THINKING_TAG_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<thinking>(.*?)</thinking>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<pensamiento>(.*?)</pensamiento>", re.IGNORECASE | re.DOTALL),
]

# Raw tool_call tags emitted by small/custom models as plain text (not structured).
_RAW_TOOL_CALL_WITH_CLOSING = re.compile(
    r"<tool_call>.*?</tool_call>", re.IGNORECASE | re.DOTALL,
)


def _strip_raw_tool_calls(content: str) -> str:
    """Remove raw <tool_call> tags that small/custom models emit as plain text.

    Some models output tool calls as ``<tool_call>{"name":...}`` inside the
    content field instead of using the structured tool_calls mechanism.
    These must be stripped so they don't leak into the final answer.

    Strategy:
    1. Strip ``<tool_call>...</tool_call>`` pairs (with closing tag).
    2. Strip ``<tool_call>`` followed by a JSON block (balanced braces) without closing tag.
    3. Remove any leftover bare ``<tool_call>`` or ``</tool_call>`` tags.
    """
    if not content or "tool_call" not in content.lower():
        return content

    cleaned = content

    # Pass 1: with closing tags
    cleaned = _RAW_TOOL_CALL_WITH_CLOSING.sub("", cleaned)

    # Pass 2: without closing tag — find <tool_call> and consume until matching }
    while True:
        idx = cleaned.lower().find("<tool_call>")
        if idx == -1:
            break
        # Find the start of JSON after the tag
        tag_end = idx + len("<tool_call>")
        rest = cleaned[tag_end:]
        json_start = rest.find("{")
        if json_start == -1:
            # No JSON — just remove the bare tag
            cleaned = cleaned[:idx] + rest
            continue
        # Walk through and find the balanced closing brace
        depth = 0
        end_pos = -1
        for i, ch in enumerate(rest[json_start:]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = json_start + i + 1
                    break
        if end_pos == -1:
            # Unbalanced — consume to end of line
            nl = rest.find("\n", json_start)
            end_pos = nl if nl != -1 else len(rest)
        cleaned = cleaned[:idx] + rest[end_pos:]

    # Pass 3: leftover bare tags
    cleaned = re.sub(r"</?tool_call>", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    if cleaned != content.strip():
        logger.warning(
            f"🧹 Stripped raw <tool_call> tags from output "
            f"({len(content)} → {len(cleaned)} chars)"
        )
    return cleaned


def _extract_thinking(content: str) -> Tuple[str, str]:
    """
    Extract thinking content from LLM response.

    Strategy:
    1. Look for explicit <think> tags (most reliable, used by Qwen3)
    2. If no tags, extract first sentence only as brief planning hint
       (avoids duplications from phrase matching)

    Returns:
        Tuple of (thinking_content, remaining_content)
    """
    if not content:
        return "", ""

    thinking_parts = []
    remaining = content

    # Try explicit think tags first (most reliable)
    for pattern in THINKING_TAG_PATTERNS:
        matches = pattern.findall(remaining)
        for match in matches:
            thinking_parts.append(match.strip())
            remaining = pattern.sub("", remaining).strip()

    # If we found explicit tags, return them
    if thinking_parts:
        return " ".join(thinking_parts).strip(), remaining

    # Fallback: Extract first sentence only (simple and avoids duplications)
    # Only if it starts with a planning indicator word
    first_sentence_match = re.match(
        r"^((?:Voy a|Necesito|Primero|Déjame|Permíteme|Para)[^.!?]{10,150}[.!?])",
        content.strip(),
        re.IGNORECASE
    )
    if first_sentence_match:
        thinking = first_sentence_match.group(1).strip()
        remaining = content[first_sentence_match.end():].strip()
        return thinking, remaining

    return "", content.strip()


def _summarize_tool_result(result: str, max_length: int = 150) -> str:
    """Summarize a tool result for the observation step."""
    if len(result) <= max_length:
        return result
    return result[:max_length] + "..."


def _truncate_repetitions(content: str, max_repeats: int = 2) -> str:
    """
    Detect and truncate repetitive content from small LLM generation loops.

    Splits content into sentences and removes sequences where the same
    sentence appears more than max_repeats times consecutively.
    """
    if not content or len(content) < 200:
        return content

    # Split into sentences (preserve numbered list items as units)
    sentences = re.split(r'(?<=[.!?\n])\s+(?=\S)', content)
    if len(sentences) < 4:
        return content

    result = []
    repeat_count = 0
    prev_normalized = ""

    for sentence in sentences:
        # Normalize for comparison (strip numbers, whitespace)
        normalized = re.sub(r'^\d+[\.\)]\s*', '', sentence.strip()).lower().strip()
        if not normalized:
            result.append(sentence)
            continue

        if normalized == prev_normalized:
            repeat_count += 1
            if repeat_count >= max_repeats:
                # Stop: we hit a loop
                logger.warning(
                    f"🔁 Repetition detected after {len(result)} sentences, truncating"
                )
                break
        else:
            repeat_count = 0

        prev_normalized = normalized
        result.append(sentence)

    truncated = " ".join(result)
    if len(truncated) < len(content):
        truncated = truncated.rstrip() + "\n\n*[Respuesta truncada por repetición]*"
    return truncated


async def create_specialist_node(
    agent_name: str,
    system_prompt: str,
    tools: List[BaseTool],
    state: RAGState,
) -> Dict[str, Any]:
    """
    Factory function to create specialist agent execution.

    This runs a specialist agent with:
    1. Domain-specific system prompt
    2. Domain-specific tools
    3. Context from retrieved documents
    4. Query from state

    Args:
        agent_name: Name of the agent (e.g., "labor_agent")
        system_prompt: Domain-specific system prompt
        tools: List of LangChain tools available to this agent
        state: Current RAG state

    Returns:
        State updates with agent results
    """
    start_time = time.time()
    query = state.get("query", "")
    retrieved_docs = state.get("retrieved_docs", [])
    current_index = state.get("current_agent_index", 0)

    # Render dynamic prompt via Jinja2 engine (handles sector injection + templates)
    from ...prompt_engine import get_prompt_engine
    engine = get_prompt_engine()
    system_prompt = engine.render_agent_prompt(agent_name, system_prompt, state)

    logger.info(f"🤖 {agent_name}: Starting execution")

    # Initialize dynamic reasoning tracker for this agent execution
    from ...reasoning_tracker import ReasoningTracker

    try:
        # Build context from retrieved documents + tree summary
        context = _build_context(retrieved_docs)
        tree_context = state.get("metadata", {}).get("context_tree_summary")
        if tree_context:
            context = (
                "Contexto de estructura del repositorio:\n"
                f"{tree_context}\n\n"
                "Contexto de documentos recuperados:\n"
                f"{context}"
            )
        metadata = state.get("metadata", {})
        doc_id = metadata.get("document_id")
        indexed_doc_ids = metadata.get("indexed_document_ids") or []
        attachment_summary = metadata.get("attachment_summary")
        uploaded_texts = metadata.get("uploaded_texts") or []
        if doc_id or indexed_doc_ids or attachment_summary or uploaded_texts:
            selected_block = []
            if doc_id:
                selected_block.append(f"- document_id: {doc_id}")
            if indexed_doc_ids:
                selected_block.append(f"- indexed_document_ids: {', '.join(indexed_doc_ids)}")
            if attachment_summary:
                selected_block.append(f"- attachment_summary: {attachment_summary}")
            if uploaded_texts:
                for item in uploaded_texts:
                    filename = item.get("filename") or "documento_subido"
                    text = item.get("text", "")
                    selected_block.append(f"- uploaded_file: {filename}\n{text}")
            context = (
                "Documentos seleccionados en el contexto de la consulta:\n"
                + "\n".join(selected_block)
                + "\n\n"
                + context
            )

        # Build messages — docgen agents get a different context framing
        is_docgen = agent_name == "docgen_agent"

        if is_docgen:
            # For docgen, build a template-focused context:
            # Give more space to the best-matching document so the model
            # can see its full structure, not just scattered chunks.
            docgen_context = _build_docgen_context(retrieved_docs)

            user_content = f"""Query: {query}

{docgen_context}

INSTRUCCIONES CRÍTICAS PARA GENERACIÓN:
1. Si hay un DOCUMENTO PLANTILLA arriba, COPIA su formato exacto: mismos encabezados, misma numeración de cláusulas, mismo estilo de redacción, misma estructura de firmas.
2. ADAPTA el contenido de la plantilla al tipo de documento solicitado, manteniendo el estilo del cliente.
3. Si hay documentos de referencia adicionales, úsalos para cláusulas complementarias.
4. Si NO hay plantilla del mismo tipo, genera con formato jurídico estándar español.
5. Marca datos no proporcionados como: [NOMBRE COMPLETO], [NIF], [DOMICILIO], [FECHA], [IMPORTE], etc.
6. Fundamenta cada cláusula con legislación vigente (artículos, leyes, BOE).
7. Al final incluye sección CAMPOS PENDIENTES DE COMPLETAR."""
        else:
            # Detect if we have NO relevant documents to avoid hallucination
            # EXCEPTION: social_agent has web_search for external info, don't disable tool use
            is_social_agent = agent_name == "social_agent"
            no_relevant_docs = (
                not context or
                "No documents retrieved" in context or
                "No documents with sufficient relevance" in context or
                "No hay documentos" in context
            )

            if is_social_agent:
                # SOCIAL AGENT: Designed for conversational channels (Slack, Telegram, WhatsApp)
                # Proactive web context may have been injected by social_node
                location_info = metadata.get("location", {})
                location_str = f"{location_info.get('city', 'España')}, {location_info.get('country', 'España')}" if location_info else "España"
                proactive_context = metadata.get("proactive_web_context", "")

                if proactive_context:
                    # We have proactive web search results - use them!
                    user_content = f"""Query: {query}

CONTEXTO:
- Ubicación del usuario: {location_str}
- Canal: social (Slack/Telegram/WhatsApp)
{proactive_context}

INSTRUCCIONES:
1. USA la información de web_search proporcionada arriba para responder
2. Responde de forma BREVE y CONVERSACIONAL (2-3 oraciones máximo)
3. Usa emojis con moderación (1-2 por mensaje)
4. NO digas que no tienes acceso a información - ¡ya la tienes arriba!
5. Si la información de búsqueda no es relevante, responde conversacionalmente"""
                else:
                    # No proactive context - normal flow (encourage tools)
                    user_content = f"""Query: {query}

CONTEXTO:
- Ubicación del usuario: {location_str}
- Canal: social (Slack/Telegram/WhatsApp)

INSTRUCCIONES CRÍTICAS:
1. Si la pregunta es sobre CLIMA, TIEMPO, NOTICIAS, EVENTOS, PRECIOS → USA `web_search` OBLIGATORIO
2. Si la pregunta es sobre DOCUMENTOS del usuario → USA `quick_document_search`
3. Responde de forma BREVE y CONVERSACIONAL (2-3 oraciones máximo)
4. Usa emojis con moderación (1-2 por mensaje)
5. NUNCA digas "no tengo acceso" si tienes una herramienta que puede ayudar

RECUERDA: Tienes herramientas `web_search` y `quick_document_search`. ¡ÚSALAS!"""
            elif no_relevant_docs:
                # CRITICAL: Do NOT encourage LLM to use "its own knowledge" - this causes hallucinations
                user_content = f"""Query: {query}

IMPORTANTE: No se encontraron documentos relevantes en el repositorio del usuario para responder esta consulta.

Tu respuesta DEBE:
1. Indicar claramente que no encontraste información relevante en los documentos del usuario
2. NO inventar leyes, artículos, BOE, normativas o información legal específica
3. Sugerir al usuario que suba documentos relacionados o reformule su pregunta
4. Si puedes dar información GENERAL sobre el tema (sin citar fuentes específicas), indicar claramente que es información general y NO verificada con sus documentos

Responde de forma honesta sobre la falta de documentos relevantes."""
            else:
                user_content = f"""Query: {query}

Context from retrieved documents:
{context}

INSTRUCCIONES:
1. Responde basándote en los documentos proporcionados.
2. NO inventes leyes, artículos o BOE que no aparezcan en los documentos.
3. Si los documentos NO son relevantes para la consulta, indica que no encontraste información relevante."""

        # Inject action-specific instructions from YAML if available
        # This provides additional context for specific actions like "retrieve"
        action_intent = state.get("metadata", {}).get("action_intent", "")
        if action_intent and action_intent != "generate" and not is_docgen:
            action_instruction = engine.get_action_instruction(action_intent, state)
            if action_instruction:
                user_content = action_instruction + "\n\n" + user_content
                logger.info(f"📋 {agent_name}: Injected action instruction for '{action_intent}'")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Get LLM client and config
        from app.agents.llm_client import get_llm_client
        from app.core.config import Settings

        settings = Settings()
        llm_client = await get_llm_client()

        # Convert tools to OpenAI format.
        # Disable tools ONLY for generate actions — the model should produce the
        # document directly using the retrieved docs as context, not call tools.
        # For all other intents (retrieve, search, analyze), let the LLM reason
        # naturally about which tools to use based on the system prompt.
        # Note: action_intent is already defined above for action instruction injection
        if action_intent == "generate":
            tool_schemas = None
            logger.info(f"🔇 {agent_name}: Tools disabled for action=generate")
        else:
            tool_schemas = [_tool_to_openai_schema(tool) for tool in tools] if tools else None

        # Execute with tools using dynamic reasoning tracker and interleaved thinking
        tools_used = []
        max_iterations = 5
        import json
        from ...reasoning_tracker import StepType

        # Create a tracker context for this agent - tools will auto-register steps
        with ReasoningTracker.create() as tracker:
            tracker.set_source(agent_name)

            for iteration in range(max_iterations):
                iteration_start = time.time()

                # Docgen needs more output tokens for full documents
                effective_max_tokens = (
                    min(settings.agent_max_tokens * 3, 6144)
                    if is_docgen
                    else settings.agent_max_tokens
                )

                response = await llm_client.chat(
                    messages=messages,
                    tools=tool_schemas,
                    temperature=settings.agent_temperature,
                    max_tokens=effective_max_tokens,
                )

                # =========================================================
                # INTERLEAVED THINKING: Extract thinking from response
                # =========================================================
                if response.content:
                    thinking, _ = _extract_thinking(response.content)
                    if thinking:
                        tracker.add_thinking_step(
                            thinking,
                            confidence=0.9,
                        )
                        logger.debug(f"💭 {agent_name}: Thinking extracted: {thinking[:80]}...")

                if not response.has_tool_calls:
                    # Agent finished - add final response step
                    if response.content and iteration > 0:
                        # If we had tool calls before, this is a reflection on results
                        tracker.add_step(
                            StepType.RESPONSE,
                            f"Respuesta generada tras {iteration} iteración(es)"
                        )
                    break

                # =========================================================
                # INTERLEAVED THINKING: Process each tool call
                # =========================================================
                for tool_call in response.tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments

                    # Step 1: TOOL_CALL - Record the decision to use this tool
                    args_summary = ", ".join(
                        f"{k}={str(v)[:30]}" for k, v in (tool_args.items() if isinstance(tool_args, dict) else [])
                    )[:100]
                    tracker.add_tool_call_step(
                        tool_name=tool_name,
                        reason=f"Ejecutando con args: {args_summary}" if args_summary else "Sin argumentos",
                        arguments=tool_args if isinstance(tool_args, dict) else {},
                    )

                    # Step 2: TOOL_EXECUTION - Execute the tool
                    exec_start = time.time()
                    tool_result = await _execute_tool_call(tool_call, tools, state, tracker)
                    exec_time_ms = (time.time() - exec_start) * 1000
                    tools_used.append(tool_name)

                    # Step 3: OBSERVATION - Record what the LLM will see
                    result_summary = _summarize_tool_result(tool_result)
                    success = not tool_result.startswith("Error")
                    tracker.add_observation_step(
                        tool_name=tool_name,
                        observation=f"{result_summary} ({exec_time_ms:.0f}ms)",
                        success=success,
                    )

                    # Add assistant message with tool call
                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [{
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args) if isinstance(tool_args, dict) else tool_args,
                            }
                        }]
                    })

                    # Add tool result
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_result,
                    })

                # =========================================================
                # INTERLEAVED THINKING: Reflection after tool results
                # =========================================================
                # After processing all tool calls in this iteration,
                # the next LLM call will naturally reflect on the results.
                # We capture this in the next iteration's thinking extraction.
                iteration_time_ms = (time.time() - iteration_start) * 1000
                logger.debug(
                    f"🔄 {agent_name}: Iteration {iteration + 1} completed in {iteration_time_ms:.0f}ms, "
                    f"tools called: {[tc.name for tc in response.tool_calls]}"
                )

            # Get all dynamically registered steps
            all_reasoning_steps = tracker.get_steps()
            logger.info(
                f"📋 {agent_name}: Collected {len(all_reasoning_steps)} reasoning steps "
                f"(interleaved thinking enabled)"
            )

        latency_ms = (time.time() - start_time) * 1000

        # Build result dict with reasoning steps
        # Clean raw <tool_call> tags and truncate repetitive content
        final_output = response.content if response else ""
        if final_output:
            final_output = _strip_raw_tool_calls(final_output)
            final_output = _truncate_repetitions(final_output)

        # Note: AgentResult is a TypedDict, access as dict not object
        result_dict = {
            "agent": agent_name,
            "output": final_output,
            "tools_used": list(set(tools_used)),
            "sources": _extract_sources(retrieved_docs),
            "error": None,
            "latency_ms": latency_ms,
            "reasoning_steps": all_reasoning_steps,
        }

        logger.info(
            f"✅ {agent_name}: Completed in {latency_ms:.1f}ms, "
            f"tools={tools_used}, reasoning_steps={len(all_reasoning_steps)}"
        )

        # Update state
        agent_results = dict(state.get("agent_results", {}))
        agent_results[agent_name] = result_dict

        return {
            "agent_results": agent_results,
            "current_agent": agent_name,
            "current_agent_index": current_index + 1,
            "metadata": {
                **state.get("metadata", {}),
                f"{agent_name}_latency_ms": latency_ms,
                f"{agent_name}_reasoning_steps": all_reasoning_steps,
            },
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ {agent_name}: Failed - {e}")

        # Record error
        agent_errors = dict(state.get("agent_errors", {}))
        agent_errors[agent_name] = str(e)

        return {
            "agent_errors": agent_errors,
            "current_agent": agent_name,
            "current_agent_index": current_index + 1,
            "metadata": {
                **state.get("metadata", {}),
                f"{agent_name}_error": str(e),
                f"{agent_name}_latency_ms": latency_ms,
            },
        }


# Use environment variable for consistency with weaviate-service
import os
MIN_RELEVANCE_SCORE = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.55"))


def _build_docgen_context(docs: List[Dict], max_chars: int = 6000) -> str:
    """Build template-focused context for document generation.

    Budget: ~6000 chars (~2000 tokens) to leave room for output (~6144 tokens)
    within the 16K model window.

    Strategy: give the highest-scoring document up to 4000 chars (so the model
    sees its full structure), then append 1-2 secondary docs with the rest.
    """
    if not docs:
        return "No hay documentos de referencia del cliente."

    # Filter and sort by relevance
    filtered = [d for d in docs if d.get("score", 0.0) >= MIN_RELEVANCE_SCORE]
    if not filtered:
        return "No se encontraron documentos relevantes del cliente."

    filtered.sort(key=lambda d: d.get("score", 0.0), reverse=True)

    # Primary template: best match gets generous space
    primary = filtered[0]
    primary_budget = min(max_chars * 2 // 3, 8000)  # ~66% of budget for primary
    primary_content = primary.get("content", "")[:primary_budget]
    primary_title = primary.get("title", "Documento")
    primary_score = primary.get("score", 0.0)

    parts = [
        f"═══ DOCUMENTO PLANTILLA (mejor coincidencia, relevancia: {primary_score:.0%}) ═══",
        f"Título: {primary_title}",
        f"Contenido completo:",
        primary_content,
    ]

    # Secondary references: remaining docs with leftover budget
    remaining_budget = max_chars - len(primary_content) - 200
    if remaining_budget > 500 and len(filtered) > 1:
        parts.append("\n═══ DOCUMENTOS DE REFERENCIA ADICIONALES ═══")
        total_used = 0
        for doc in filtered[1:6]:  # max 5 secondary docs
            available = remaining_budget - total_used
            if available <= 200:
                break
            content = doc.get("content", "")[:available]
            title = doc.get("title", "Documento")
            score = doc.get("score", 0.0)
            parts.append(f"\n--- {title} (relevancia: {score:.0%}) ---")
            parts.append(content)
            total_used += len(content) + 100

    return "\n".join(parts)


def _build_context(docs: List[Dict], max_chars: int = 8000) -> str:
    """Build context string from retrieved documents, filtering low-relevance chunks."""
    if not docs:
        return "No documents retrieved."

    # Filter out low-relevance documents that add noise
    filtered_docs = []
    skipped = 0
    for doc in docs:
        score = doc.get("score", 0.0)
        if score >= MIN_RELEVANCE_SCORE:
            filtered_docs.append(doc)
        else:
            skipped += 1

    if skipped:
        logger.info(
            f"📊 Context filter: {skipped} docs below {MIN_RELEVANCE_SCORE} threshold "
            f"({len(filtered_docs)} retained)"
        )

    if not filtered_docs:
        return "No documents with sufficient relevance found."

    context_parts = []
    total_chars = 0

    for i, doc in enumerate(filtered_docs):
        title = doc.get("title", "Untitled")
        content = doc.get("content", "")
        score = doc.get("score", 0.0)

        # Truncate content if needed
        available = max_chars - total_chars - 100  # Reserve for header
        if available <= 0:
            break

        content_truncated = content[:available] if len(content) > available else content

        part = f"""--- Document {i+1}: {title} (relevance: {score:.2f}) ---
{content_truncated}
"""
        context_parts.append(part)
        total_chars += len(part)

    return "\n".join(context_parts)


def _extract_sources(docs: List[Dict]) -> List[str]:
    """Extract source references from documents, deduplicated by title."""
    sources = []
    seen_titles = set()
    for doc in docs:
        title = doc.get("title", "")
        doc_id = doc.get("id", "")
        if not title and not doc_id:
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)
        sources.append(f"{title} ({doc_id[:8]}...)" if doc_id else title)
        if len(sources) >= 5:
            break
    return sources


def _tool_to_openai_schema(tool: BaseTool) -> Dict[str, Any]:
    """Convert LangChain tool to OpenAI function schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.args_schema.schema() if tool.args_schema else {
                "type": "object",
                "properties": {},
            },
        },
    }


async def _execute_tool_call(
    tool_call: Any,
    tools: List[BaseTool],
    state: RAGState,
    tracker: Optional[Any] = None,
) -> str:
    """
    Execute a tool call and return result.

    Reasoning steps are automatically registered by tools via the
    ReasoningTracker context - no need to return them explicitly.

    Args:
        tool_call: The tool call from LLM
        tools: Available tools
        state: Current RAG state
        tracker: Optional reasoning tracker (tools can also get it via get_current())

    Returns:
        Result string to pass back to the LLM
    """
    tool_name = tool_call.name
    tool_args = tool_call.arguments

    # Find matching tool
    tool = next((t for t in tools if t.name == tool_name), None)

    if not tool:
        return f"Error: Tool '{tool_name}' not found"

    try:
        # Context (tenant_id, user_id, document_id) is now provided via
        # execution_context (contextvars) — tools call get_tenant_id_or_raise() internally.
        # No manual injection needed.

        # Execute tool - it will auto-register steps via ReasoningTracker.get_current()
        if hasattr(tool, 'ainvoke'):
            result = await tool.ainvoke(tool_args)
        elif hasattr(tool, 'invoke'):
            result = tool.invoke(tool_args)
        else:
            result = await tool._arun(**tool_args)

        # Handle dict results (e.g., structural_query returns {response, reasoning_steps})
        # The reasoning_steps are already captured by the tracker, we just need the response
        if isinstance(result, dict):
            return result.get("response", str(result))

        return str(result)

    except Exception as e:
        logger.error(f"Tool {tool_name} execution failed: {e}")
        if tracker:
            from ...reasoning_tracker import StepType
            tracker.add_step(StepType.ERROR, f"Error en {tool_name}: {str(e)}")
        return f"Error executing {tool_name}: {str(e)}"
