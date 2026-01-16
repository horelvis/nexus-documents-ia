"""
Tool Interceptor - OpenCode-style tool call interception.

This module intercepts tool calls at the system level to:
1. Evaluate permission rules BEFORE execution
2. Check results AFTER execution for clarification needs
3. Emit SSE events when user input is required
4. Resume execution when user responds

Key difference from LLM-dependent approaches:
- The SYSTEM decides when to ask, not the LLM
- Guarantees consistent behavior regardless of LLM reasoning
- Automatic clarification for ambiguous results (e.g., multiple documents)
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .permission_manager import (
    PermissionDecision,
    PermissionManager,
    PermissionRequest,
    get_permission_manager,
)

logger = logging.getLogger(__name__)


class InterceptionPoint(str, Enum):
    """When the interception occurs."""
    PRE_EXECUTION = "pre"      # Before tool runs
    POST_EXECUTION = "post"    # After tool runs (check results)


@dataclass
class InterceptedResult:
    """
    Result of tool interception.

    Attributes:
        decision: The permission decision (allow, ask, deny)
        should_continue: Whether to continue with tool execution
        clarification_request: If ask, the request to send to user
        modified_input: Optional modified tool input
        original_result: The original tool result (if post-execution)
        user_selection: User's selection (after clarification resolved)
    """
    decision: PermissionDecision
    should_continue: bool = True
    clarification_request: Optional[PermissionRequest] = None
    modified_input: Optional[Dict[str, Any]] = None
    original_result: Any = None
    user_selection: Optional[List[str]] = None

    def to_sse_event(self) -> Optional[Dict[str, Any]]:
        """Convert to SSE event if clarification is needed."""
        if self.clarification_request:
            return {
                "type": "clarification_needed",
                "data": self.clarification_request.to_sse_event()
            }
        return None


class ToolInterceptor:
    """
    Intercepts tool calls for permission evaluation.

    Usage:
        interceptor = ToolInterceptor()

        # Before executing a tool
        result = await interceptor.intercept_pre(
            tool_name="search_agent",
            tool_input={"query": "contratos 2024"}
        )

        if result.decision == PermissionDecision.DENY:
            return "Operation not allowed"

        if result.decision == PermissionDecision.ASK:
            # Emit SSE event and wait for user response
            await emit_sse(result.to_sse_event())
            # ... wait for user response ...

        # After tool execution
        result = await interceptor.intercept_post(
            tool_name="search_agent",
            tool_input={"query": "contratos 2024"},
            tool_result=search_results
        )

        if result.decision == PermissionDecision.ASK:
            # Multiple results found, ask user to select
            await emit_sse(result.to_sse_event())
    """

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self._manager = permission_manager or get_permission_manager()
        self._pending_requests: Dict[str, asyncio.Event] = {}
        self._request_responses: Dict[str, List[str]] = {}

    async def intercept_pre(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> InterceptedResult:
        """
        Intercept a tool call BEFORE execution.

        Args:
            tool_name: Name of the tool being called
            tool_input: Input parameters to the tool

        Returns:
            InterceptedResult with decision and optional clarification request
        """
        decision = self._manager.evaluate(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=None  # No result yet
        )

        logger.debug(f"Pre-intercept {tool_name}: {decision}")

        if decision == PermissionDecision.DENY:
            return InterceptedResult(
                decision=decision,
                should_continue=False,
            )

        if decision == PermissionDecision.ASK:
            # Create clarification request for pre-execution ask
            request = self._manager.create_clarification_request(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=None,
                question=f"¿Deseas ejecutar {tool_name}?",
                options=[
                    {"label": "Sí, continuar", "value": "yes"},
                    {"label": "No, cancelar", "value": "no"},
                ],
                header="Confirmación",
            )

            return InterceptedResult(
                decision=decision,
                should_continue=False,  # Wait for user response
                clarification_request=request,
            )

        return InterceptedResult(
            decision=decision,
            should_continue=True,
        )

    async def intercept_post(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Any,
    ) -> InterceptedResult:
        """
        Intercept a tool call AFTER execution.

        This is where we check if results need user clarification,
        e.g., when search returns multiple documents.

        Args:
            tool_name: Name of the tool that was called
            tool_input: Input parameters that were used
            tool_result: Result from the tool execution

        Returns:
            InterceptedResult with decision and optional clarification request
        """
        decision = self._manager.evaluate(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result
        )

        logger.debug(f"Post-intercept {tool_name}: {decision}")

        if decision == PermissionDecision.ASK:
            # Generate clarification options from results
            options = self._extract_options_from_result(tool_name, tool_result)

            if options:
                query = tool_input.get("query", "")
                request = self._manager.create_clarification_request(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_result=tool_result,
                    question=f"Encontré múltiples resultados para '{query}'. ¿Cuál deseas analizar?",
                    options=options,
                    header="Selecciona documento",
                    multi_select=False,
                )

                return InterceptedResult(
                    decision=decision,
                    should_continue=False,
                    clarification_request=request,
                    original_result=tool_result,
                )

        return InterceptedResult(
            decision=decision,
            should_continue=True,
            original_result=tool_result,
        )

    def _extract_options_from_result(
        self,
        tool_name: str,
        result: Any
    ) -> List[Dict[str, str]]:
        """
        Extract user-friendly options from tool result.

        Converts technical search results into human-readable options
        for the clarification UI.
        """
        options = []

        # Parse result if string
        data = result
        if isinstance(result, str):
            try:
                data = json.loads(result)
            except:
                return options

        # Extract documents/results from common formats
        items = []
        if isinstance(data, dict):
            for key in ["results", "documents", "items", "matches", "data"]:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
        elif isinstance(data, list):
            items = data

        # Convert to options
        for i, item in enumerate(items[:10]):  # Limit to 10 options
            if isinstance(item, dict):
                # Try to extract meaningful label
                label = (
                    item.get("title") or
                    item.get("name") or
                    item.get("filename") or
                    item.get("document_name") or
                    f"Documento {i + 1}"
                )

                # Try to extract ID for value
                value = str(
                    item.get("id") or
                    item.get("document_id") or
                    item.get("uuid") or
                    i
                )

                # Try to extract description
                description = (
                    item.get("description") or
                    item.get("summary") or
                    item.get("snippet") or
                    item.get("content", "")[:100] + "..." if item.get("content") else ""
                )

                options.append({
                    "label": label[:50],  # Truncate long labels
                    "value": value,
                    "description": description[:100] if description else "",
                })
            else:
                # Simple item (string)
                options.append({
                    "label": str(item)[:50],
                    "value": str(i),
                    "description": "",
                })

        return options

    async def wait_for_response(
        self,
        request_id: str,
        timeout: float = 300.0  # 5 minutes default
    ) -> Optional[List[str]]:
        """
        Wait for user response to a clarification request.

        Args:
            request_id: The request ID to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            User's selected values, or None if timeout
        """
        event = asyncio.Event()
        self._pending_requests[request_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._request_responses.get(request_id)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response to {request_id}")
            return None
        finally:
            self._pending_requests.pop(request_id, None)
            self._request_responses.pop(request_id, None)

    def resolve_request(self, request_id: str, user_response: List[str]) -> bool:
        """
        Resolve a pending request with user's response.

        Called when user submits their selection via the API.

        Args:
            request_id: The request ID
            user_response: User's selected values

        Returns:
            True if request was found and resolved
        """
        # Store response
        self._request_responses[request_id] = user_response

        # Signal waiting coroutine
        event = self._pending_requests.get(request_id)
        if event:
            event.set()

        # Also resolve in permission manager
        resolved = self._manager.resolve_request(request_id, user_response)

        return resolved is not None


# Singleton instance
_interceptor: Optional[ToolInterceptor] = None


def get_tool_interceptor() -> ToolInterceptor:
    """Get or create the tool interceptor singleton."""
    global _interceptor
    if _interceptor is None:
        _interceptor = ToolInterceptor()
    return _interceptor


async def intercept_tool_call(
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_result: Any = None,
    point: InterceptionPoint = InterceptionPoint.POST_EXECUTION,
) -> InterceptedResult:
    """
    Convenience function to intercept a tool call.

    Args:
        tool_name: Name of the tool
        tool_input: Input parameters
        tool_result: Result (for post-execution interception)
        point: When to intercept (pre or post)

    Returns:
        InterceptedResult with decision and optional clarification
    """
    interceptor = get_tool_interceptor()

    if point == InterceptionPoint.PRE_EXECUTION:
        return await interceptor.intercept_pre(tool_name, tool_input)
    else:
        return await interceptor.intercept_post(tool_name, tool_input, tool_result)


def create_intercepted_tool(
    original_tool: Callable,
    tool_name: str,
) -> Callable:
    """
    Wrap a tool with interception logic.

    This wraps a tool callable (e.g., from .as_tool()) to add
    post-execution interception. When the tool returns multiple
    results, the interceptor modifies the output to trigger
    user clarification.

    Args:
        original_tool: The original tool callable from .as_tool()
        tool_name: Name of the tool for logging and rule matching

    Returns:
        Wrapped callable with interception logic
    """
    import functools

    @functools.wraps(original_tool)
    async def intercepted_tool(*args, **kwargs):
        """Execute tool and intercept results."""
        # Execute original tool
        result = await original_tool(*args, **kwargs)

        # Post-execution interception
        try:
            interception = await intercept_tool_call(
                tool_name=tool_name,
                tool_input=kwargs,
                tool_result=result,
                point=InterceptionPoint.POST_EXECUTION
            )

            if interception.decision == PermissionDecision.ASK and interception.clarification_request:
                # Format result as clarification response
                # This will be detected by parse_clarification_response in streaming
                clarification = interception.clarification_request
                clarification_output = json.dumps({
                    "_type": "clarification_request",
                    "request_id": clarification.request_id,
                    "question": clarification.question,
                    "header": clarification.header,
                    "options": clarification.options,
                    "multi_select": clarification.multi_select,
                    "original_result": result if isinstance(result, str) else str(result)[:500],
                }, ensure_ascii=False)

                logger.info(f"🔒 INTERCEPTOR: {tool_name} → ASK (multiple results)")
                return f"CLARIFICATION_NEEDED:{clarification_output}"

        except Exception as e:
            logger.warning(f"⚠️ Interception error for {tool_name}: {e}")

        return result

    return intercepted_tool


def format_clarification_for_llm(clarification_request: PermissionRequest) -> str:
    """
    Format a clarification request so the LLM understands it needs user input.

    This creates a structured response that the LLM should pass through
    to the user interface, triggering the clarification UI.
    """
    options_text = "\n".join([
        f"  - {opt.get('label', 'Option')}: {opt.get('description', '')}"
        for opt in clarification_request.options
    ])

    return f"""🔍 **Encontré múltiples opciones. Necesito tu ayuda para continuar.**

**{clarification_request.question}**

Opciones disponibles:
{options_text}

Por favor, selecciona una opción para continuar con el análisis.

[CLARIFICATION_REQUEST:{clarification_request.request_id}]"""
