"""
Predictive Analysis Service — Sector-Agnostic Prediction.

This package implements predictive analysis where each factor is extracted,
verified against documents, weighted, and aggregated into a prediction.

Components:
- PredictiveAnalysisService: Orchestrates the stop-and-go factor loop
- FactorAgent: Extracts factors using LLM (sector-parametrized)
- OutcomeExtractor: Evaluates each match → sector outcome labels
- PredictionSynthesizer: Aggregates factors into probability + recommendation
- PredictiveCache: Redis-backed storage for factors and results

Usage:
    from app.services.predictive_analysis import (
        get_predictive_analysis_service,
        PredictiveAnalysisService,
    )

    service = get_predictive_analysis_service()
    async for event in service.analyze(request):
        yield event.to_sse()
"""

from .predictive_cache import (
    PredictiveCache,
    get_predictive_cache,
    initialize_predictive_cache,
)
from .factor_agent import (
    FactorAgent,
    get_factor_agent,
)
from .service import (
    PredictiveAnalysisService,
    get_predictive_analysis_service,
    initialize_predictive_analysis_service,
)

__all__ = [
    # Cache
    "PredictiveCache",
    "get_predictive_cache",
    "initialize_predictive_cache",
    # Factor Agent
    "FactorAgent",
    "get_factor_agent",
    # Service
    "PredictiveAnalysisService",
    "get_predictive_analysis_service",
    "initialize_predictive_analysis_service",
]
