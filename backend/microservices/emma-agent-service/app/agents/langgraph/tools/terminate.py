"""
Emma ReAct Agent — Terminate Tool

Signals the ReAct loop to stop and produce a final answer.
Inspired by OpenManus Terminate pattern: the agent explicitly decides
when it has gathered enough information to respond.

The agent calls this tool when:
1. It has enough information to answer the user's question
2. It determines the question cannot be answered with available tools
3. It wants to respond directly without further tool calls
"""

import logging
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class TerminateInput(BaseModel):
    """Input schema for the terminate tool."""
    answer: str = Field(
        description="La respuesta completa y final para el usuario. "
        "Incluye toda la información relevante, citas y fuentes."
    )
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Lista de fuentes citadas. Cada fuente puede incluir: "
        "title, document_id, boe_id, url, type, relevance.",
    )


class TerminateTool(EmmaTool):
    """Signals the ReAct loop to stop with a final answer.

    This is a special tool: react_loop checks for it by name and
    exits the loop when invoked. The 'answer' becomes final_answer
    in the state, and 'sources' are passed through to synthesize.
    """

    @property
    def name(self) -> str:
        return "terminate"

    @property
    def description(self) -> str:
        return (
            "Finaliza la conversación con una respuesta completa. "
            "Usa esta herramienta cuando tengas suficiente información "
            "para responder al usuario. Incluye todas las fuentes relevantes."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return TerminateInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        answer = arguments.get("answer", "")
        sources = arguments.get("sources", [])
        return ToolResult(
            output=answer,
            sources=sources,
            data={"terminated": True},
            success=True,
        )
