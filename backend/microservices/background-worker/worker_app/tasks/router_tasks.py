"""
Celery tasks for NexusRouter training and management.

Tasks:
- train_nexus_router_task: Train/retrain the NexusRouter model
- check_router_retraining_needed: Check if retraining is needed based on new data
- reload_nexus_router_model: Hot-reload the model without service restart

These tasks are triggered:
1. Manually via admin API
2. Automatically after connector sync (post-sync hook)
3. On schedule (e.g., weekly retraining)
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from worker_app.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine in the Celery task context."""
    return asyncio.run(coro)


# =============================================================================
# NexusRouter Training Configuration
# =============================================================================

# Minimum thresholds for triggering automatic retraining
MIN_NEW_DOCUMENTS_FOR_RETRAIN = 100
MIN_NEW_QUERIES_FOR_RETRAIN = 50
RETRAIN_COOLDOWN_HOURS = 24

# Redis keys for tracking
ROUTER_LAST_TRAIN_KEY = "nexus_router:last_train_timestamp"
ROUTER_DOCS_SINCE_TRAIN_KEY = "nexus_router:docs_since_last_train"
ROUTER_QUERIES_SINCE_TRAIN_KEY = "nexus_router:queries_since_last_train"


# =============================================================================
# Training Task
# =============================================================================

async def _train_nexus_router(
    tenant_ids: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Train or retrain the NexusRouter model.

    Args:
        tenant_ids: Specific tenants to include (None = all tenants)
        force: Force training even if cooldown hasn't passed

    Returns:
        Dict with training results
    """
    import redis.asyncio as redis

    try:
        # Import NexusRouter components
        from app.services.nexus_router import (
            data_collector,
            dataset_builder,
            model_trainer,
        )

        # Check cooldown unless forced
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

        if not force:
            last_train = await redis_client.get(ROUTER_LAST_TRAIN_KEY)
            if last_train:
                last_train_dt = datetime.fromisoformat(last_train)
                cooldown_end = last_train_dt + timedelta(hours=RETRAIN_COOLDOWN_HOURS)
                if datetime.now(timezone.utc) < cooldown_end:
                    logger.info(
                        f"Training cooldown active until {cooldown_end}. "
                        f"Use force=True to override."
                    )
                    return {
                        "status": "skipped",
                        "reason": "cooldown_active",
                        "cooldown_ends": cooldown_end.isoformat(),
                    }

        logger.info(f"Starting NexusRouter training for tenants: {tenant_ids or 'all'}")

        # 1. Collect training data
        await data_collector.initialize()
        collected_data = await data_collector.collect_all(tenant_ids)

        stats = collected_data.get("statistics", {})
        logger.info(
            f"Collected: {stats.get('total_historical_queries', 0)} queries, "
            f"{stats.get('total_documents', 0)} documents, "
            f"{stats.get('total_entities', 0)} entities"
        )

        # 2. Build training dataset
        dataset = dataset_builder.build_dataset(
            collected_data,
            include_synthetic=True,
            include_manual=True,
        )

        logger.info(
            f"Built dataset: {len(dataset.train_examples)} train, "
            f"{len(dataset.eval_examples)} eval"
        )

        # 3. Train model
        version = datetime.now().strftime("v%Y%m%d_%H%M%S")
        model, metadata = model_trainer.train(
            dataset=dataset,
            version=version,
        )

        # 4. Update tracking in Redis
        await redis_client.set(
            ROUTER_LAST_TRAIN_KEY,
            datetime.now(timezone.utc).isoformat(),
        )
        await redis_client.set(ROUTER_DOCS_SINCE_TRAIN_KEY, 0)
        await redis_client.set(ROUTER_QUERIES_SINCE_TRAIN_KEY, 0)

        # 5. Cleanup old versions
        removed = model_trainer.cleanup_old_versions(keep_versions=3)
        if removed > 0:
            logger.info(f"Cleaned up {removed} old model versions")

        await redis_client.close()

        result = {
            "status": "success",
            "version": version,
            "accuracy": metadata.accuracy,
            "f1_score": metadata.f1_score,
            "training_examples": metadata.training_examples,
            "eval_examples": metadata.eval_examples,
            "examples_per_intent": metadata.examples_per_intent,
            "sources": metadata.sources,
            "tenant_ids": tenant_ids,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"NexusRouter training complete: {version} (accuracy: {metadata.accuracy:.4f})")

        return result

    except ImportError as e:
        logger.error(f"NexusRouter dependencies not available: {e}")
        return {
            "status": "error",
            "error": f"Dependencies not available: {e}",
        }
    except Exception as e:
        logger.exception(f"NexusRouter training failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@celery_app.task(name="router.train", bind=True, max_retries=2)
def train_nexus_router_task(
    self,
    tenant_ids: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Celery task to train the NexusRouter model.

    Args:
        tenant_ids: Specific tenants to include
        force: Force training even if cooldown hasn't passed

    Returns:
        Dict with training results
    """
    try:
        return _run_async(_train_nexus_router(tenant_ids, force))
    except Exception as exc:
        logger.exception(f"NexusRouter training task failed: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry after 5 minutes


# =============================================================================
# Check Retraining Needed
# =============================================================================

async def _check_retraining_needed() -> Dict[str, Any]:
    """
    Check if NexusRouter retraining is needed based on new data.

    Checks:
    1. Number of new documents since last training
    2. Number of new queries since last training
    3. Time since last training

    Returns:
        Dict with check results and recommendation
    """
    import redis.asyncio as redis

    try:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

        # Get tracking values
        docs_since_train = int(await redis_client.get(ROUTER_DOCS_SINCE_TRAIN_KEY) or 0)
        queries_since_train = int(await redis_client.get(ROUTER_QUERIES_SINCE_TRAIN_KEY) or 0)
        last_train = await redis_client.get(ROUTER_LAST_TRAIN_KEY)

        last_train_dt = None
        hours_since_train = None
        if last_train:
            last_train_dt = datetime.fromisoformat(last_train)
            hours_since_train = (datetime.now(timezone.utc) - last_train_dt).total_seconds() / 3600

        await redis_client.close()

        # Determine if retraining is needed
        needs_retrain = False
        reasons = []

        if docs_since_train >= MIN_NEW_DOCUMENTS_FOR_RETRAIN:
            needs_retrain = True
            reasons.append(f"new_documents: {docs_since_train}")

        if queries_since_train >= MIN_NEW_QUERIES_FOR_RETRAIN:
            needs_retrain = True
            reasons.append(f"new_queries: {queries_since_train}")

        # Check if cooldown has passed
        cooldown_passed = True
        if hours_since_train is not None and hours_since_train < RETRAIN_COOLDOWN_HOURS:
            cooldown_passed = False

        return {
            "needs_retrain": needs_retrain and cooldown_passed,
            "reasons": reasons,
            "docs_since_train": docs_since_train,
            "queries_since_train": queries_since_train,
            "last_train": last_train,
            "hours_since_train": hours_since_train,
            "cooldown_passed": cooldown_passed,
            "thresholds": {
                "min_docs": MIN_NEW_DOCUMENTS_FOR_RETRAIN,
                "min_queries": MIN_NEW_QUERIES_FOR_RETRAIN,
                "cooldown_hours": RETRAIN_COOLDOWN_HOURS,
            }
        }

    except Exception as e:
        logger.error(f"Error checking retraining need: {e}")
        return {
            "needs_retrain": False,
            "error": str(e),
        }


@celery_app.task(name="router.check_retraining")
def check_router_retraining_needed_task() -> Dict[str, Any]:
    """
    Celery task to check if NexusRouter retraining is needed.

    If retraining is needed, automatically triggers the training task.

    Returns:
        Dict with check results
    """
    result = _run_async(_check_retraining_needed())

    if result.get("needs_retrain"):
        logger.info(f"NexusRouter retraining triggered: {result.get('reasons')}")
        train_nexus_router_task.delay()

    return result


# =============================================================================
# Post-Sync Hook: Increment Document Counter
# =============================================================================

async def _increment_docs_since_train(count: int = 1) -> int:
    """
    Increment the document counter after sync.

    Called by connector tasks after successful sync.

    Args:
        count: Number of documents synced

    Returns:
        New total count
    """
    import redis.asyncio as redis

    try:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )

        new_count = await redis_client.incrby(ROUTER_DOCS_SINCE_TRAIN_KEY, count)
        await redis_client.close()

        logger.debug(f"NexusRouter: {count} new docs synced, total since train: {new_count}")
        return new_count

    except Exception as e:
        logger.warning(f"Failed to increment docs counter: {e}")
        return 0


@celery_app.task(name="router.increment_docs")
def increment_docs_since_train_task(count: int = 1) -> Dict[str, Any]:
    """
    Celery task to increment document counter after sync.

    Called as a post-sync hook from connector tasks.

    Args:
        count: Number of documents synced

    Returns:
        Dict with new count
    """
    new_count = _run_async(_increment_docs_since_train(count))

    # If threshold reached, check for retraining
    if new_count >= MIN_NEW_DOCUMENTS_FOR_RETRAIN:
        check_router_retraining_needed_task.delay()

    return {"new_count": new_count, "threshold": MIN_NEW_DOCUMENTS_FOR_RETRAIN}


# =============================================================================
# Model Reload Task
# =============================================================================

async def _notify_model_reload() -> Dict[str, Any]:
    """
    Notify weaviate-service to reload the NexusRouter model.

    This is called after training completes to hot-reload the model
    without requiring a service restart.

    Returns:
        Dict with reload status
    """
    import httpx

    try:
        # Call weaviate-service API to reload model
        weaviate_service_url = settings.get("WEAVIATE_SERVICE_URL", "http://weaviate-service:8007")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{weaviate_service_url}/router/reload",
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if response.status_code == 200:
                logger.info("NexusRouter model reload triggered successfully")
                return {"status": "success", "reloaded": True}
            else:
                logger.warning(f"Model reload request failed: {response.status_code}")
                return {"status": "failed", "status_code": response.status_code}

    except Exception as e:
        logger.error(f"Failed to notify model reload: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task(name="router.reload_model")
def reload_nexus_router_model_task() -> Dict[str, Any]:
    """
    Celery task to trigger model reload in weaviate-service.

    Called after training completes.

    Returns:
        Dict with reload status
    """
    return _run_async(_notify_model_reload())
