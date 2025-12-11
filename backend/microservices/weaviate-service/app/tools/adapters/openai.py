"""
OpenAI Tool Call Adapter for GPT-4 and GPT-4o models.

This adapter handles OpenAI's native tool calling format, which uses
a structured tool_calls array in the API response.

OpenAI Tool Calling Format:
    Request:
        {
            "model": "gpt-4o",
            "messages": [...],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather for a location",
                        "parameters": { JSON Schema }
                    }
                }
            ]
        }

    Response:
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{\"location\": \"Paris\"}"
                        }
                    }]
                }
            }]
        }

Key Features:
    - Supports parallel tool calls (multiple tools in one response)
    - Uses tool_call_id for correlating results
    - Strict JSON schema validation available
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .base import ToolCallAdapter, register_adapter
from ..base import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


@register_adapter("openai")
@register_adapter("gpt-4")
@register_adapter("gpt-4o")
class OpenAIAdapter(ToolCallAdapter):
    """
    Adapter for OpenAI's native tool calling format.

    Used with:
    - GPT-4, GPT-4 Turbo
    - GPT-4o, GPT-4o-mini
    - Any OpenAI-compatible API that uses the same format

    Features:
    - Full parallel tool call support
    - Structured output with strict JSON schemas
    - Tool choice control (auto, none, required, specific)
    """

    @property
    def provider_name(self) -> str:
        return "openai"

    def format_tools_for_request(
        self,
        tools: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """
        Convert tools to OpenAI's tool format.

        Args:
            tools: List of ToolDefinition objects

        Returns:
            List of OpenAI tool objects
        """
        formatted_tools = []

        for tool in tools:
            formatted_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.to_json_schema(),
                    # Enable strict mode for better validation
                    "strict": False  # Set to True for strict JSON schema adherence
                }
            })

        return formatted_tools

    def parse_tool_calls(
        self,
        response: Any
    ) -> List[ToolCall]:
        """
        Parse tool calls from OpenAI response.

        Handles both ChatCompletion response format and streaming
        delta format.

        Args:
            response: OpenAI API response

        Returns:
            List of ToolCall objects
        """
        tool_calls = []

        if not isinstance(response, dict):
            return tool_calls

        # Handle ChatCompletion response
        if "choices" in response:
            for choice in response.get("choices", []):
                message = choice.get("message") or choice.get("delta", {})
                api_tool_calls = message.get("tool_calls", [])

                for tc in api_tool_calls:
                    if tc.get("type") == "function":
                        func = tc.get("function", {})

                        # Parse arguments JSON
                        raw_args = func.get("arguments", "{}")
                        try:
                            arguments = json.loads(raw_args) if raw_args else {}
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse arguments: {raw_args}")
                            arguments = {}

                        tool_calls.append(ToolCall(
                            id=tc.get("id", str(uuid4())),
                            name=func.get("name", ""),
                            arguments=arguments,
                            raw_arguments=raw_args
                        ))

        # Handle direct message format (e.g., from streaming accumulation)
        elif "tool_calls" in response:
            for tc in response.get("tool_calls", []):
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    raw_args = func.get("arguments", "{}")

                    try:
                        arguments = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        arguments = {}

                    tool_calls.append(ToolCall(
                        id=tc.get("id", str(uuid4())),
                        name=func.get("name", ""),
                        arguments=arguments,
                        raw_arguments=raw_args
                    ))

        return tool_calls

    def format_tool_results(
        self,
        results: List[ToolResult]
    ) -> List[Dict[str, Any]]:
        """
        Format tool results for OpenAI's expected format.

        OpenAI expects tool results as messages with role="tool"
        and a tool_call_id reference.

        Args:
            results: List of ToolResult from execution

        Returns:
            List of tool message dictionaries
        """
        messages = []

        for result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": result.to_llm_content()
            })

        return messages

    def has_tool_calls(self, response: Any) -> bool:
        """
        Check if response contains tool calls.

        Args:
            response: OpenAI response

        Returns:
            True if tool calls are present
        """
        if not isinstance(response, dict):
            return False

        if "choices" in response:
            for choice in response.get("choices", []):
                message = choice.get("message") or choice.get("delta", {})
                if message.get("tool_calls"):
                    return True

        elif response.get("tool_calls"):
            return True

        return False

    def get_text_content(self, response: Any) -> Optional[str]:
        """
        Extract text content from response.

        Args:
            response: OpenAI response

        Returns:
            Text content if present
        """
        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            # ChatCompletion format
            if "choices" in response:
                for choice in response.get("choices", []):
                    message = choice.get("message") or choice.get("delta", {})
                    content = message.get("content")
                    if content:
                        return content

            # Direct content
            elif "content" in response:
                return response["content"]

        return None

    def supports_parallel_tool_calls(self) -> bool:
        """
        OpenAI fully supports parallel tool calls.

        The model can call multiple tools in a single response,
        and all results can be sent back together.
        """
        return True

    def get_tool_choice_param(
        self,
        mode: str = "auto"
    ) -> Any:
        """
        Get OpenAI-compatible tool_choice parameter.

        Args:
            mode: Control mode
                - "auto": Model decides whether to use tools
                - "none": Never use tools
                - "required": Must use at least one tool
                - tool name: Must use specific tool

        Returns:
            tool_choice value for OpenAI API
        """
        if mode == "auto":
            return "auto"
        elif mode == "none":
            return "none"
        elif mode == "required":
            return "required"
        else:
            # Specific tool name - force that tool
            return {"type": "function", "function": {"name": mode}}

    def format_assistant_tool_call_message(
        self,
        response: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Format the assistant's tool call message for conversation history.

        When tool calls are made, you need to include the assistant's
        message with the tool_calls in the conversation before adding
        the tool results.

        Args:
            response: OpenAI response containing tool calls

        Returns:
            Assistant message dict for conversation history
        """
        if not isinstance(response, dict):
            return None

        if "choices" in response:
            for choice in response.get("choices", []):
                message = choice.get("message", {})
                if message.get("tool_calls"):
                    return {
                        "role": "assistant",
                        "content": message.get("content"),
                        "tool_calls": message["tool_calls"]
                    }

        return None
