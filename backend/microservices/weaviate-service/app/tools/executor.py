"""
Tool Executor - Async execution with timeout, retry, and error handling.

The ToolExecutor is responsible for:
1. Validating tool call arguments
2. Executing tools with proper timeouts
3. Retrying on transient failures
4. Producing standardized ToolResult objects
5. Logging and metrics collection

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                     ToolExecutor                             │
    │                                                              │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ 1. Validate Arguments (Pydantic)                      │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                          ↓                                   │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ 2. Check Rate Limits / Permissions                    │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                          ↓                                   │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ 3. Execute with Timeout (asyncio.wait_for)            │   │
    │  │    └── Retry on transient errors (exponential backoff)│   │
    │  └──────────────────────────────────────────────────────┘   │
    │                          ↓                                   │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ 4. Return ToolResult (success or error)               │   │
    │  └──────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import ValidationError

from .base import (
    BaseTool,
    ToolCall,
    ToolExecutionContext,
    ToolResult,
    ToolResultStatus,
)

if TYPE_CHECKING:
    from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Base exception for tool execution errors."""

    def __init__(self, message: str, status: ToolResultStatus = ToolResultStatus.ERROR):
        super().__init__(message)
        self.status = status


class ToolNotFoundError(ToolExecutionError):
    """Tool not found in registry."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", ToolResultStatus.NOT_FOUND)
        self.tool_name = tool_name


class ToolValidationError(ToolExecutionError):
    """Tool arguments failed validation."""

    def __init__(self, tool_name: str, details: str):
        super().__init__(
            f"Invalid arguments for {tool_name}: {details}",
            ToolResultStatus.ERROR
        )
        self.tool_name = tool_name
        self.details = details


class ToolTimeoutError(ToolExecutionError):
    """Tool execution timed out."""

    def __init__(self, tool_name: str, timeout: float):
        super().__init__(
            f"Tool {tool_name} timed out after {timeout}s",
            ToolResultStatus.TIMEOUT
        )
        self.tool_name = tool_name
        self.timeout = timeout


@dataclass
class ExecutorConfig:
    """Configuration for ToolExecutor."""

    # Default timeout for tool execution (seconds)
    default_timeout: float = 30.0

    # Maximum timeout allowed (seconds)
    max_timeout: float = 120.0

    # Default retry attempts for transient failures
    default_retries: int = 2

    # Initial retry delay (seconds) - doubles each attempt
    retry_base_delay: float = 1.0

    # Maximum retry delay (seconds)
    retry_max_delay: float = 10.0

    # Whether to run tools in parallel when multiple calls are made
    parallel_execution: bool = True

    # Maximum concurrent tool executions
    max_concurrency: int = 5


class ToolExecutor:
    """
    Executes tools with proper error handling, timeouts, and retries.

    The executor is the central point for all tool invocations. It ensures
    consistent behavior, logging, and error handling across all tools.

    Example:
        executor = ToolExecutor(registry)

        result = await executor.execute(
            call=ToolCall(name="search_emails", arguments={"query": "invoice"}),
            context=ToolExecutionContext(tenant_id="abc123")
        )

        if result.is_success:
            print(result.data)
        else:
            print(f"Error: {result.error}")
    """

    def __init__(
        self,
        registry: "ToolRegistry",
        config: Optional[ExecutorConfig] = None
    ):
        """
        Initialize the executor.

        Args:
            registry: ToolRegistry with available tools
            config: Executor configuration (uses defaults if not provided)
        """
        self.registry = registry
        self.config = config or ExecutorConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)

    async def execute(
        self,
        call: ToolCall,
        context: ToolExecutionContext,
        timeout: Optional[float] = None
    ) -> ToolResult:
        """
        Execute a single tool call.

        Args:
            call: The tool call to execute
            context: Execution context (tenant, user, credentials)
            timeout: Override timeout (uses tool or default if not provided)

        Returns:
            ToolResult with execution outcome
        """
        start_time = time.perf_counter()

        try:
            # Get tool from registry
            tool = self.registry.get_tool(call.name)
            if not tool:
                raise ToolNotFoundError(call.name)

            # Determine timeout
            effective_timeout = min(
                timeout or tool.timeout_seconds or self.config.default_timeout,
                self.config.max_timeout
            )

            # Validate arguments
            try:
                params = tool.validate_params(call.arguments)
            except ValidationError as e:
                raise ToolValidationError(call.name, str(e))

            # Execute with retries
            result = await self._execute_with_retry(
                tool=tool,
                params=params,
                context=context,
                call_id=call.id,
                timeout=effective_timeout
            )

            return result

        except ToolExecutionError as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                status=e.status,
                error=str(e),
                execution_time_ms=execution_time
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.exception(f"Unexpected error executing tool {call.name}")
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                status=ToolResultStatus.ERROR,
                error=f"Unexpected error: {str(e)}",
                execution_time_ms=execution_time
            )

    async def execute_many(
        self,
        calls: List[ToolCall],
        context: ToolExecutionContext
    ) -> List[ToolResult]:
        """
        Execute multiple tool calls.

        If parallel_execution is enabled and the adapter supports it,
        calls will be executed concurrently (up to max_concurrency).

        Args:
            calls: List of tool calls to execute
            context: Shared execution context

        Returns:
            List of ToolResult in same order as calls
        """
        if not calls:
            return []

        if self.config.parallel_execution and len(calls) > 1:
            # Execute in parallel with concurrency limit
            tasks = [
                self._execute_with_semaphore(call, context)
                for call in calls
            ]
            return await asyncio.gather(*tasks)
        else:
            # Execute sequentially
            results = []
            for call in calls:
                result = await self.execute(call, context)
                results.append(result)
            return results

    async def _execute_with_semaphore(
        self,
        call: ToolCall,
        context: ToolExecutionContext
    ) -> ToolResult:
        """Execute a call with concurrency limiting."""
        async with self._semaphore:
            return await self.execute(call, context)

    async def _execute_with_retry(
        self,
        tool: BaseTool,
        params: Any,
        context: ToolExecutionContext,
        call_id: str,
        timeout: float
    ) -> ToolResult:
        """
        Execute tool with retry logic for transient failures.

        Uses exponential backoff between retries.

        Args:
            tool: The tool to execute
            params: Validated parameters
            context: Execution context
            call_id: ID for result correlation
            timeout: Execution timeout

        Returns:
            ToolResult from successful execution

        Raises:
            ToolTimeoutError: If all attempts timeout
            ToolExecutionError: If all retries fail
        """
        max_attempts = tool.max_retries + 1
        last_error: Optional[Exception] = None
        delay = self.config.retry_base_delay

        for attempt in range(max_attempts):
            try:
                start_time = time.perf_counter()

                # Execute with timeout
                result = await asyncio.wait_for(
                    tool.execute(params, context),
                    timeout=timeout
                )

                execution_time = (time.perf_counter() - start_time) * 1000

                # Update execution time in result
                result.execution_time_ms = execution_time

                return result

            except asyncio.TimeoutError:
                last_error = ToolTimeoutError(tool.name, timeout)
                logger.warning(
                    f"Tool {tool.name} timed out (attempt {attempt + 1}/{max_attempts})"
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Tool {tool.name} failed (attempt {attempt + 1}/{max_attempts}): {e}"
                )

            # Don't retry on last attempt or non-transient errors
            if attempt < max_attempts - 1:
                if self._is_transient_error(last_error):
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.config.retry_max_delay)
                else:
                    break

        # All retries exhausted
        execution_time = 0  # Couldn't calculate exact time

        if isinstance(last_error, ToolTimeoutError):
            raise last_error

        raise ToolExecutionError(
            f"Tool {tool.name} failed after {max_attempts} attempts: {last_error}"
        )

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient (worth retrying).

        Args:
            error: The exception that occurred

        Returns:
            True if the error might be transient
        """
        # Timeouts are always transient
        if isinstance(error, (asyncio.TimeoutError, ToolTimeoutError)):
            return True

        # Check for common transient error indicators
        error_str = str(error).lower()
        transient_indicators = [
            "timeout",
            "connection",
            "temporary",
            "unavailable",
            "rate limit",
            "503",
            "504",
            "429",
        ]

        return any(indicator in error_str for indicator in transient_indicators)


class BatchToolExecutor:
    """
    Optimized executor for batch tool operations.

    Some tools can be more efficient when handling multiple requests
    at once (e.g., batch database queries). This executor detects
    batchable calls and groups them.
    """

    def __init__(
        self,
        registry: "ToolRegistry",
        config: Optional[ExecutorConfig] = None
    ):
        self.registry = registry
        self.config = config or ExecutorConfig()
        self._executor = ToolExecutor(registry, config)

    async def execute_batch(
        self,
        calls: List[ToolCall],
        context: ToolExecutionContext
    ) -> List[ToolResult]:
        """
        Execute a batch of tool calls, optimizing where possible.

        Groups calls by tool name and executes batchable tools
        in optimized batches.

        Args:
            calls: List of tool calls
            context: Execution context

        Returns:
            List of ToolResult in same order as calls
        """
        if not calls:
            return []

        # Group calls by tool name
        grouped: Dict[str, List[tuple[int, ToolCall]]] = {}
        for idx, call in enumerate(calls):
            if call.name not in grouped:
                grouped[call.name] = []
            grouped[call.name].append((idx, call))

        # Execute each group
        results: List[Optional[ToolResult]] = [None] * len(calls)

        for tool_name, indexed_calls in grouped.items():
            tool = self.registry.get_tool(tool_name)

            if tool and hasattr(tool, "execute_batch"):
                # Tool supports batching
                batch_calls = [call for _, call in indexed_calls]
                batch_results = await tool.execute_batch(batch_calls, context)

                for (idx, _), result in zip(indexed_calls, batch_results):
                    results[idx] = result
            else:
                # Execute individually
                for idx, call in indexed_calls:
                    results[idx] = await self._executor.execute(call, context)

        # Filter out None (shouldn't happen)
        return [r for r in results if r is not None]
