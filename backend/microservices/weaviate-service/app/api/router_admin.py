"""
NexusRouter Admin API

Provides administrative endpoints for managing the NexusRouter:
- GET /router/status - Current router status and metrics
- POST /router/train - Trigger model training
- POST /router/reload - Hot-reload the model
- POST /router/test - Test classification on a query
- GET /router/metrics - Detailed classification metrics
- GET /router/versions - List available model versions

All endpoints require API key authentication.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/router",
    tags=["NexusRouter Admin"],
    dependencies=[Depends(verify_api_key)],
)


# =============================================================================
# Request/Response Models
# =============================================================================

class TrainRequest(BaseModel):
    """Request to trigger model training."""
    tenant_ids: Optional[List[str]] = Field(
        None,
        description="Specific tenant IDs to include (None = all tenants)"
    )
    force: bool = Field(
        False,
        description="Force training even if cooldown hasn't passed"
    )


class TrainResponse(BaseModel):
    """Response from training request."""
    status: str
    message: str
    task_id: Optional[str] = None
    version: Optional[str] = None


class TestRequest(BaseModel):
    """Request to test classification."""
    query: str = Field(..., description="Query text to classify")
    tenant_id: Optional[str] = Field(None, description="Tenant context")


class TestResponse(BaseModel):
    """Response from test classification."""
    query: str
    intent: str
    confidence: float
    entities: List[str]
    document_types: List[str]
    required_action: str
    model_version: Optional[str]
    classification_time_ms: float


class StatusResponse(BaseModel):
    """Router status response."""
    initialized: bool
    model_loaded: bool
    model_version: Optional[str]
    using_fallback: bool
    classifier_status: Dict[str, Any]
    extractor_status: Dict[str, Any]
    metrics: Dict[str, Any]


class MetricsResponse(BaseModel):
    """Detailed metrics response."""
    total_classifications: int
    classifications_by_intent: Dict[str, int]
    avg_confidence: float
    avg_latency_ms: float
    forced_searches: int
    direct_responses: int
    model_version: Optional[str]


class VersionInfo(BaseModel):
    """Model version information."""
    version: str
    is_current: bool
    accuracy: Optional[float]
    f1_score: Optional[float]
    created_at: Optional[str]


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=StatusResponse)
async def get_router_status():
    """
    Get current NexusRouter status.

    Returns status of classifier, extractor, and recent metrics.
    """
    try:
        from app.services.nexus_router import nexus_router

        status = nexus_router.get_status()

        return StatusResponse(
            initialized=status.get("initialized", False),
            model_loaded=status.get("classifier", {}).get("model_loaded", False),
            model_version=status.get("classifier", {}).get("model_version"),
            using_fallback=status.get("classifier", {}).get("using_fallback", True),
            classifier_status=status.get("classifier", {}),
            extractor_status=status.get("extractor", {}),
            metrics=status.get("metrics", {}),
        )

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="NexusRouter not available"
        )
    except Exception as e:
        logger.error(f"Error getting router status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting status: {str(e)}"
        )


@router.post("/train", response_model=TrainResponse)
async def trigger_training(request: TrainRequest):
    """
    Trigger NexusRouter model training.

    Training can run via:
    1. Background worker (async, preferred)
    2. Direct training (sync, fallback when worker unavailable)
    """
    import httpx
    from app.core.config import settings

    use_direct_training = False

    # Try to queue training via background worker
    try:
        worker_url = getattr(settings, "BACKGROUND_WORKER_URL", "http://background-worker:8100")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{worker_url}/api/tasks/router/train",
                json={
                    "tenant_ids": request.tenant_ids,
                    "force": request.force,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )

            if response.status_code == 200:
                data = response.json()
                return TrainResponse(
                    status="queued",
                    message="Training task queued successfully",
                    task_id=data.get("task_id"),
                )
            elif response.status_code == 404:
                # Endpoint doesn't exist in worker - use direct training
                logger.warning("Worker training endpoint not found, using direct training")
                use_direct_training = True
            else:
                return TrainResponse(
                    status="error",
                    message=f"Failed to queue training: {response.status_code}",
                )

    except httpx.ConnectError:
        logger.warning("Background worker not available, using direct training")
        use_direct_training = True
    except Exception as e:
        logger.warning(f"Worker request failed: {e}, using direct training")
        use_direct_training = True

    # Direct training fallback
    if use_direct_training:
        try:
            from app.services.nexus_router import (
                data_collector,
                dataset_builder,
                model_trainer,
            )
            from datetime import datetime

            logger.info("Starting direct model training...")

            # Initialize and collect data
            await data_collector.initialize()
            collected_data = await data_collector.collect_all(request.tenant_ids)

            # Build dataset
            dataset = dataset_builder.build_dataset(collected_data)

            # Train model
            version = datetime.now().strftime("v%Y%m%d_%H%M%S")
            model, metadata = model_trainer.train(dataset=dataset, version=version)

            return TrainResponse(
                status="completed",
                message=f"Training completed successfully (direct mode)",
                version=version,
            )

        except Exception as e:
            logger.error(f"Direct training failed: {e}")
            return TrainResponse(
                status="error",
                message=f"Training failed: {str(e)}",
            )


@router.post("/reload")
async def reload_model():
    """
    Hot-reload the NexusRouter model.

    Reloads the model from disk without service restart.
    Use after training to apply the new model.
    """
    try:
        from app.services.nexus_router import nexus_router

        success = await nexus_router.reload_model()

        if success:
            status = nexus_router.get_status()
            return {
                "status": "success",
                "message": "Model reloaded successfully",
                "model_version": status.get("classifier", {}).get("model_version"),
            }
        else:
            return {
                "status": "warning",
                "message": "Model reload completed but using fallback mode",
            }

    except Exception as e:
        logger.error(f"Error reloading model: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reloading model: {str(e)}"
        )


@router.post("/test", response_model=TestResponse)
async def test_classification(request: TestRequest):
    """
    Test classification on a query.

    Useful for debugging and validating classifications.
    """
    try:
        from app.services.nexus_router import nexus_router

        # Ensure initialized
        await nexus_router.initialize()

        # Classify the query
        classification = await nexus_router.classify(
            query=request.query,
            tenant_id=request.tenant_id,
        )

        return TestResponse(
            query=request.query,
            intent=classification.intent.value,
            confidence=classification.confidence,
            entities=classification.entities,
            document_types=classification.document_types,
            required_action=classification.required_action.value,
            model_version=classification.model_version,
            classification_time_ms=classification.classification_time_ms,
        )

    except Exception as e:
        logger.error(f"Error testing classification: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error classifying: {str(e)}"
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """
    Get detailed classification metrics.

    Returns aggregate metrics since service start.
    """
    try:
        from app.services.nexus_router import nexus_router

        metrics = nexus_router.get_metrics()
        status = nexus_router.get_status()

        return MetricsResponse(
            total_classifications=metrics.total_classifications,
            classifications_by_intent=metrics.classifications_by_intent,
            avg_confidence=metrics.avg_confidence,
            avg_latency_ms=metrics.avg_latency_ms,
            forced_searches=metrics.forced_searches,
            direct_responses=metrics.direct_responses,
            model_version=status.get("classifier", {}).get("model_version"),
        )

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting metrics: {str(e)}"
        )


@router.post("/metrics/reset")
async def reset_metrics():
    """
    Reset classification metrics.

    Clears all accumulated metrics.
    """
    try:
        from app.services.nexus_router import nexus_router

        nexus_router.reset_metrics()

        return {
            "status": "success",
            "message": "Metrics reset successfully",
        }

    except Exception as e:
        logger.error(f"Error resetting metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting metrics: {str(e)}"
        )


@router.get("/versions", response_model=List[VersionInfo])
async def list_versions():
    """
    List available model versions.

    Shows all trained model versions with their metrics.
    """
    try:
        from app.services.nexus_router import model_trainer

        versions = model_trainer.list_versions()

        return [
            VersionInfo(
                version=v["version"],
                is_current=v["is_current"],
                accuracy=v.get("accuracy"),
                f1_score=v.get("f1_score"),
                created_at=v.get("created_at"),
            )
            for v in versions
        ]

    except Exception as e:
        logger.error(f"Error listing versions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing versions: {str(e)}"
        )


@router.get("/data-stats")
async def get_data_statistics():
    """
    Get statistics about available training data.

    Shows document types, entity types, and counts.
    """
    try:
        from app.services.nexus_router import data_collector

        await data_collector.initialize()
        stats = await data_collector.get_collection_stats()

        return {
            "status": "success",
            "statistics": stats,
        }

    except Exception as e:
        logger.error(f"Error getting data statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting statistics: {str(e)}"
        )
