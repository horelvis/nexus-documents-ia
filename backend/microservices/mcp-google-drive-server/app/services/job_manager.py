"""
In-memory async job manager for background tasks.

Identical to mcp-alfresco-server job_manager.py.
Manages sync and indexing jobs launched via asyncio.create_task().
Job state is stored in-memory (lost on restart, acceptable for on-premise).
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobState(BaseModel):
    """State of an async job."""
    job_id: str
    job_type: str
    status: JobStatus = JobStatus.RUNNING
    progress: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class JobManager:
    """In-memory async job manager."""

    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start_job(
        self,
        job_type: str,
        coro_func: Callable[..., Coroutine],
        params: Dict[str, Any],
    ) -> str:
        # Prevent duplicate: reject if same job_type + connector_id is already running
        connector_id = params.get("connector_id")
        if connector_id:
            for existing in self._jobs.values():
                if (
                    existing.status == JobStatus.RUNNING
                    and existing.job_type == job_type
                    and existing.params.get("connector_id") == connector_id
                ):
                    logger.warning(
                        f"Job {existing.job_id} ({job_type}) already running for connector {connector_id}"
                    )
                    return existing.job_id

        job_id = str(uuid.uuid4())[:8]
        state = JobState(
            job_id=job_id,
            job_type=job_type,
            params=params,
        )
        self._jobs[job_id] = state

        async def _run():
            try:
                result = await coro_func(state, **params)
                state.status = JobStatus.COMPLETED
                state.result = result
            except Exception as e:
                logger.exception(f"Job {job_id} ({job_type}) failed: {e}")
                state.status = JobStatus.FAILED
                state.error = str(e)
            finally:
                state.completed_at = datetime.now(timezone.utc)

        task = asyncio.create_task(_run())
        self._tasks[job_id] = task

        logger.info(f"Started job {job_id} ({job_type}) with params: {params}")
        return job_id

    def get_job(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

    def list_jobs(self, job_type: Optional[str] = None) -> List[JobState]:
        jobs = list(self._jobs.values())
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        jobs.sort(key=lambda j: j.started_at, reverse=True)
        return jobs

    def cleanup_old_jobs(self, max_completed: int = 100):
        completed = [
            j for j in self._jobs.values()
            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        completed.sort(key=lambda j: j.completed_at or j.started_at)
        while len(completed) > max_completed:
            old = completed.pop(0)
            self._jobs.pop(old.job_id, None)
            self._tasks.pop(old.job_id, None)


# Singleton
job_manager = JobManager()
