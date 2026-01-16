"""
Permission System for Emma AI - OpenCode-style Tool Interceptor

This module implements a permission system similar to OpenCode that:
1. Intercepts tool calls BEFORE execution
2. Evaluates rules to determine: "allow", "ask", or "deny"
3. For "ask" - pauses execution and requests user confirmation
4. Supports pattern matching for fine-grained control

Key difference from LLM-dependent approaches:
- The system decides when to ask, not the LLM
- Guarantees consistent behavior regardless of LLM reasoning
- Supports automatic clarification for ambiguous results

Reference: https://github.com/anomalyco/opencode
Documentation: https://opencode.ai/docs/permissions/
"""

from .permission_manager import (
    PermissionManager,
    PermissionRule,
    PermissionDecision,
    PermissionRequest,
    get_permission_manager,
)
from .tool_interceptor import (
    ToolInterceptor,
    InterceptedResult,
    InterceptionPoint,
    intercept_tool_call,
    get_tool_interceptor,
    create_intercepted_tool,
    format_clarification_for_llm,
)

__all__ = [
    # Permission Manager
    "PermissionManager",
    "PermissionRule",
    "PermissionDecision",
    "PermissionRequest",
    "get_permission_manager",
    # Tool Interceptor
    "ToolInterceptor",
    "InterceptedResult",
    "InterceptionPoint",
    "intercept_tool_call",
    "get_tool_interceptor",
    "create_intercepted_tool",
    "format_clarification_for_llm",
]
