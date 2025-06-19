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
            
            # Get queue lengths for all queues
            queue_types = ["categorization", "preview", "email"]
            priorities = ["high", "default", "low"]
            stats = {}
            
            for queue_type in queue_types:
                for priority in priorities:
                    queue_name = f"{queue_type}:{priority}"
                    queue_length = await pool.zcard(f"arq:queue:{queue_name}")
                    stats[queue_name] = queue_length
            
            # Get job counts
            stats["completed"] = await pool.zcard("arq:results")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}
    
    async def enqueue_preview_generation(
        self,
        document_id: str,
        tenant_id: str,
        user_id: str,
        preview_type: str = "all",
        force_regenerate: bool = False,
        priority: str = "default"
    ) -> Optional[str]:
        """
        Enqueue document preview generation
        
        Args:
            document_id: Document ID
            tenant_id: Tenant ID
            user_id: User ID
            preview_type: Type of preview ("pdf", "thumbnail", "all")
            force_regenerate: Force regeneration even if preview exists
            priority: Job priority
            
        Returns:
            Job ID if successful
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'generate_document_preview',
                document_id,
                tenant_id,
                user_id,
                preview_type,
                force_regenerate,
                _queue_name=f"preview:{priority}",
                _job_try=2  # Retry once on failure
            )
            
            logger.info(f"Enqueued preview generation for document {document_id}, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue preview generation: {e}")
            return None
    
    async def enqueue_preview_batch(
        self,
        document_ids: List[str],
        tenant_id: str,
        user_id: str,
        preview_type: str = "all",
        batch_size: int = 5,
        priority: str = "default"
    ) -> Optional[str]:
        """
        Enqueue batch preview generation
        
        Args:
            document_ids: List of document IDs
            tenant_id: Tenant ID
            user_id: User ID
            preview_type: Type of preview
            batch_size: Concurrent processing size
            priority: Job priority
            
        Returns:
            Job ID if successful
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'generate_preview_batch',
                document_ids,
                tenant_id,
                user_id,
                preview_type,
                batch_size,
                _queue_name=f"preview:{priority}",
                _job_try=2
            )
            
            logger.info(f"Enqueued batch preview for {len(document_ids)} documents, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue batch preview: {e}")
            return None
    
    async def enqueue_email(
        self,
        to_email: str,
        subject: str,
        template_name: str,
        template_data: Dict[str, Any],
        priority: str = "default"
    ) -> Optional[str]:
        """
        Enqueue single email
        
        Args:
            to_email: Recipient email
            subject: Email subject
            template_name: Template to use
            template_data: Template variables
            priority: Job priority
            
        Returns:
            Job ID if successful
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'send_email',
                to_email,
                subject,
                template_name,
                template_data,
                0,  # retry_count
                _queue_name=f"email:{priority}",
                _job_try=3  # Retry up to 3 times
            )
            
            logger.info(f"Enqueued email to {to_email}, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue email: {e}")
            return None
    
    async def enqueue_bulk_emails(
        self,
        email_batch: List[Dict[str, Any]],
        batch_size: int = 10,
        priority: str = "low"
    ) -> Optional[str]:
        """
        Enqueue bulk email sending
        
        Args:
            email_batch: List of email data
            batch_size: Concurrent sending size
            priority: Job priority
            
        Returns:
            Job ID if successful
        """
        try:
            pool = await self.connect()
            
            job = await pool.enqueue_job(
                'send_bulk_emails',
                email_batch,
                batch_size,
                _queue_name=f"email:{priority}",
                _job_try=2
            )
            
            logger.info(f"Enqueued bulk email batch of {len(email_batch)} emails, job: {job.job_id}")
            return job.job_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue bulk emails: {e}")
            return None


# Global queue service instance
queue_service = QueueService()


async def get_queue_service() -> QueueService:
    """Dependency to get queue service"""
    return queue_service