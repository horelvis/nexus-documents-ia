#!/usr/bin/env python
"""
Start ARQ worker for background tasks
"""
import asyncio
import logging
from arq import run_worker

from app.workers.categorization_worker import WorkerSettings
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def startup(ctx):
    """Startup function for worker"""
    logger.info("Starting categorization worker...")
    logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    logger.info(f"Microservices API: {settings.LANGCHAIN_SERVICE_URL}")


async def shutdown(ctx):
    """Shutdown function for worker"""
    logger.info("Shutting down categorization worker...")


if __name__ == "__main__":
    logger.info("Categorization Worker Starting...")
    
    # Run worker
    run_worker(
        WorkerSettings,
        startup=startup,
        shutdown=shutdown
    )