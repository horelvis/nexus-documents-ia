"""
Async LLM Client for Emma v2

Native async client using httpx for direct communication with vLLM/OpenAI APIs.
Eliminates the sync/async mismatch from Qwen-Agent by being fully async.

Key Features:
- Native async streaming via SSE
- OpenAI-compatible tool calling
- Thinking mode support (Qwen3)
- Multi-provider support (vLLM, OpenAI, Anthropic)

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    LLMClient                                 │
    │                                                             │
    │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
    │  │   chat()     │    │ chat_stream()│    │ execute_tools│  │
    │  │ (non-stream) │    │ (SSE async)  │    │ (parallel)   │  │
    │  └──────────────┘    └──────────────┘    └──────────────┘  │
    │                              │                              │
    │                              ▼                              │
    │                    ┌──────────────────┐                    │
    │                    │  httpx.AsyncClient│                    │
    │                    │  (connection pool) │                    │
    │                    └──────────────────┘                    │
    │                              │                              │
    │                              ▼                              │
    │                    ┌──────────────────┐                    │
    │                    │  vLLM / OpenAI   │                    │
    │                    │  /v1/chat/completions                  │
    │                    └──────────────────┘                    │
    └─────────────────────────────────────────────────────────────┘

References:
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- https://platform.openai.com/docs/api-reference/chat
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

import httpx

from app.core.langfuse_config import langfuse_context, observe

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    VLLM = "vllm"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ToolCallState(str, Enum):
    """State of tool call parsing during streaming."""
    NONE = "none"
    STARTED = "started"
    COLLECTING = "collecting"
    COMPLETE = "complete"


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]
    raw_arguments: str = ""

    def to_message(self) -> Dict[str, Any]:
        """Convert to OpenAI assistant message format."""
        return {
            "tool_calls": [{
                "id": self.id,
                "type": "function",
                "function": {
                    "name": self.name,
                    "arguments": json.dumps(self.arguments),
                }
            }]
        }


@dataclass
class ToolResult:
    """Result from executing a tool."""
    tool_call_id: str
    name: str
    result: Any
    error: Optional[str] = None

    def to_message(self) -> Dict[str, Any]:
        """Convert to OpenAI tool response message format."""
        content = json.dumps(self.result) if not self.error else json.dumps({"error": self.error})
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": content,
        }


@dataclass
class LLMResponse:
    """Response from LLM chat completion."""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    thinking: Optional[str] = None
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency_ms: float = 0.0

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0

    def to_assistant_message(self) -> Dict[str, Any]:
        """Convert to OpenAI assistant message format for history."""
        msg = {
            "role": "assistant",
            "content": self.content,
        }
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    }
                }
                for tc in self.tool_calls
            ]
        return msg

    @classmethod
    def from_openai(cls, data: Dict[str, Any], latency_ms: float = 0.0) -> "LLMResponse":
        """Parse OpenAI-compatible API response."""
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        content = message.get("content", "") or ""
        finish_reason = choice.get("finish_reason", "stop")

        # Parse thinking tags from content
        thinking = None
        if "<think>" in content:
            thinking, content = _parse_thinking(content)

        # Parse tool calls
        tool_calls = []
        if raw_tool_calls := message.get("tool_calls"):
            for tc in raw_tool_calls:
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                    logger.warning(f"Failed to parse tool arguments: {args_str}")

                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=args,
                    raw_arguments=args_str,
                ))

        return cls(
            content=content.strip(),
            tool_calls=tool_calls,
            thinking=thinking,
            finish_reason=finish_reason,
            usage=data.get("usage", {}),
            model=data.get("model", ""),
            latency_ms=latency_ms,
        )


@dataclass
class StreamEvent:
    """Event from streaming response."""
    event_type: str  # "content", "tool_call", "thinking", "done", "error"
    content: str = ""
    tool_call: Optional[ToolCall] = None
    thinking: str = ""
    error: Optional[str] = None


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    provider: LLMProvider = LLMProvider.VLLM
    base_url: str = "http://vllm:8000/v1"
    model: str = "Qwen/Qwen3-4B"
    api_key: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    timeout: float = 120.0
    enable_thinking: bool = False
    thinking_budget: int = 4096


def _parse_thinking(text: str) -> tuple[Optional[str], str]:
    """
    Parse <think>...</think> tags from response.

    Returns:
        Tuple of (thinking_content, final_content)
    """
    think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)

    thinking_matches = think_pattern.findall(text)
    thinking = "\n".join(m.strip() for m in thinking_matches) if thinking_matches else None

    final_content = think_pattern.sub('', text).strip()

    return thinking, final_content


class LLMClient:
    """
    Async LLM Client for vLLM/OpenAI-compatible APIs.

    Features:
    - Fully async (no thread pools)
    - Native SSE streaming
    - Tool calling support
    - Thinking mode (Qwen3)
    - Connection pooling via httpx

    Example:
        >>> client = LLMClient(config)
        >>> response = await client.chat(messages, tools)
        >>> if response.has_tool_calls:
        ...     results = await execute_tools(response.tool_calls)
    """

    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                headers=headers,
                limits=httpx.Limits(
                    max_connections=10,
                    max_keepalive_connections=5,
                ),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _build_request_body(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        stream: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """Build request body for chat completion."""
        enable_thinking = kwargs.get("enable_thinking", self.config.enable_thinking)
        body = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "stream": stream,
        }

        # Add tools if provided
        if tools:
            body["tools"] = [
                {"type": "function", "function": t} if "type" not in t else t
                for t in tools
            ]
            body["tool_choice"] = kwargs.get("tool_choice", "auto")

        # Add thinking mode for vLLM with Qwen3 (override per request if provided)
        # NOTE: chat_template_kwargs must be at top level, NOT inside extra_body
        if self.config.provider == LLMProvider.VLLM:
            body["chat_template_kwargs"] = {
                "enable_thinking": enable_thinking,
            }

        return body

    @observe(as_type="generation", name="llm.chat")
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Send chat completion request (non-streaming).

        Args:
            messages: Conversation history
            tools: Available tools (OpenAI function format)
            **kwargs: Override config (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with content and/or tool calls
        """
        client = await self._get_client()
        body = self._build_request_body(messages, tools, stream=False, **kwargs)

        # Update Langfuse with generation details
        langfuse_context.update_current_observation(
            input=messages,
            metadata={
                "model": self.config.model,
                "provider": self.config.provider.value,
                "temperature": kwargs.get("temperature", self.config.temperature),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
                "tools_count": len(tools) if tools else 0,
            },
        )

        start_time = time.time()

        try:
            response = await client.post(
                f"{self.config.base_url}/chat/completions",
                json=body,
            )
            response.raise_for_status()

            latency_ms = (time.time() - start_time) * 1000
            data = response.json()

            result = LLMResponse.from_openai(data, latency_ms)

            # Update Langfuse with response details
            langfuse_context.update_current_observation(
                output=result.content,
                metadata={
                    "finish_reason": result.finish_reason,
                    "has_tool_calls": result.has_tool_calls,
                    "tool_calls": [tc.name for tc in result.tool_calls] if result.tool_calls else [],
                    "latency_ms": latency_ms,
                },
                usage={
                    "input": result.usage.get("prompt_tokens", 0),
                    "output": result.usage.get("completion_tokens", 0),
                    "total": result.usage.get("total_tokens", 0),
                } if result.usage else None,
                model=result.model or self.config.model,
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API error: {e.response.status_code} - {e.response.text}")
            langfuse_context.update_current_observation(
                level="ERROR",
                status_message=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
            raise
        except httpx.TimeoutException:
            logger.error(f"LLM request timed out after {self.config.timeout}s")
            langfuse_context.update_current_observation(
                level="ERROR",
                status_message=f"Timeout after {self.config.timeout}s",
            )
            raise

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream chat completion response.

        Yields StreamEvents as the response is generated:
        - "content": Text content chunk
        - "thinking": Thinking content chunk
        - "tool_call": Complete tool call
        - "done": Stream finished
        - "error": Error occurred

        Args:
            messages: Conversation history
            tools: Available tools
            **kwargs: Override config

        Yields:
            StreamEvent objects
        """
        client = await self._get_client()
        body = self._build_request_body(messages, tools, stream=True, **kwargs)

        # Create a generation span for streaming
        parent = langfuse_context.get_current_observation()
        generation = None
        if parent:
            try:
                generation = parent.generation(
                    name="llm.chat_stream",
                    input=messages,
                    metadata={
                        "model": self.config.model,
                        "provider": self.config.provider.value,
                        "streaming": True,
                        "tools_count": len(tools) if tools else 0,
                    },
                    model=self.config.model,
                )
                langfuse_context.push_observation(generation)
            except Exception as e:
                logger.debug(f"Failed to create generation span: {e}")

        start_time = time.time()
        total_content = ""

        try:
            async with client.stream(
                "POST",
                f"{self.config.base_url}/chat/completions",
                json=body,
            ) as response:
                response.raise_for_status()

                # State for accumulating tool calls
                current_tool_call: Optional[Dict[str, Any]] = None
                accumulated_content = ""
                in_thinking = False
                thinking_content = ""

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]  # Remove "data: " prefix

                    if data_str == "[DONE]":
                        # Emit any pending tool call
                        if current_tool_call:
                            try:
                                args = json.loads(current_tool_call.get("arguments", "{}"))
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamEvent(
                                event_type="tool_call",
                                tool_call=ToolCall(
                                    id=current_tool_call.get("id", ""),
                                    name=current_tool_call.get("name", ""),
                                    arguments=args,
                                    raw_arguments=current_tool_call.get("arguments", ""),
                                )
                            )

                        # Finalize Langfuse generation
                        if generation:
                            latency_ms = (time.time() - start_time) * 1000
                            try:
                                generation.update(
                                    output=accumulated_content,
                                    metadata={
                                        "latency_ms": latency_ms,
                                        "has_tool_calls": current_tool_call is not None,
                                    },
                                )
                                generation.end()
                            except Exception:
                                pass
                            langfuse_context.pop_observation()

                        yield StreamEvent(event_type="done")
                        return

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = data.get("choices", [{}])[0].get("delta", {})

                    # Handle content
                    if content := delta.get("content"):
                        # Check for thinking tags
                        if "<think>" in content:
                            in_thinking = True
                            content = content.replace("<think>", "")

                        if "</think>" in content:
                            in_thinking = False
                            parts = content.split("</think>")
                            thinking_content += parts[0]
                            content = parts[1] if len(parts) > 1 else ""

                            if thinking_content:
                                yield StreamEvent(
                                    event_type="thinking",
                                    thinking=thinking_content,
                                )
                                thinking_content = ""

                        if in_thinking:
                            thinking_content += content
                        elif content:
                            accumulated_content += content
                            yield StreamEvent(
                                event_type="content",
                                content=content,
                            )

                    # Handle tool calls
                    if tool_calls := delta.get("tool_calls"):
                        for tc in tool_calls:
                            tc_index = tc.get("index", 0)

                            # New tool call
                            if tc.get("id"):
                                # Emit previous tool call if exists
                                if current_tool_call:
                                    try:
                                        args = json.loads(current_tool_call.get("arguments", "{}"))
                                    except json.JSONDecodeError:
                                        args = {}
                                    yield StreamEvent(
                                        event_type="tool_call",
                                        tool_call=ToolCall(
                                            id=current_tool_call.get("id", ""),
                                            name=current_tool_call.get("name", ""),
                                            arguments=args,
                                            raw_arguments=current_tool_call.get("arguments", ""),
                                        )
                                    )

                                current_tool_call = {
                                    "id": tc.get("id"),
                                    "name": tc.get("function", {}).get("name", ""),
                                    "arguments": "",
                                }

                            # Accumulate arguments
                            if current_tool_call and tc.get("function", {}).get("arguments"):
                                current_tool_call["arguments"] += tc["function"]["arguments"]

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM stream error: {e.response.status_code}")
            if generation:
                try:
                    generation.update(level="ERROR", status_message=str(e))
                    generation.end()
                except Exception:
                    pass
                langfuse_context.pop_observation()
            yield StreamEvent(event_type="error", error=str(e))
        except httpx.TimeoutException:
            logger.error("LLM stream timed out")
            if generation:
                try:
                    generation.update(level="ERROR", status_message="Timeout")
                    generation.end()
                except Exception:
                    pass
                langfuse_context.pop_observation()
            yield StreamEvent(event_type="error", error="Request timed out")
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            if generation:
                try:
                    generation.update(level="ERROR", status_message=str(e))
                    generation.end()
                except Exception:
                    pass
                langfuse_context.pop_observation()
            yield StreamEvent(event_type="error", error=str(e))

    async def validate_connection(self) -> tuple[bool, str]:
        """
        Validate connection to LLM server.

        Returns:
            Tuple of (is_connected, message)
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.config.base_url}/models")

            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "unknown") for m in data.get("data", [])]
                return True, f"Connected. Models: {', '.join(models)}"
            else:
                return False, f"Server responded with status {response.status_code}"

        except httpx.ConnectError:
            return False, f"Cannot connect to {self.config.base_url}"
        except httpx.TimeoutException:
            return False, "Connection timed out"
        except Exception as e:
            return False, f"Connection error: {str(e)}"


# =============================================================================
# Factory Functions
# =============================================================================

def create_llm_client_from_settings() -> LLMClient:
    """
    Create LLM client from weaviate-service settings.

    Returns:
        Configured LLMClient instance
    """
    from app.core.config import settings

    # Determine provider
    provider_str = settings.llm_provider.lower()
    provider = LLMProvider(provider_str) if provider_str in [p.value for p in LLMProvider] else LLMProvider.VLLM

    if provider == LLMProvider.VLLM:
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            base_url=settings.vllm_base_url,
            model=settings.vllm_model,
            max_tokens=settings.vllm_max_tokens,
            temperature=settings.vllm_temperature,
            enable_thinking=settings.vllm_enable_thinking,
            thinking_budget=settings.vllm_thinking_budget,
            timeout=settings.agent_timeout_seconds,
        )
    elif provider == LLMProvider.OPENAI:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            timeout=settings.agent_timeout_seconds,
        )
    elif provider == LLMProvider.ANTHROPIC:
        # Note: Anthropic uses different API format, would need adapter
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            base_url="https://api.anthropic.com/v1",
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            timeout=settings.agent_timeout_seconds,
        )
    else:
        # Default to vLLM
        config = LLMConfig(
            provider=LLMProvider.VLLM,
            base_url=settings.vllm_base_url,
            model=settings.vllm_model,
        )

    return LLMClient(config)


# Global client instance (lazy initialization)
_llm_client: Optional[LLMClient] = None


async def get_llm_client() -> LLMClient:
    """
    Get global LLM client instance.

    Returns:
        Shared LLMClient instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = create_llm_client_from_settings()
    return _llm_client


async def close_llm_client() -> None:
    """Close global LLM client."""
    global _llm_client
    if _llm_client:
        await _llm_client.close()
        _llm_client = None
