"""Temporalio Worker Manager"""
from temporalio.worker import Worker
from temporalio.runtime import Runtime
from typing import Optional, Dict, Any
import asyncio
import logging

from app.core.config import settings
from app.core.temporalio_client import temporalio_client
from app.workflows.dynamic_workflow import DynamicWorkflow
from app.workers.activity_loader import get_all_workflow_activities

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages Temporalio workers and their lifecycle"""
    
    def __init__(self):
        self._workers: Dict[str, Worker] = {}
        self._worker_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
    
    async def start(self) -> None:
        """Start all workers"""
        if self._running:
            logger.warning("Worker manager already running")
            return
        
        try:
            logger.info("🏗️ Starting Temporalio workers...")
            
            # Ensure client is initialized
            if not temporalio_client.is_initialized:
                await temporalio_client.initialize()
            
            # Start main workflow worker
            await self._start_main_worker()
            
            # Start specialized workers if needed
            # await self._start_document_worker()
            
            self._running = True
            logger.info("✅ All Temporalio workers started successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to start workers: {e}")
            await self.shutdown()
            raise
    
    async def _start_main_worker(self) -> None:
        """Start main workflow worker"""
        try:
            # Get all available activities
            all_activities = get_all_workflow_activities()
            
            # Create worker with all workflows and activities
            worker = Worker(
                temporalio_client.client,
                task_queue=settings.temporalio_task_queue,
                workflows=[
                    DynamicWorkflow,  # Dynamic workflow for templates
                ],
                activities=all_activities,
                max_concurrent_activities=settings.worker_max_concurrent_activities,
                max_concurrent_workflow_tasks=settings.worker_max_concurrent_workflows,
            )
            
            # Store worker reference
            self._workers["main"] = worker
            
            # Start worker in background task
            self._worker_tasks["main"] = asyncio.create_task(
                worker.run(),
                name="main-worker"
            )
            
            logger.info(f"✅ Main worker started on task queue: {settings.temporalio_task_queue}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start main worker: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown all workers"""
        if not self._running:
            return
        
        try:
            logger.info("🔄 Shutting down Temporalio workers...")
            
            # Cancel all worker tasks
            for name, task in self._worker_tasks.items():
                if not task.done():
                    logger.info(f"Cancelling {name} worker...")
                    task.cancel()
                    
                    try:
                        await asyncio.wait_for(task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        logger.info(f"{name} worker cancelled")
                    except Exception as e:
                        logger.error(f"Error cancelling {name} worker: {e}")
            
            # Clear references
            self._workers.clear()
            self._worker_tasks.clear()
            self._running = False
            
            logger.info("✅ All workers shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during worker shutdown: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if workers are running"""
        return self._running
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on workers"""
        try:
            if not self._running:
                return {
                    "status": "unhealthy",
                    "error": "Workers not running"
                }
            
            # Check if worker tasks are still running
            running_workers = {}
            failed_workers = {}
            
            for name, task in self._worker_tasks.items():
                if task.done():
                    if task.exception():
                        failed_workers[name] = str(task.exception())
                    else:
                        failed_workers[name] = "Task completed unexpectedly"
                else:
                    running_workers[name] = "running"
            
            if failed_workers:
                return {
                    "status": "unhealthy",
                    "running_workers": running_workers,
                    "failed_workers": failed_workers
                }
            
            return {
                "status": "healthy",
                "running_workers": running_workers,
                "task_queue": settings.temporalio_task_queue,
                "max_concurrent_activities": settings.worker_max_concurrent_activities,
                "max_concurrent_workflows": settings.worker_max_concurrent_workflows
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global worker manager instance
worker_manager = WorkerManager()