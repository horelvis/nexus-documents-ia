"""
Emma Swarm Agent — Worker Node (Typed SubAgents)

Each swarm worker is a focused mini-ReAct loop that handles one sub-task
from the decomposition. Workers execute in parallel via LangGraph's Send() API.

Key differences from react_loop_node:
- Typed profiles: Each focus category has a WorkerProfile with specialized
  system prompt, model role, tool set, and Langfuse prompt key
- Focused tools: Only the tools assigned in swarm_current_task.tool_names + terminate
- Fewer iterations: max_steps from profile (typically 2-3 vs 10 for full react_loop)
- Own message history: Builds fresh system+user messages per sub-task
- Results accumulate via swarm_worker_results (merge_lists reducer)

Inspired by Deep Agents SubAgentMiddleware where each subagent has
{name, description, system_prompt, tools}, but implemented natively
within LangGraph's Send() fan-out architecture.

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
from ..tools.worker_profiles import get_worker_profile

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
        State updates: swarm_worker_results, reasoning_steps.
        Worker events emitted via get_stream_writer() (not state).
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

    # Resolve typed worker profile for this focus category (sector-aware)
    profile = get_worker_profile(task_focus, sector=state.get("sector"))
    max_steps = task.get("max_steps", profile.max_steps)

    logger.info(f"Swarm worker {worker_id} [{profile.name}]: starting '{task_description[:80]}' "
                f"(tools: {task_tool_names}, role: {profile.model_role.value}, max_steps: {max_steps})")

    # Emit worker_started via stream writer (real-time to frontend)
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        writer({
            "type": "worker_started",
            "data": {
                "worker_id": worker_id,
                "worker_type": profile.name,
                "sub_task": task_description[:200],
                "tools": list(task_tool_names),
            },
        })
    except Exception:
        writer = None  # Fallback: no streaming (e.g., invoke() without stream_mode)

    # Filter tools to task's assigned tools + terminate
    registry = get_tool_registry()
    all_tools = registry.get_tools_for_context(
        sector=state.get("sector"),
        features=state.get("features"),
    )
    worker_tools = [
        t for t in all_tools
        if t.name in task_tool_names or t.name == "terminate"
    ]

    if not worker_tools:
        logger.warning(f"Swarm worker {worker_id}: no matching tools found")
        return _worker_failure(worker_id, task, "No matching tools available", start, writer)

    tool_schemas = [t.to_openai_param() for t in worker_tools]
    tools_desc = ", ".join(t.name for t in worker_tools if t.name != "terminate")

    # Build specialized system prompt from worker profile (Langfuse → default)
    system_content = await profile.resolve_prompt(
        task_description=task_description,
        tools_desc=tools_desc,
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": query},
    ]

    # Tool execution context
    tool_context = {
        "user_id": state.get("user_id"),
        "user_roles": state.get("user_roles", []),
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
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage as AIM, ToolMessage
        from app.agents.llm_models import get_planner_model

        # Build LangChain messages from dict messages
        lc_messages = [
            SystemMessage(content=messages[0]["content"]),
            HumanMessage(content=messages[1]["content"]),
        ]

        model_with_tools = get_planner_model().bind_tools(tool_schemas)

        for step in range(max_steps):
            response = await asyncio.wait_for(
                model_with_tools.ainvoke(lc_messages),
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
            if not response.tool_calls:
                content = re.sub(r"</?tool_call>", "", content).strip()
                answer = content
                break

            # Process tool calls (ChatOpenAI format: list of dicts with name/args/id)
            terminate_found = False

            for tc in response.tool_calls:
                tc_name = tc["name"]
                tc_args = tc["args"]
                tc_id = tc.get("id", "")

                reasoning_steps.append({
                    "type": StepType.TOOL_CALL.value,
                    "content": f"[Worker {worker_id}] {tc_name}({_summarize_args(tc_args)})",
                })

                if tc_name == "terminate":
                    answer = tc_args.get("answer", "")
                    sources = tc_args.get("sources", [])
                    if sources:
                        collected_sources.extend(sources)
                    terminate_found = True

                    # Execute terminate for proper message format
                    result = await registry.execute(tc_name, tc_args, context=tool_context)
                    lc_messages.append(response)  # AIMessage with tool_calls
                    lc_messages.append(ToolMessage(
                        content=result.output,
                        tool_call_id=tc_id,
                    ))
                    break

            if terminate_found:
                break

            # Execute non-terminate tools in parallel
            regular_tcs = [tc for tc in response.tool_calls if tc["name"] != "terminate"]
            if regular_tcs:
                # Append the AIMessage with tool_calls
                lc_messages.append(response)

                async def _run_tool(tc):
                    return tc, await registry.execute(tc["name"], tc["args"], context=tool_context)

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

                    lc_messages.append(ToolMessage(
                        content=observation,
                        tool_call_id=tc.get("id", ""),
                    ))

                    if result.sources:
                        collected_sources.extend(result.sources)

                    reasoning_steps.append({
                        "type": StepType.OBSERVATION.value,
                        "content": f"[Worker {worker_id}] {observation[:200]}",
                        "source": tc["name"],
                    })

    except asyncio.TimeoutError:
        logger.warning(f"Swarm worker {worker_id}: timed out after {settings.swarm_worker_timeout_seconds}s")
        return _worker_failure(
            worker_id, task,
            f"Timeout after {settings.swarm_worker_timeout_seconds}s",
            start, writer, reasoning_steps,
        )
    except Exception as e:
        logger.error(f"Swarm worker {worker_id}: error: {e}", exc_info=True)
        return _worker_failure(
            worker_id, task, str(e), start, writer, reasoning_steps,
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

    # Emit worker_complete via stream writer (real-time to frontend)
    if writer:
        writer({
            "type": "worker_complete",
            "data": {
                "worker_id": worker_id,
                "worker_type": profile.name,
                "preview": answer[:200] if answer else "",
                "sources_count": len(collected_sources),
                "latency_ms": latency_ms,
            },
        })

    worker_result = {
        "worker_id": worker_id,
        "worker_type": profile.name,
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
    }


def _worker_failure(
    worker_id: int,
    task: Dict[str, Any],
    error: str,
    start_time: float,
    writer: Any = None,
    reasoning_steps: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a failure result for a worker."""
    latency_ms = (time.time() - start_time) * 1000

    # Emit worker_complete (error) via stream writer if available
    if writer:
        writer({
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
    }
