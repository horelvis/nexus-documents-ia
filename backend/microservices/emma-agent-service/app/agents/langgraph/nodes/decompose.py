"""
Emma Swarm Agent — Decompose Node

Decomposes complex multi-faceted queries into independent sub-tasks
that can execute in parallel via LangGraph's Send() API.

The decompose node:
1. Receives a query that classify_node marked as complex (use_swarm=True)
2. Calls LLM with a decomposition prompt
3. Returns N sub-tasks, each with assigned tools and focus area
4. If decomposition fails or returns empty → falls back to react_loop

Each sub-task is a dict:
    {
        "id": 0,
        "description": "Buscar el contrato de arrendamiento...",
        "tool_names": ["search_documents", "get_document_content"],
        "focus": "document_search",
        "max_steps": 2,
    }
"""

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
from ..tools.worker_profiles import get_worker_profile, get_valid_focus_types

logger = logging.getLogger(__name__)


def _extract_json_array(text: str) -> Optional[List[Dict[str, Any]]]:
    """Extract a JSON array from LLM response, handling common formatting issues."""
    text = text.strip()

    # Remove markdown code blocks if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```", "", text)

    # Remove <think> tags
    text = re.sub(r"</?think(?:ing)?>.*?(?:</?think(?:ing)?>|$)", "", text, flags=re.DOTALL)
    text = text.strip()

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON array from the text
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


def _validate_sub_tasks(
    sub_tasks: List[Dict[str, Any]],
    valid_tool_names: set,
    max_workers: int,
) -> List[Dict[str, Any]]:
    """Validate and normalize sub-tasks from LLM response."""
    validated = []

    for i, task in enumerate(sub_tasks[:max_workers]):
        if not isinstance(task, dict):
            continue

        description = task.get("description", "").strip()
        if not description:
            continue

        # Resolve focus and get typed worker profile
        focus = task.get("focus", "document_search")
        profile = get_worker_profile(focus)

        # Validate tool names — keep only known ones
        raw_tools = task.get("tool_names", [])
        if isinstance(raw_tools, str):
            raw_tools = [raw_tools]

        tool_names = [t for t in raw_tools if t in valid_tool_names and t != "terminate"]
        if not tool_names:
            # Use profile's default tools
            tool_names = _default_tools_for_focus(focus)

        validated.append({
            "id": i,
            "description": description,
            "tool_names": tool_names,
            "focus": focus,
            "worker_type": profile.name,
            "max_steps": min(task.get("max_steps", profile.max_steps), 4),
        })

    return validated


def _default_tools_for_focus(focus: str) -> List[str]:
    """Return default tool names from the typed worker profile.

    Each focus category has a WorkerProfile that defines its preferred
    tools. This replaces the hardcoded mapping with profile-driven defaults.
    """
    profile = get_worker_profile(focus)
    return list(profile.tool_names) if profile.tool_names else ["smart_search"]


@observe(as_type="span", name="decompose_node")
async def decompose_node(state: ReActState) -> Dict[str, Any]:
    """Decompose a complex query into parallel sub-tasks.

    If decomposition succeeds:
        Returns swarm_sub_tasks with N independent tasks.
    If decomposition fails or returns empty:
        Returns use_swarm=False so routing falls back to react_loop.

    Returns:
        State updates: swarm_sub_tasks, swarm_pending_events, reasoning_steps,
        metadata, and possibly use_swarm=False for fallback.
    """
    start = time.time()
    query = state.get("query", "")
    reasoning_steps = []

    # Get available tool names for validation
    registry = get_tool_registry()
    tools = registry.get_tools_for_context(
        sector=state.get("sector"),
        features=state.get("features"),
    )
    valid_tool_names = {t.name for t in tools}

    # Build tools description for the prompt
    tools_desc = "\n".join(
        f"- {t.name}: {t.description[:150]}"
        for t in tools if t.name != "terminate"
    )

    max_workers = settings.swarm_max_workers

    # Build focus types description from worker profiles
    from ..tools.worker_profiles import WORKER_PROFILES
    focus_types_str = "\n".join(
        f"- {focus}: {p.name} (herramientas: {', '.join(p.tool_names)})"
        for focus, p in WORKER_PROFILES.items()
    )

    # Load prompt from Langfuse
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt(
        "emma_swarm_decompose",
        variables={
            "tools_description": tools_desc,
            "focus_types": focus_types_str,
            "max_workers": str(max_workers),
        },
    )
    prompt_content = prompt.content

    # LLM call for decomposition
    # /no_think tells Qwen3 to skip thinking mode and output directly
    messages = [
        {"role": "system", "content": prompt_content},
        {"role": "user", "content": f"/no_think\n{query}"},
    ]

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        lc_messages = [
            SystemMessage(content=messages[0]["content"]),
            HumanMessage(content=messages[1]["content"]),
        ]
        model = get_planner_model()
        response = await model.ainvoke(lc_messages)
    except Exception as e:
        logger.error(f"Decompose: LLM call failed: {e}")
        reasoning_steps.append({
            "type": StepType.ERROR.value,
            "content": f"Decomposition failed: {e} — falling back to react_loop",
        })
        return {
            "use_swarm": False,
            "reasoning_steps": reasoning_steps,
            "metadata": {"decompose_error": str(e)},
        }

    # Parse LLM response — try content first, then thinking as fallback
    content = response.content or ""
    raw_tasks = _extract_json_array(content)

    # Qwen3 may put JSON inside <think> tags — check thinking as fallback
    thinking = getattr(response, "thinking", None)
    if raw_tasks is None and thinking:
        logger.debug("Decompose: trying thinking content as JSON fallback")
        raw_tasks = _extract_json_array(thinking)

    # Retry once on empty response (known OpenRouter/Qwen3 issue)
    if raw_tasks is None and not content and not thinking:
        logger.info("Decompose: empty response, retrying once...")
        try:
            retry_model = model.bind(temperature=0.5)
            response = await retry_model.ainvoke(lc_messages)
            content = response.content or ""
            raw_tasks = _extract_json_array(content)
            thinking = getattr(response, "thinking", None)
            if raw_tasks is None and thinking:
                raw_tasks = _extract_json_array(thinking)
        except Exception as e:
            logger.warning(f"Decompose: retry also failed: {e}")

    if raw_tasks is None:
        logger.warning(f"Decompose: failed to parse JSON from LLM response: {content[:200]}")
        reasoning_steps.append({
            "type": StepType.ERROR.value,
            "content": "Decomposition JSON parse failed — falling back to react_loop",
        })
        return {
            "use_swarm": False,
            "reasoning_steps": reasoning_steps,
            "metadata": {"decompose_parse_error": True},
        }

    if not raw_tasks:
        logger.info("Decompose: LLM returned empty list — falling back to react_loop")
        reasoning_steps.append({
            "type": StepType.ROUTING.value,
            "content": "Decomposition returned empty — query is simple, using react_loop",
        })
        return {
            "use_swarm": False,
            "reasoning_steps": reasoning_steps,
            "metadata": {"decompose_empty": True},
        }

    # Validate sub-tasks
    sub_tasks = _validate_sub_tasks(raw_tasks, valid_tool_names, max_workers)

    if not sub_tasks:
        logger.warning("Decompose: no valid sub-tasks after validation — falling back")
        return {
            "use_swarm": False,
            "reasoning_steps": [{
                "type": StepType.ERROR.value,
                "content": "No valid sub-tasks after validation — falling back to react_loop",
            }],
        }

    latency_ms = (time.time() - start) * 1000

    logger.info(
        f"Decompose: {len(sub_tasks)} sub-tasks in {latency_ms:.0f}ms: "
        f"{[t['focus'] for t in sub_tasks]}"
    )

    reasoning_steps.append({
        "type": StepType.ROUTING.value,
        "content": (
            f"Decomposed into {len(sub_tasks)} parallel sub-tasks: "
            + ", ".join(t["description"][:60] for t in sub_tasks)
        ),
    })

    # Emit swarm_started event via stream writer (real-time to frontend)
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
        writer({
            "type": "swarm_started",
            "data": {
                "num_workers": len(sub_tasks),
                "sub_tasks": [
                    {"description": t["description"][:200], "focus": t["focus"]}
                    for t in sub_tasks
                ],
            },
        })
    except Exception:
        pass  # No streaming context (e.g., graph.invoke())

    return {
        "swarm_sub_tasks": sub_tasks,
        "reasoning_steps": reasoning_steps,
        "metadata": {
            "decompose_latency_ms": latency_ms,
            "decompose_count": len(sub_tasks),
        },
    }
