"""
Meta Agent Sandbox — Secure execution environment for generated forward() code.

Provides three layers of defense:
1. ASTValidator: Whitelist-based AST inspection (blocks imports, exec, eval, dunder)
2. CodeExecutor: Restricted globals namespace (only safe builtins + AgentContext)
3. AgentContext: Proxied access to LLM and tools with call limits and timeouts

The generated forward() function receives AgentContext as its only interface
to the outside world. All LLM calls, tool executions, and state reads go through
proxied, rate-limited wrappers.

Security model:
    - No imports (ast.Import, ast.ImportFrom blocked)
    - No exec/eval/compile/open/__import__/getattr/setattr
    - No dunder attribute access (obj.__class__ etc.)
    - No file I/O (open not in builtins, no os/pathlib)
    - Max LLM calls enforced (default 10)
    - Max tool calls enforced (default 20)
    - Global timeout via asyncio.wait_for (default 120s)
"""

from __future__ import annotations

import ast
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .schemas import AgentResult

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class SecurityError(Exception):
    """Raised when generated code violates sandbox policy."""
    pass


class ResourceLimitError(Exception):
    """Raised when generated code exceeds resource limits."""
    pass


# =============================================================================
# AST Validator — Whitelist-based code inspection
# =============================================================================

# Node types that generated code is ALLOWED to use
ALLOWED_NODE_TYPES: Set[type] = {
    # Definitions
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    # Assignments
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    # Control flow
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.Return,
    ast.Break,
    ast.Continue,
    ast.Pass,
    # Expressions
    ast.Expr,
    ast.Call,
    ast.Await,
    ast.Attribute,
    ast.Subscript,
    ast.Name,
    ast.Constant,
    ast.Starred,
    ast.IfExp,
    # Collections
    ast.List,
    ast.Dict,
    ast.Tuple,
    ast.Set,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
    # Comprehension internals
    ast.comprehension,
    # Operators
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    # String formatting
    ast.JoinedStr,
    ast.FormattedValue,
    # Error handling
    ast.Try,
    ast.ExceptHandler,
    # Operator/comparator nodes (children of BinOp, Compare, etc.)
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.BitAnd, ast.BitOr, ast.BitXor, ast.Invert, ast.LShift, ast.RShift,
    ast.USub, ast.UAdd,
    # Module wrapper
    ast.Module,
    # Load/Store/Del contexts
    ast.Load, ast.Store, ast.Del,
    # Arguments
    ast.arguments, ast.arg,
    # Keyword arguments
    ast.keyword,
    # Slice
    ast.Slice,
}

# Function names that are BLOCKED even if in builtins
BLOCKED_FUNCTIONS: Set[str] = {
    "exec", "eval", "compile", "open", "__import__",
    "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir",
    "type", "super", "breakpoint",
    "input", "exit", "quit",
    "memoryview", "bytearray", "bytes",
    "classmethod", "staticmethod", "property",
    "help", "id", "hash", "object",
}


class ASTValidator:
    """Validates generated Python code via AST inspection.

    Uses a whitelist of allowed AST node types. Any node type not in
    the whitelist is rejected. Additionally blocks:
    - Attribute access starting with '_' (prevents dunder escape)
    - Known dangerous function calls (exec, eval, etc.)
    """

    def validate(self, code: str) -> None:
        """Parse and validate code. Raises SecurityError on violations."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SecurityError(f"Syntax error in generated code: {e}")

        self._visit(tree)

    def _visit(self, node: ast.AST) -> None:
        """Recursively validate all nodes in the AST."""
        node_type = type(node)

        # Check against whitelist
        if node_type not in ALLOWED_NODE_TYPES:
            raise SecurityError(
                f"Forbidden AST node: {node_type.__name__}. "
                f"Generated code must not use {node_type.__name__} constructs."
            )

        # Block underscore-prefixed attribute access (prevents dunder escape)
        if isinstance(node, ast.Attribute):
            if isinstance(node.attr, str) and node.attr.startswith("_"):
                raise SecurityError(
                    f"Access to private/dunder attribute '{node.attr}' is forbidden."
                )

        # Block dangerous function calls
        if isinstance(node, ast.Call):
            func = node.func
            func_name = None
            if isinstance(func, ast.Name):
                func_name = func.id
            elif isinstance(func, ast.Attribute):
                func_name = func.attr

            if func_name and func_name in BLOCKED_FUNCTIONS:
                raise SecurityError(
                    f"Call to forbidden function '{func_name}'."
                )

        # Recurse into children
        for child in ast.iter_child_nodes(node):
            self._visit(child)


# =============================================================================
# Agent Context — Safe primitives for generated code
# =============================================================================

class _LLMProxy:
    """Proxied LLM access with call counting and limits."""

    def __init__(self, router: Any, max_calls: int = 10):
        self._router = router
        self._max_calls = max_calls
        self._call_count = 0

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Any:
        """Send chat completion via LLM Router (rate-limited)."""
        self._call_count += 1
        if self._call_count > self._max_calls:
            raise ResourceLimitError(
                f"Exceeded maximum LLM calls ({self._max_calls}). "
                f"Strategy is too LLM-heavy."
            )
        return await self._router.chat(messages=messages, tools=tools, **kwargs)


class _ToolProxy:
    """Proxied tool access with call counting, context injection, and limits."""

    def __init__(self, registry: Any, state: Dict[str, Any], max_calls: int = 20):
        self._registry = registry
        self._state = state
        self._max_calls = max_calls
        self._call_count = 0

    async def execute(self, name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a tool by name (rate-limited, context-injected)."""
        self._call_count += 1
        if self._call_count > self._max_calls:
            raise ResourceLimitError(
                f"Exceeded maximum tool calls ({self._max_calls}). "
                f"Strategy uses too many tools."
            )

        context = {
            "tenant_id": self._state.get("tenant_id", ""),
            "user_id": self._state.get("user_id"),
            "is_admin": self._state.get("is_admin", False),
            "sector": self._state.get("sector"),
            "sector_config": self._state.get("sector_config"),
            "features": self._state.get("features", {}),
            "query": self._state.get("query", ""),
        }

        return await self._registry.execute(name, args or {}, context)

    def list_names(self) -> List[str]:
        """List available tool names."""
        tools = self._registry.get_tools_for_context(
            self._state.get("tenant_id", ""),
            self._state.get("sector"),
            self._state.get("features"),
        )
        return [t.name for t in tools]

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI-format tool schemas."""
        return self._registry.get_openai_params(
            self._state.get("tenant_id", ""),
            self._state.get("sector"),
            self._state.get("features"),
        )


class _ReadOnlyState:
    """Read-only view of ReActState for generated code."""

    def __init__(self, state: Dict[str, Any]):
        self.query: str = state.get("query", "")
        self.tenant_id: str = state.get("tenant_id", "")
        self.sector: Optional[str] = state.get("sector")
        self.features: Dict[str, bool] = state.get("features", {})
        self.thread_id: str = state.get("thread_id", "")


class AgentContext:
    """Sandboxed access to Emma's primitives for generated forward() functions.

    This is the ONLY interface generated code has to the outside world.
    All LLM calls, tool executions, and state access go through here.
    """

    def __init__(
        self,
        state: Dict[str, Any],
        registry: Any,
        router: Any,
        max_llm_calls: int = 10,
        max_tool_calls: int = 20,
    ):
        self.llm = _LLMProxy(router, max_calls=max_llm_calls)
        self.tools = _ToolProxy(registry, state, max_calls=max_tool_calls)
        self.state = _ReadOnlyState(state)
        self._reasoning_steps: List[Dict[str, Any]] = []

    def log(self, message: str) -> None:
        """Record a reasoning step (visible in SSE stream)."""
        self._reasoning_steps.append({
            "type": "reasoning_step",
            "content": str(message)[:500],
        })


# =============================================================================
# Safe builtins for restricted exec
# =============================================================================

SAFE_BUILTINS: Dict[str, Any] = {
    # Types
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    # Iteration
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    # Math
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    # Sorting
    "sorted": sorted,
    "reversed": reversed,
    # Type checking
    "isinstance": isinstance,
    "issubclass": issubclass,
    # Logic
    "any": any,
    "all": all,
    # String
    "repr": repr,
    "format": format,
    # Exceptions (for try/except in generated code)
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "TypeError": TypeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    # Constants
    "True": True,
    "False": False,
    "None": None,
    # No-op print (prevents output leakage)
    "print": lambda *a, **kw: None,
}


# =============================================================================
# Code Executor — Restricted exec with resource limits
# =============================================================================

class CodeExecutor:
    """Execute validated forward() in a restricted namespace.

    Execution pipeline:
    1. Validate AST (whitelist check)
    2. Compile (syntax check)
    3. Execute in restricted namespace (custom __builtins__)
    4. Extract forward() function
    5. Run with timeout
    """

    def __init__(self, validator: Optional[ASTValidator] = None):
        self._validator = validator or ASTValidator()

    async def execute(
        self,
        code: str,
        query: str,
        ctx: AgentContext,
        timeout: float = 120.0,
    ) -> AgentResult:
        """Execute generated forward() code in the sandbox.

        Args:
            code: Python source containing async def forward(query, ctx)
            query: User query to pass to forward()
            ctx: AgentContext with proxied LLM/tools
            timeout: Maximum execution time in seconds

        Returns:
            AgentResult from the forward() function

        Raises:
            SecurityError: Code violates sandbox policy
            ResourceLimitError: Code exceeds call limits
            asyncio.TimeoutError: Code exceeds timeout
        """
        # 1. Validate AST
        self._validator.validate(code)

        # 2. Compile
        try:
            compiled = compile(code, "<meta-strategy>", "exec")
        except SyntaxError as e:
            raise SecurityError(f"Compilation error: {e}")

        # 3. Execute in restricted namespace
        namespace: Dict[str, Any] = {
            "__builtins__": SAFE_BUILTINS,
            "AgentContext": AgentContext,
            "AgentResult": AgentResult,
        }
        exec(compiled, namespace)  # noqa: S102 — intentional restricted exec

        # 4. Extract forward()
        forward_fn = namespace.get("forward")
        if forward_fn is None:
            raise SecurityError(
                "Generated code must define 'async def forward(query, ctx)'"
            )
        if not asyncio.iscoroutinefunction(forward_fn):
            raise SecurityError(
                "forward() must be an async function (async def forward(...))"
            )

        # 5. Run with timeout
        result = await asyncio.wait_for(
            forward_fn(query, ctx),
            timeout=timeout,
        )

        if not isinstance(result, AgentResult):
            raise SecurityError(
                f"forward() must return AgentResult, got {type(result).__name__}"
            )

        # Normalize sources to list (LLM-generated code may pass wrong types)
        if not isinstance(result.sources, list):
            result.sources = []

        return result
