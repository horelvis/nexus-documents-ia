#!/usr/bin/env python
"""
Start ARQ worker for background tasks
"""
import asyncio
import logging
import sys
from arq import run_worker

# Import the appropriate worker based on command line argument
worker_type = sys.argv[1] if len(sys.argv) > 1 else "unified"

if worker_type == "categorization":
    from app.workers.categorization_worker import WorkerSettings
    worker_name = "Categorization Worker"
elif worker_type == "preview":
    from app.workers.preview_worker import WorkerSettings
    worker_name = "Preview Worker"
elif worker_type == "email":
    from app.workers.email_worker import WorkerSettings
    worker_name = "Email Worker"
else:
    from app.workers.unified_worker import WorkerSettings
    worker_name = "Unified Worker"

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def startup(ctx):
    """Startup function for worker"""
    logger.info(f"Starting {worker_name}...")
    logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    logger.info(f"Microservices API: {settings.LANGCHAIN_SERVICE_URL}")
    logger.info(f"Worker type: {worker_type}")


async def shutdown(ctx):
    """Shutdown function for worker"""
    logger.info(f"Shutting down {worker_name}...")


if __name__ == "__main__":
    logger.info(f"{worker_name} Starting...")
    
    # Run worker
    run_worker(
        WorkerSettings,
        startup=startup,
        shutdown=shutdown
    )