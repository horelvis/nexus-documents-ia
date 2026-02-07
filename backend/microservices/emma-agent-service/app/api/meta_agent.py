"""
Meta Agent API Endpoints

REST API for managing the ADAS-inspired meta agent system:
- Archive: View and manage discovered strategies
- Search: Trigger and monitor search loops
- Test Sets: Manage evaluation test cases
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meta-agent", dependencies=[Depends(verify_api_key)])


# =============================================================================
# Request/Response schemas
# =============================================================================

class RunSearchRequest(BaseModel):
    intent_target: str = Field(description="Intent to optimize for")
    sector_target: Optional[str] = Field(default=None, description="Optional sector")
    test_set_id: str = Field(description="Test set ID to use")
    max_iterations: Optional[int] = Field(default=None, description="Override max iterations")
    candidates_per_iteration: Optional[int] = Field(default=None, description="Override candidates count")


class TestQueryRequest(BaseModel):
    query: str = Field(description="Test query to run against strategy")


class FeedbackRequest(BaseModel):
    strategy_id: str
    latency_s: float = 0.0
    thumbs_up: bool = False
    thumbs_down: bool = False


# =============================================================================
# Archive endpoints
# =============================================================================

@router.get("/archive/stats")
async def get_archive_stats():
    """Get archive-wide statistics."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    return await archive.get_stats()


@router.get("/archive/strategies")
async def list_strategies(
    intent: Optional[str] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
):
    """List top strategies, optionally filtered by intent/sector."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()

    if intent:
        entries = await archive.get_top_strategies(intent, sector, limit=limit)
    else:
        # Get stats to find all intents, then aggregate
        stats = await archive.get_stats()
        entries = []
        for intent_key in stats.get("by_intent", {}):
            top = await archive.get_top_strategies(intent_key, sector, limit=limit)
            entries.extend(top)
        entries.sort(key=lambda e: e.metrics.composite_score, reverse=True)
        entries = entries[:limit]

    return {
        "strategies": [
            {
                "id": e.strategy.id,
                "name": e.strategy.name,
                "intent_target": e.strategy.intent_target,
                "sector_target": e.strategy.sector_target,
                "description": e.strategy.description,
                "generation": e.strategy.generation,
                "composite_score": e.metrics.composite_score,
                "answer_quality": e.metrics.answer_quality,
                "efficiency": e.metrics.efficiency,
                "success_rate": e.metrics.success_rate,
                "production_uses": e.production_uses,
                "is_active": e.is_active,
                "is_default": e.is_default,
            }
            for e in entries
        ],
        "total": len(entries),
    }


@router.get("/archive/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get full strategy details including metrics and code."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    entry = await archive.get_entry(strategy_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return entry.model_dump()


@router.get("/archive/strategies/{strategy_id}/code")
async def get_strategy_code(strategy_id: str):
    """Get raw code of a strategy."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    entry = await archive.get_entry(strategy_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "id": strategy_id,
        "name": entry.strategy.name,
        "code": entry.strategy.code,
    }


@router.post("/archive/strategies/{strategy_id}/promote")
async def promote_strategy(strategy_id: str):
    """Promote a strategy to default for its intent+sector.

    Runs validation if test cases are available. Only promotes if
    validation_score >= 85% of discovery_score.
    """
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    entry = await archive.get_entry(strategy_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Try to run validation
    from app.services.meta_agent.test_sets import get_test_sets_for_intent
    test_sets = get_test_sets_for_intent(
        entry.strategy.intent_target, entry.strategy.sector_target
    )

    validation_score = None
    if test_sets and test_sets[0].validation_cases:
        from app.services.meta_agent.runner import StrategyRunner
        from app.services.meta_agent.evaluator import StrategyEvaluator

        runner = StrategyRunner()
        evaluator = StrategyEvaluator()
        run_result = await runner.run_test_set(
            entry.strategy, test_sets[0].validation_cases
        )
        metrics = await evaluator.evaluate(
            entry.strategy, run_result, test_sets[0].validation_cases
        )
        validation_score = metrics.composite_score

    success = await archive.promote_to_default(strategy_id, validation_score)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Promotion failed — validation score too low or strategy not found"
        )

    return {"status": "promoted", "validation_score": validation_score}


@router.post("/archive/strategies/{strategy_id}/deactivate")
async def deactivate_strategy(strategy_id: str):
    """Remove a strategy from online selection."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    success = await archive.deactivate_strategy(strategy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"status": "deactivated"}


@router.post("/archive/strategies/{strategy_id}/test")
async def test_strategy(strategy_id: str, request: TestQueryRequest):
    """Run a strategy against a single query for testing."""
    from app.services.meta_agent.archive import get_strategy_archive
    from app.services.meta_agent.runner import StrategyRunner
    from app.services.meta_agent.schemas import TestCase

    archive = get_strategy_archive()
    entry = await archive.get_entry(strategy_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Strategy not found")

    runner = StrategyRunner()
    case = TestCase(
        query=request.query,
        intent=entry.strategy.intent_target,
        sector=entry.strategy.sector_target,
    )
    result = await runner.run_test_set(entry.strategy, [case])

    if result.case_results:
        cr = result.case_results[0]
        return {
            "success": cr.success,
            "answer": cr.answer,
            "sources": cr.sources,
            "llm_calls": cr.llm_calls,
            "tool_calls": cr.tool_calls,
            "latency_s": cr.latency_s,
            "reasoning_steps": cr.reasoning_steps,
            "error": cr.error,
        }
    return {"success": False, "error": "No results"}


# =============================================================================
# Search endpoints
# =============================================================================

@router.post("/search/run")
async def run_search(request: RunSearchRequest, background_tasks: BackgroundTasks):
    """Trigger a search loop (runs in background)."""
    from app.services.meta_agent.test_sets import get_test_set
    from app.services.meta_agent.search_loop import MetaAgentSearchLoop
    from app.services.meta_agent.schemas import SearchJob

    test_set = get_test_set(request.test_set_id)
    if not test_set:
        raise HTTPException(status_code=404, detail=f"Test set '{request.test_set_id}' not found")

    # Create job record
    job = SearchJob(
        intent_target=request.intent_target,
        sector_target=request.sector_target,
        test_set_id=request.test_set_id,
        max_iterations=request.max_iterations or settings.meta_agent_max_search_iterations,
        candidates_per_iteration=request.candidates_per_iteration or settings.meta_agent_candidates_per_iteration,
        status="queued",
    )

    # Store initial job state
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    await archive.store_search_job(job)

    # Run in background (Starlette natively awaits async tasks)
    async def _run():
        loop = MetaAgentSearchLoop()
        await loop.run(
            test_set=test_set,
            intent_target=request.intent_target,
            sector_target=request.sector_target,
            max_iterations=request.max_iterations,
            candidates_per_iteration=request.candidates_per_iteration,
            job_id=job.job_id,
        )

    background_tasks.add_task(_run)

    return {
        "job_id": job.job_id,
        "status": "queued",
        "test_set_id": request.test_set_id,
        "intent_target": request.intent_target,
        "sector_target": request.sector_target,
    }


@router.get("/search/status/{job_id}")
async def get_search_status(job_id: str):
    """Get search job status."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    job = await archive.get_search_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found")
    return job.model_dump()


@router.get("/search/history")
async def get_search_history(limit: int = Query(default=10, ge=1, le=50)):
    """Get recent search job history."""
    from app.services.meta_agent.archive import get_strategy_archive
    archive = get_strategy_archive()
    jobs = await archive.get_search_history(limit=limit)
    return {"jobs": [j.model_dump() for j in jobs]}


# =============================================================================
# Test set endpoints
# =============================================================================

@router.get("/test-sets")
async def list_test_sets():
    """List available test sets."""
    from app.services.meta_agent.test_sets import ALL_TEST_SETS
    return {
        "test_sets": [
            {
                "id": ts.id,
                "name": ts.name,
                "intent": ts.intent,
                "sector": ts.sector,
                "discovery_cases": len(ts.discovery_cases),
                "validation_cases": len(ts.validation_cases),
            }
            for ts in ALL_TEST_SETS
        ]
    }


@router.get("/test-sets/{test_set_id}")
async def get_test_set_detail(test_set_id: str):
    """Get test set details including cases."""
    from app.services.meta_agent.test_sets import get_test_set
    ts = get_test_set(test_set_id)
    if not ts:
        raise HTTPException(status_code=404, detail="Test set not found")
    return ts.model_dump()


# =============================================================================
# Feedback endpoint
# =============================================================================

@router.post("/feedback")
async def record_feedback(request: FeedbackRequest):
    """Record production feedback for a strategy."""
    if not settings.meta_agent_feedback_enabled:
        raise HTTPException(status_code=400, detail="Feedback collection is disabled")

    from app.services.meta_agent.feedback_collector import get_feedback_collector
    collector = get_feedback_collector()
    await collector.record_feedback(
        strategy_id=request.strategy_id,
        latency_s=request.latency_s,
        thumbs_up=request.thumbs_up,
        thumbs_down=request.thumbs_down,
    )
    return {"status": "recorded"}
