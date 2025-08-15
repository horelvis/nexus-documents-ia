"""
Background task for automatic reindexing of failed documents
"""
import asyncio
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.db.database import SessionLocal
from app.db.models import Tenant
from app.services.reindex_service import ReindexService

logger = logging.getLogger(__name__)


class AutoReindexTask:
    """Background task to automatically reindex failed documents for all tenants"""
    
    def __init__(self):
        self.is_running = False
        self.last_run = None
        self.run_interval = 300  # 5 minutes in seconds
        
    async def run_auto_reindex_for_all_tenants(self) -> Dict[str, Any]:
        """
        Run auto-reindex for all active tenants
        """
        if self.is_running:
            logger.info("Auto-reindex task already running, skipping")
            return {"status": "skipped", "reason": "already_running"}
        
        try:
            self.is_running = True
            self.last_run = datetime.now()
            
            logger.info("Starting auto-reindex task for all tenants")
            
            # Get all active tenants
            with SessionLocal() as db:
                tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
                
            if not tenants:
                logger.info("No active tenants found")
                return {"status": "completed", "tenants_processed": 0}
            
            results = []
            total_reindexed = 0
            
            # Process each tenant
            for tenant in tenants:
                try:
                    logger.info(f"Processing auto-reindex for tenant: {tenant.id}")
                    
                    reindex_service = ReindexService(tenant_id=str(tenant.id))
                    result = await reindex_service.auto_reindex_failed_documents()
                    
                    results.append({
                        "tenant_id": str(tenant.id),
                        "result": result
                    })
                    
                    if result.get("success_count", 0) > 0:
                        total_reindexed += result["success_count"]
                        logger.info(f"Auto-reindexed {result['success_count']} documents for tenant {tenant.id}")
                    
                except Exception as e:
                    logger.error(f"Error processing auto-reindex for tenant {tenant.id}: {str(e)}")
                    results.append({
                        "tenant_id": str(tenant.id),
                        "error": str(e)
                    })
            
            logger.info(f"Auto-reindex task completed. Total documents reindexed: {total_reindexed}")
            
            return {
                "status": "completed",
                "tenants_processed": len(tenants),
                "total_reindexed": total_reindexed,
                "results": results,
                "completed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in auto-reindex task: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            }
        finally:
            self.is_running = False
    
    async def start_periodic_task(self):
        """
        Start the periodic auto-reindex task
        """
        logger.info(f"Starting periodic auto-reindex task (interval: {self.run_interval}s)")
        
        while True:
            try:
                # Check if it's time to run
                if (self.last_run is None or 
                    datetime.now() - self.last_run >= timedelta(seconds=self.run_interval)):
                    
                    await self.run_auto_reindex_for_all_tenants()
                
                # Wait a bit before checking again
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in periodic auto-reindex task: {str(e)}")
                await asyncio.sleep(60)


# Global instance
auto_reindex_task = AutoReindexTask()