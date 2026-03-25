"""
Hermes Tool Call Adapter for SGLang and Qwen3 models.

Hermes is the tool calling format used by SGLang's OpenAI-compatible API
when configured with --tool-call-parser hermes. It's based on the
Hermes function calling format originally from NousResearch.

Format Overview:
    Tool calls in responses use XML-like tags:
    <tool_call>
    {"name": "tool_name", "arguments": {"arg1": "value1"}}
    </tool_call>

    Tool results are formatted as:
    <tool_response>
    {"name": "tool_name", "content": "result content"}
    </tool_response>

When using SGLang's OpenAI-compatible API:
    - Set --tool-call-parser hermes in SGLang startup
    - Tools are passed in OpenAI format, SGLang handles conversion
    - Response includes tool_calls array when tools are used

This adapter handles both:
    1. Direct Hermes format (XML tags in text)
    2. SGLang's OpenAI-compatible parsed format
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .base import ToolCallAdapter, register_adapter
from ..base import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Regex patterns for parsing Hermes format
TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL
)
TOOL_RESPONSE_PATTERN = re.compile(
    r"<tool_response>\s*(.*?)\s*</tool_response>",
    re.DOTALL
)


@register_adapter("hermes")
@register_adapter("sglang")  # Primary alias
@register_adapter("vllm")  # Backward compatibility alias
class HermesAdapter(ToolCallAdapter):
    """
    Adapter for Hermes tool calling format.

    Used with:
    - SGLang with --tool-call-parser hermes
    - Qwen3 models (native Hermes support)
    - Some Ollama models

    The adapter handles both raw Hermes XML format and SGLang's
    OpenAI-compatible parsed format.
    """

    @property
    def provider_name(self) -> str:
        return "hermes"

    def format_tools_for_request(
        self,
        tools: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """
        Convert tools to OpenAI-compatible format for SGLang.

        SGLang's OpenAI-compatible endpoint accepts tools in OpenAI format
        and converts them internally to Hermes format for the model.

        Args:
            tools: List of ToolDefinition objects

        Returns:
            List of tool objects in OpenAI format
        """
        formatted_tools = []

        for tool in tools:
            formatted_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.to_json_schema()
                }
            })

        return formatted_tools

    def parse_tool_calls(
        self,
        response: Any
    ) -> List[ToolCall]:
        """
        Parse tool calls from SGLang response.

        Handles two formats:
        1. OpenAI-compatible format (parsed by SGLang)
        2. Raw Hermes XML format (fallback)

        Args:
            response: Response from SGLang API

        Returns:
            List of ToolCall objects
        """
        tool_calls = []

        # Check for OpenAI-compatible format first (SGLang parsed response)
        if isinstance(response, dict):
            # Handle ChatCompletion response format
            if "choices" in response:
                for choice in response.get("choices", []):
                    message = choice.get("message", {})
                    api_tool_calls = message.get("tool_calls", [])

                    for tc in api_tool_calls:
                        if tc.get("type") == "function":
                            func = tc.get("function", {})
                            try:
                                arguments = json.loads(func.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                arguments = {}
                                logger.warning(
                                    f"Failed to parse tool arguments: {func.get('arguments')}"
                                )

                            tool_calls.append(ToolCall(
                                id=tc.get("id", str(uuid4())),
                                name=func.get("name", ""),
                                arguments=arguments,
                                raw_arguments=func.get("arguments")
                            ))

            # Handle direct message format
            elif "tool_calls" in response:
                for tc in response.get("tool_calls", []):
                    if tc.get("type") == "function":
                        func = tc.get("function", {})
                        try:
                            arguments = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            arguments = {}

                        tool_calls.append(ToolCall(
                            id=tc.get("id", str(uuid4())),
                            name=func.get("name", ""),
                            arguments=arguments,
                            raw_arguments=func.get("arguments")
                        ))

        # If no OpenAI-format calls found, try raw Hermes format
        if not tool_calls:
            text_content = self.get_text_content(response)
            if text_content:
                tool_calls = self._parse_hermes_xml(text_content)

        return tool_calls

    def _parse_hermes_xml(self, text: str) -> List[ToolCall]:
        """
        Parse tool calls from raw Hermes XML format.

        Args:
            text: Text content potentially containing <tool_call> tags

        Returns:
            List of ToolCall objects
        """
        tool_calls = []
        matches = TOOL_CALL_PATTERN.findall(text)

        for match in matches:
            try:
                # Parse JSON inside the tool_call tags
                data = json.loads(match.strip())

                # Handle both formats: {"name": ..., "arguments": ...}
                # and {"name": ..., "parameters": ...}
                name = data.get("name", "")
                arguments = data.get("arguments") or data.get("parameters", {})

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}

                tool_calls.append(ToolCall(
                    id=str(uuid4()),
                    name=name,
                    arguments=arguments,
                    raw_arguments=match.strip()
                ))

            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse Hermes tool call: {e}")
                continue

        return tool_calls

    def format_tool_results(
        self,
        results: List[ToolResult]
    ) -> List[Dict[str, Any]]:
        """
        Format tool results for the next SGLang request.

        Returns results in OpenAI-compatible tool message format,
        which SGLang converts internally.

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

    def format_tool_results_hermes(
        self,
        results: List[ToolResult]
    ) -> str:
        """
        Format tool results in raw Hermes XML format.

        Use this when sending results directly to a model
        (not through SGLang's OpenAI-compatible API).

        Args:
            results: List of ToolResult from execution

        Returns:
            String with <tool_response> tags
        """
        parts = []

        for result in results:
            response_data = {
                "name": result.tool_name,
                "content": result.to_llm_content()
            }

            if not result.is_success:
                response_data["error"] = result.error

            parts.append(
                f"<tool_response>\n{json.dumps(response_data, ensure_ascii=False)}\n</tool_response>"
            )

        return "\n".join(parts)

    def has_tool_calls(self, response: Any) -> bool:
        """
        Check if response contains tool calls.

        Args:
            response: SGLang response

        Returns:
            True if tool calls are present
        """
        # Check OpenAI-compatible format
        if isinstance(response, dict):
            if "choices" in response:
                for choice in response.get("choices", []):
                    message = choice.get("message", {})
                    if message.get("tool_calls"):
                        return True

            elif "tool_calls" in response and response["tool_calls"]:
                return True

        # Check raw text for Hermes format
        text = self.get_text_content(response)
        if text and "<tool_call>" in text:
            return True

        return False

    def get_text_content(self, response: Any) -> Optional[str]:
        """
        Extract text content from response.

        Args:
            response: SGLang response

        Returns:
            Text content if present
        """
        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            # ChatCompletion format
            if "choices" in response:
                for choice in response.get("choices", []):
                    message = choice.get("message", {})
                    content = message.get("content")
                    if content:
                        return content

            # Direct content
            elif "content" in response:
                return response["content"]

            # Message format
            elif "message" in response:
                return response["message"].get("content")

        return None

    def get_text_without_tool_calls(self, response: Any) -> Optional[str]:
        """
        Get text content with tool call XML tags removed.

        Useful for getting clean text output when tools were used.

        Args:
            response: SGLang response

        Returns:
            Cleaned text content
        """
        text = self.get_text_content(response)
        if not text:
            return None

        # Remove tool_call tags and their content
        cleaned = TOOL_CALL_PATTERN.sub("", text)
        # Remove tool_response tags and their content
        cleaned = TOOL_RESPONSE_PATTERN.sub("", cleaned)
        # Clean up extra whitespace
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned.strip())

        return cleaned if cleaned else None

    def format_system_prompt_with_tools(
        self,
        base_prompt: str,
        tools: List[ToolDefinition]
    ) -> str:
        """
        Augment system prompt with Hermes tool instructions.

        While SGLang handles tool formatting, adding explicit instructions
        to the system prompt can improve tool usage reliability.

        Args:
            base_prompt: Original system prompt
            tools: Available tools

        Returns:
            Augmented system prompt
        """
        if not tools:
            return base_prompt

        # Build tool descriptions
        tool_descriptions = []
        for tool in tools:
            params_desc = []
            for param in tool.parameters:
                req = "required" if param.required else "optional"
                params_desc.append(f"  - {param.name} ({param.type}, {req}): {param.description}")

            tool_descriptions.append(
                f"- {tool.name}: {tool.description}\n" +
                "\n".join(params_desc)
            )

        tool_section = """

## Available Tools

You have access to the following tools:

""" + "\n\n".join(tool_descriptions) + """

To use a tool, respond with:
<tool_call>
{"name": "tool_name", "arguments": {"arg1": "value1"}}
</tool_call>

Wait for the tool response before continuing.
"""

        return base_prompt + tool_section

    def supports_parallel_tool_calls(self) -> bool:
        """Hermes typically handles one tool at a time."""
        return False

    def get_tool_choice_param(
        self,
        mode: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """
        Get SGLang-compatible tool_choice parameter.

        Args:
            mode: "auto", "none", "required", or tool name

        Returns:
            tool_choice value for SGLang API
        """
        if mode == "auto":
            return "auto"
        elif mode == "none":
            return "none"
        elif mode == "required":
            return "required"
        else:
            # Specific tool name
            return {"type": "function", "function": {"name": mode}}
