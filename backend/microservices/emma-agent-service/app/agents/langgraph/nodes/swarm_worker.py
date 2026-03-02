"""
Emma Swarm Agent — Worker Node

Each swarm worker is a focused mini-ReAct loop that handles one sub-task
from the decomposition. Workers execute in parallel via LangGraph's Send() API.

Key differences from react_loop_node:
- Focused tools: Only the tools assigned in swarm_current_task.tool_names + terminate
- Fewer iterations: max_steps = 2-3 (vs 10 for full react_loop)
- Own message history: Builds fresh system+user messages per sub-task
- Simpler system prompt: Focused on the sub-task, not the full agent persona
- Results accumulate via swarm_worker_results (merge_lists reducer)

The worker follows the same Think-Act-Observe pattern as react_loop
but is scoped to a single independent research task.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.langfuse_config import observe
from ..state import ReActState
from ..reasoning_tracker import StepType
from ..tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


def _parse_thinking(content: str) -> tuple:
    """Extract thinking tags from LLM response."""
    patterns = [
        (r"<think>(.*?)</think>", re.DOTALL),
        (r"<thinking>(.*?)</thinking>", re.DOTALL),
    ]
    for pattern, flags in patterns:
        match = re.search(pattern, content, flags)
        if match:
            thinking = match.group(1).strip()
            remaining = re.sub(pattern, "", content, flags=flags).strip()
            return thinking, remaining
    return None, content


def _summarize_args(args: Dict[str, Any], max_length: int = 80) -> str:
    """Create a short summary of tool arguments for logging."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 40:
            v_str = v_str[:37] + "..."
        parts.append(f"{k}={v_str}")
    result = ", ".join(parts)
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    return result


@observe(as_type="span", name="swarm_worker_node")
async def swarm_worker_node(state: ReActState) -> Dict[str, Any]:
    """Execute a focused mini-ReAct loop for one sub-task.

    Each worker:
    1. Gets its assigned sub-task from swarm_current_task
    2. Filters tools to only those assigned + terminate
    3. Runs a mini-ReAct loop (max_steps iterations)
    4. Returns results via swarm_worker_results reducer

    If the worker fails (timeout, tool error), it returns success=False.
    Other workers continue independently.

    Returns:
        State updates: swarm_worker_results, sources, reasoning_steps,
        swarm_pending_events
    """
    start = time.time()
    task = state.get("swarm_current_task")
    worker_id = state.get("swarm_worker_id", 0)
    query = state.get("query", "")

    if not task:
        logger.error(f"Swarm worker {worker_id}: no task assigned")
        return {
            "swarm_worker_results": [{
                "worker_id": worker_id,
                "sub_task": "unknown",
                "focus": "error",
                "answer": "",
                "sources": [],
                "success": False,
                "error": "No task assigned",
                "latency_ms": 0,
            }],
        }

    task_description = task.get("description", "")
    task_tool_names = set(task.get("tool_names", []))
    task_focus = task.get("focus", "general")
    max_steps = task.get("max_steps", settings.swarm_worker_max_steps)

    logger.info(f"Swarm worker {worker_id}: starting '{task_description[:80]}' "
                f"(tools: {task_tool_names}, max_steps: {max_steps})")

    # Emit worker_started SSE event
    pending_events = [{
        "type": "worker_started",
        "data": {
            "worker_id": worker_id,
            "sub_task": task_description[:200],
            "tools": list(task_tool_names),
        },
    }]

    # Filter tools to task's assigned tools + terminate
    registry = get_tool_registry()
    all_tools = registry.get_tools_for_context(
        tenant_id=state.get("tenant_id", ""),
        sector=state.get("sector"),
        features=state.get("features"),
    )
    worker_tools = [
        t for t in all_tools
        if t.name in task_tool_names or t.name == "terminate"
    ]

    if not worker_tools:
        logger.warning(f"Swarm worker {worker_id}: no matching tools found")
        return _worker_failure(worker_id, task, "No matching tools available", start, pending_events)

    tool_schemas = [t.to_openai_param() for t in worker_tools]
    tools_desc = ", ".join(t.name for t in worker_tools if t.name != "terminate")

    # Build focused system prompt
    system_content = (
        f"Eres un agente especializado. Tu tarea: {task_description}\n\n"
        f"Herramientas: {tools_desc}\n\n"
        f"Reglas:\n"
        f"- Usa SOLO las herramientas proporcionadas\n"
        f"- Sé conciso y directo\n"
        f"- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
        f"- Cita las fuentes encontradas\n"
        f"- Responde en el mismo idioma que el usuario"
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": query},
    ]

    # Tool execution context
    tool_context = {
        "tenant_id": state.get("tenant_id", ""),
        "user_id": state.get("user_id"),
        "user_role_ids": state.get("user_role_ids"),
        "is_admin": state.get("is_admin", False),
        "sector": state.get("sector"),
        "features": state.get("features"),
        "query": query,
        "thread_id": state.get("thread_id", ""),
        "metadata": state.get("metadata"),
    }

    reasoning_steps: List[Dict[str, Any]] = []
    collected_sources: List[Dict[str, Any]] = []
    answer = ""

    # Mini-ReAct loop
    try:
        for step in range(max_steps):
            # LLM call with focused tools
            from app.agents.llm_router import get_llm_router
            router = await get_llm_router()

            response = await asyncio.wait_for(
                router.chat(
                    messages=messages,
                    tools=tool_schemas,
                    max_tokens=settings.react_max_completion_tokens,
                ),
                timeout=settings.swarm_worker_timeout_seconds,
            )

            content = response.content or ""

            # Extract thinking
            thinking, content = _parse_thinking(content)
            if thinking:
                reasoning_steps.append({
                    "type": StepType.THINKING.value,
                    "content": f"[Worker {worker_id}] {thinking[:300]}",
                })

            # No tool calls → agent wants to respond directly
            if not response.has_tool_calls:
                content = re.sub(r"</?tool_call>", "", content).strip()
                answer = content
                break

            # Process tool calls
            terminate_found = False

            for tc in response.tool_calls:
                reasoning_steps.append({
                    "type": StepType.TOOL_CALL.value,
                    "content": f"[Worker {worker_id}] {tc.name}({_summarize_args(tc.arguments)})",
                })

                if tc.name == "terminate":
                    answer = tc.arguments.get("answer", "")
                    sources = tc.arguments.get("sources", [])
                    if sources:
                        collected_sources.extend(sources)
                    terminate_found = True

                    # Execute terminate for proper message format
                    result = await registry.execute(tc.name, tc.arguments, context=tool_context)
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [{
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.output,
                    })
                    break

            if terminate_found:
                break

            # Execute non-terminate tools in parallel
            regular_tcs = [tc for tc in response.tool_calls if tc.name != "terminate"]
            if regular_tcs:
                # Build AI message with tool calls
                ai_tool_calls = [{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                } for tc in regular_tcs]

                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": ai_tool_calls,
                })

                async def _run_tool(tc):
                    return tc, await registry.execute(tc.name, tc.arguments, context=tool_context)

                results = await asyncio.gather(
                    *[_run_tool(tc) for tc in regular_tcs],
                    return_exceptions=True,
                )

                for item in results:
                    if isinstance(item, Exception):
                        logger.warning(f"Swarm worker {worker_id}: tool error: {item}")
                        continue

                    tc, result = item
                    observation = result.output
                    max_observe = settings.react_max_observe_length
                    if len(observation) > max_observe:
                        observation = observation[:max_observe] + "\n[... truncado]"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": observation,
                    })

                    if result.sources:
                        collected_sources.extend(result.sources)

                    reasoning_steps.append({
                        "type": StepType.OBSERVATION.value,
                        "content": f"[Worker {worker_id}] {observation[:200]}",
                        "source": tc.name,
                    })

    except asyncio.TimeoutError:
        logger.warning(f"Swarm worker {worker_id}: timed out after {settings.swarm_worker_timeout_seconds}s")
        return _worker_failure(
            worker_id, task,
            f"Timeout after {settings.swarm_worker_timeout_seconds}s",
            start, pending_events, reasoning_steps,
        )
    except Exception as e:
        logger.error(f"Swarm worker {worker_id}: error: {e}", exc_info=True)
        return _worker_failure(
            worker_id, task, str(e), start, pending_events, reasoning_steps,
        )

    latency_ms = (time.time() - start) * 1000

    # If no answer was produced via terminate, use last content
    if not answer:
        # Try to extract from last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                answer = msg["content"]
                break

    logger.info(
        f"Swarm worker {worker_id}: completed in {latency_ms:.0f}ms, "
        f"answer_len={len(answer)}, sources={len(collected_sources)}"
    )

    # Emit worker_complete SSE event
    pending_events.append({
        "type": "worker_complete",
        "data": {
            "worker_id": worker_id,
            "preview": answer[:200] if answer else "",
            "sources_count": len(collected_sources),
            "latency_ms": latency_ms,
        },
    })

    worker_result = {
        "worker_id": worker_id,
        "sub_task": task_description,
        "focus": task_focus,
        "answer": answer,
        "sources": collected_sources,
        "success": True,
        "latency_ms": latency_ms,
    }

    return {
        "swarm_worker_results": [worker_result],
        # NOTE: sources are NOT written here to avoid INVALID_CONCURRENT_GRAPH_UPDATE
        # when multiple workers complete in the same step. Sources are stored
        # inside swarm_worker_results and extracted by synthesize_swarm_node.
        "reasoning_steps": reasoning_steps,
        "swarm_pending_events": pending_events,
    }


def _worker_failure(
    worker_id: int,
    task: Dict[str, Any],
    error: str,
    start_time: float,
    pending_events: List[Dict[str, Any]],
    reasoning_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a failure result for a worker."""
    latency_ms = (time.time() - start_time) * 1000

    pending_events.append({
        "type": "worker_complete",
        "data": {
            "worker_id": worker_id,
            "preview": f"Error: {error}",
            "sources_count": 0,
            "latency_ms": latency_ms,
            "error": True,
        },
    })

    return {
        "swarm_worker_results": [{
            "worker_id": worker_id,
            "sub_task": task.get("description", "unknown"),
            "focus": task.get("focus", "error"),
            "answer": "",
            "sources": [],
            "success": False,
            "error": error,
            "latency_ms": latency_ms,
        }],
        "reasoning_steps": (reasoning_steps or []) + [{
            "type": StepType.ERROR.value,
            "content": f"[Worker {worker_id}] Failed: {error}",
        }],
        "swarm_pending_events": pending_events,
    }
