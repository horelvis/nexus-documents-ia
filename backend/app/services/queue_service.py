"""
Queue Service for managing background tasks
"""
import logging
from typing import List, Dict, Any, Optional
from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueueService:
    """Service for managing background task queues"""
    
    def __init__(self):
        self.redis_settings = RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            database=0,
        )
        self._pool: Optional[ArqRedis] = None
    
    async def connect(self):
        """Connect to Redis pool"""
        if not self._pool:
            self._pool = await create_pool(self.redis_settings)
        return self._pool
    
    async def disconnect(self):
        """Disconnect from Redis pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    async def enqueue_document_categorization(
        self,
        document_id: str,
        tenant_id: str,
        user_id: str,
        priority: str = "default"
    ) -> Optional[str]:
        """
        Enqueue a single document for categorization
        
        Args:
            document_id: Document ID to categorize
            tenant_id: Tenant ID
            user_id: User ID who triggered the categorization
            priority: Job priority (high, default, low)
            
        Returns:
            Job ID if successful, None otherwise
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'categorize_document',
                document_id,
                tenant_id,
                user_id,
                _queue_name=f"categorization:{priority}",
                _job_try=3  # Retry up to 3 times
            )
            
            logger.info(f"Enqueued document {document_id} for categorization, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue document categorization: {e}")
            return None
    
    async def enqueue_batch_categorization(
        self,
        document_ids: List[str],
        tenant_id: str,
        user_id: str,
        batch_size: int = 10,
        priority: str = "default"
    ) -> Optional[str]:
        """
        Enqueue multiple documents for batch categorization
        
        Args:
            document_ids: List of document IDs to categorize
            tenant_id: Tenant ID
            user_id: User ID who triggered the categorization
            batch_size: Number of documents to process concurrently
            priority: Job priority
            
        Returns:
            Job ID if successful, None otherwise
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'categorize_document_batch',
                document_ids,
                tenant_id,
                user_id,
                batch_size,
                _queue_name=f"categorization:{priority}",
                _job_try=3
            )
            
            logger.info(f"Enqueued batch of {len(document_ids)} documents for categorization, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue batch categorization: {e}")
            return None
    
    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a job
        
        Args:
            job_id: Job ID to check
            
        Returns:
            Job status dict or None
        """
        try:
            pool = await self.connect()
            job = await pool.job_status(job_id)
            
            if job:
                return {
                    "job_id": job_id,
                    "status": job.status,
                    "result": job.result,
                    "error": job.error,
                    "start_time": job.start_time,
                    "finish_time": job.finish_time
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return None
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about the queues"""
        try:
            pool = await self.connect()
            
            # Get queue lengths
            queues = ["categorization:high", "categorization:default", "categorization:low"]
            stats = {}
            
            for queue_name in queues:
                queue_length = await pool.zcard(f"arq:queue:{queue_name}")
                stats[queue_name] = queue_length
            
            # Get job counts
            stats["completed"] = await pool.zcard("arq:results")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}


# Global queue service instance
queue_service = QueueService()


async def get_queue_service() -> QueueService:
    """Dependency to get queue service"""
    return queue_service