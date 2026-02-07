"""
Emma ReAct Agent — Tools Package

OpenManus-inspired tool collection for the ReAct agent loop.
Each tool is a self-contained unit with schema, execution, and observability.
"""

from .base import EmmaTool, ToolResult, ToolError
from .registry import ToolRegistry, get_tool_registry
from .terminate import TerminateTool

__all__ = [
    "EmmaTool",
    "ToolResult",
    "ToolError",
    "ToolRegistry",
    "get_tool_registry",
    "TerminateTool",
]
