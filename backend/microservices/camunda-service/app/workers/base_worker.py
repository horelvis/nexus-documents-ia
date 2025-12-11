"""
Base External Task Worker for Camunda 7

Provides abstract base class for implementing external task workers.
Uses long polling with fetch-and-lock pattern.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class ExternalTask:
    """Represents a Camunda external task."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str = data.get("id", "")
        self.worker_id: str = data.get("workerId", "")
        self.topic_name: str = data.get("topicName", "")
        self.process_instance_id: str = data.get("processInstanceId", "")
        self.process_definition_id: str = data.get("processDefinitionId", "")
        self.process_definition_key: str = data.get("processDefinitionKey", "")
        self.activity_id: str = data.get("activityId", "")
        self.activity_instance_id: str = data.get("activityInstanceId", "")
        self.execution_id: str = data.get("executionId", "")
        self.tenant_id: Optional[str] = data.get("tenantId")
        self.priority: int = data.get("priority", 0)
        self.retries: int = data.get("retries", 3)
        self.business_key: Optional[str] = data.get("businessKey")
        self._variables: Dict[str, Any] = data.get("variables", {})
        self._raw_data = data

    @property
    def variables(self) -> Dict[str, Any]:
        """Get parsed variables from task."""
        parsed = {}
        for key, value_data in self._variables.items():
            if isinstance(value_data, dict) and "value" in value_data:
                parsed[key] = value_data["value"]
            else:
                parsed[key] = value_data
        return parsed

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a specific variable by name."""
        return self.variables.get(name, default)

    def __repr__(self) -> str:
        return f"ExternalTask(id={self.id}, topic={self.topic_name}, process={self.process_instance_id})"


class TaskResult:
    """Result of task execution."""

    def __init__(
        self,
        success: bool,
        variables: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        error_details: Optional[str] = None,
        bpmn_error_code: Optional[str] = None,
        bpmn_error_message: Optional[str] = None,
        retries: Optional[int] = None,
        retry_timeout: int = 10000
    ):
        self.success = success
        self.variables = variables or {}
        self.error_message = error_message
        self.error_details = error_details
        self.bpmn_error_code = bpmn_error_code
        self.bpmn_error_message = bpmn_error_message
        self.retries = retries
        self.retry_timeout = retry_timeout

    @classmethod
    def complete(cls, variables: Optional[Dict[str, Any]] = None) -> "TaskResult":
        """Create a successful completion result."""
        return cls(success=True, variables=variables)

    @classmethod
    def fail(
        cls,
        error_message: str,
        error_details: Optional[str] = None,
        retries: int = 0,
        retry_timeout: int = 10000
    ) -> "TaskResult":
        """Create a failure result with optional retry."""
        return cls(
            success=False,
            error_message=error_message,
            error_details=error_details,
            retries=retries,
            retry_timeout=retry_timeout
        )

    @classmethod
    def bpmn_error(
        cls,
        error_code: str,
        error_message: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> "TaskResult":
        """Create a BPMN error result for error boundary events."""
        return cls(
            success=False,
            bpmn_error_code=error_code,
            bpmn_error_message=error_message,
            variables=variables
        )


class BaseWorker(ABC):
    """
    Abstract base class for Camunda external task workers.

    Implements fetch-and-lock pattern with long polling.
    Subclasses must implement the `handle` method.
    """

    def __init__(
        self,
        topic_name: str,
        worker_id: Optional[str] = None,
        lock_duration: int = 60000,
        max_tasks: int = 1,
        long_polling_timeout: int = 30000,
        variables: Optional[List[str]] = None
    ):
        self.settings = get_settings()
        self.topic_name = topic_name
        self.worker_id = worker_id or f"{topic_name}-worker-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.lock_duration = lock_duration
        self.max_tasks = max_tasks
        self.long_polling_timeout = long_polling_timeout
        self.variables = variables  # Variables to fetch, None = all

        self._running = False
        self._client: Optional[httpx.AsyncClient] = None

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def camunda_url(self) -> str:
        """Get Camunda REST API URL."""
        return self.settings.camunda_rest_url

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(self.long_polling_timeout / 1000) + 10,
                    write=10.0,
                    pool=10.0
                )
            )
        return self._client

    @abstractmethod
    async def handle(self, task: ExternalTask) -> TaskResult:
        """
        Handle an external task.

        Subclasses must implement this method to process the task
        and return a TaskResult indicating success, failure, or BPMN error.

        Args:
            task: The external task to process

        Returns:
            TaskResult indicating the outcome
        """
        pass

    def _format_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Format variables for Camunda REST API."""
        formatted = {}
        for key, value in variables.items():
            if isinstance(value, bool):
                formatted[key] = {"value": value, "type": "Boolean"}
            elif isinstance(value, int):
                formatted[key] = {"value": value, "type": "Integer"}
            elif isinstance(value, float):
                formatted[key] = {"value": value, "type": "Double"}
            elif isinstance(value, dict) or isinstance(value, list):
                import json
                formatted[key] = {"value": json.dumps(value), "type": "Json"}
            else:
                formatted[key] = {"value": str(value), "type": "String"}
        return formatted

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _fetch_and_lock(self) -> List[ExternalTask]:
        """Fetch and lock external tasks from Camunda."""
        client = await self._get_client()

        payload = {
            "workerId": self.worker_id,
            "maxTasks": self.max_tasks,
            "asyncResponseTimeout": self.long_polling_timeout,
            "topics": [
                {
                    "topicName": self.topic_name,
                    "lockDuration": self.lock_duration,
                    "variables": self.variables
                }
            ]
        }

        try:
            response = await client.post(
                f"{self.camunda_url}/external-task/fetchAndLock",
                json=payload
            )
            response.raise_for_status()

            tasks_data = response.json()
            tasks = [ExternalTask(data) for data in tasks_data]

            if tasks:
                self.logger.info(f"Fetched {len(tasks)} task(s) for topic '{self.topic_name}'")

            return tasks

        except httpx.TimeoutException:
            # Long polling timeout is expected
            return []
        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error fetching tasks: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            self.logger.error(f"Error fetching tasks: {e}")
            raise

    async def _complete_task(self, task: ExternalTask, variables: Dict[str, Any]) -> bool:
        """Complete an external task successfully."""
        client = await self._get_client()

        payload = {
            "workerId": self.worker_id,
            "variables": self._format_variables(variables) if variables else {}
        }

        try:
            response = await client.post(
                f"{self.camunda_url}/external-task/{task.id}/complete",
                json=payload
            )
            response.raise_for_status()
            self.logger.info(f"Completed task {task.id} for topic '{task.topic_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Error completing task {task.id}: {e}")
            return False

    async def _fail_task(
        self,
        task: ExternalTask,
        error_message: str,
        error_details: Optional[str] = None,
        retries: int = 0,
        retry_timeout: int = 10000
    ) -> bool:
        """Report task failure with optional retry."""
        client = await self._get_client()

        payload = {
            "workerId": self.worker_id,
            "errorMessage": error_message[:500],  # Camunda limit
            "errorDetails": error_details[:4000] if error_details else None,
            "retries": retries,
            "retryTimeout": retry_timeout
        }

        try:
            response = await client.post(
                f"{self.camunda_url}/external-task/{task.id}/failure",
                json=payload
            )
            response.raise_for_status()
            self.logger.warning(f"Failed task {task.id}: {error_message} (retries={retries})")
            return True
        except Exception as e:
            self.logger.error(f"Error reporting task failure {task.id}: {e}")
            return False

    async def _bpmn_error(
        self,
        task: ExternalTask,
        error_code: str,
        error_message: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Report BPMN error for error boundary event handling."""
        client = await self._get_client()

        payload = {
            "workerId": self.worker_id,
            "errorCode": error_code,
            "errorMessage": error_message,
            "variables": self._format_variables(variables) if variables else {}
        }

        try:
            response = await client.post(
                f"{self.camunda_url}/external-task/{task.id}/bpmnError",
                json=payload
            )
            response.raise_for_status()
            self.logger.info(f"BPMN error {error_code} for task {task.id}")
            return True
        except Exception as e:
            self.logger.error(f"Error reporting BPMN error for task {task.id}: {e}")
            return False

    async def _process_task(self, task: ExternalTask) -> None:
        """Process a single task."""
        self.logger.info(f"Processing task {task.id} (topic={task.topic_name}, process={task.process_instance_id})")

        try:
            result = await self.handle(task)

            if result.success:
                await self._complete_task(task, result.variables)
            elif result.bpmn_error_code:
                await self._bpmn_error(
                    task,
                    result.bpmn_error_code,
                    result.bpmn_error_message,
                    result.variables
                )
            else:
                retries = result.retries if result.retries is not None else max(0, task.retries - 1)
                await self._fail_task(
                    task,
                    result.error_message or "Unknown error",
                    result.error_details,
                    retries,
                    result.retry_timeout
                )

        except Exception as e:
            self.logger.exception(f"Unhandled exception processing task {task.id}")
            retries = max(0, task.retries - 1)
            await self._fail_task(task, str(e), None, retries)

    async def run(self) -> None:
        """Start the worker polling loop."""
        self._running = True
        self.logger.info(f"Starting worker '{self.worker_id}' for topic '{self.topic_name}'")

        while self._running:
            try:
                tasks = await self._fetch_and_lock()

                for task in tasks:
                    await self._process_task(task)

            except Exception as e:
                self.logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def stop(self) -> None:
        """Stop the worker."""
        self.logger.info(f"Stopping worker '{self.worker_id}'")
        self._running = False

        if self._client:
            await self._client.aclose()
            self._client = None


class WorkerManager:
    """Manages multiple external task workers."""

    def __init__(self):
        self.workers: List[BaseWorker] = []
        self._tasks: List[asyncio.Task] = []
        self.logger = logging.getLogger(f"{__name__}.WorkerManager")

    def register(self, worker: BaseWorker) -> None:
        """Register a worker."""
        self.workers.append(worker)
        self.logger.info(f"Registered worker for topic '{worker.topic_name}'")

    async def start_all(self) -> None:
        """Start all registered workers."""
        self.logger.info(f"Starting {len(self.workers)} worker(s)")

        for worker in self.workers:
            task = asyncio.create_task(worker.run())
            self._tasks.append(task)

    async def stop_all(self) -> None:
        """Stop all workers."""
        self.logger.info("Stopping all workers")

        for worker in self.workers:
            await worker.stop()

        # Cancel tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()


# Global worker manager instance
_worker_manager: Optional[WorkerManager] = None


def get_worker_manager() -> WorkerManager:
    """Get or create the global worker manager."""
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager()
    return _worker_manager
