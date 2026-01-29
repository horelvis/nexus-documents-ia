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

from ...state import RAGState, AgentResult

logger = logging.getLogger(__name__)

# Explicit thinking tag patterns (Qwen3, DeepSeek R1, etc.)
# These are the most reliable - models output thinking in these tags
THINKING_TAG_PATTERNS = [
    re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<thinking>(.*?)</thinking>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<pensamiento>(.*?)</pensamiento>", re.IGNORECASE | re.DOTALL),
]


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

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""Query: {query}

Context from retrieved documents:
{context}

Please analyze and respond using your specialized knowledge and tools."""},
        ]

        # Get LLM client
        from app.agents.llm_client import get_llm_client

        llm_client = await get_llm_client()

        # Convert tools to OpenAI format
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

                response = await llm_client.chat(
                    messages=messages,
                    tools=tool_schemas,
                    temperature=0.3,
                    max_tokens=2048,
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
        # Note: AgentResult is a TypedDict, access as dict not object
        result_dict = {
            "agent": agent_name,
            "output": response.content if response else "",
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


def _build_context(docs: List[Dict], max_chars: int = 8000) -> str:
    """Build context string from retrieved documents."""
    if not docs:
        return "No documents retrieved."

    context_parts = []
    total_chars = 0

    for i, doc in enumerate(docs):
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
    """Extract source references from documents."""
    sources = []
    for doc in docs[:5]:  # Max 5 sources
        doc_id = doc.get("id", "")
        title = doc.get("title", "")
        if doc_id or title:
            sources.append(f"{title} ({doc_id[:8]}...)" if doc_id else title)
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
