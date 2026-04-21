"""
PredictiveStrategy — wraps FactorAgent, OutcomeExtractor, PredictiveCache,
and PredictionSynthesizer for the stop-and-go graph.

Moved from stop_and_go/strategies/

This strategy does NOT own any LLM logic — it delegates to the same
existing modules that the old while-loop used. The graph just
orchestrates the flow.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

from app.schemas.predictive_analysis import (
    PredictionFactor,
    WeightedFactor,
)
from app.agents.langgraph.sectors.predictive_config import (
    PredictiveConfig,
    get_predictive_config,
)

logger = logging.getLogger(__name__)


class PredictiveStrategy:
    """Strategy implementation for predictive analysis mode."""

    def __init__(self):
        self._factor_agent = None
        self._cache = None
        self._config: PredictiveConfig | None = None

    @property
    def mode(self) -> str:
        return "predictive"

    async def initialize(self, state: dict) -> None:
        """Lazy-init factor agent and cache."""
        from app.services.predictive_analysis.factor_agent import get_factor_agent
        from app.services.predictive_analysis.predictive_cache import get_predictive_cache

        if self._factor_agent is None:
            self._factor_agent = get_factor_agent()
        if self._cache is None:
            self._cache = get_predictive_cache()
            await self._cache.connect()

        # Resolve sector config from mode_config
        sector_override = state.get("mode_config", {}).get("sector_override")
        self._config = get_predictive_config(sector_override)

        # Clear prior session
        await self._cache.clear_session("", state["session_id"])

        # Store session metadata
        from datetime import datetime, timezone
        await self._cache.store_session_metadata(
            "",
            state["session_id"],
            {
                "case_description": state["query"],
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "session_id": state["session_id"],
                "sector": self._config.system_prompt_key,
            },
        )

    async def extract_item(self, state: dict, source_context: str) -> Dict[str, Any]:
        """Extract next factor via FactorAgent."""
        # Get existing weighted factors from Redis for LLM context
        existing_factors = await self._cache.get_weighted_factors(
            "", state["session_id"]
        )

        # Build rejected factors list from all_extracted_items
        all_items = state.get("all_extracted_items", [])
        rejected_factors = [
            PredictionFactor(**item["_raw_factor"])
            for item in all_items
            if "_raw_factor" in item
        ]

        factor_number = len(all_items) + 1

        factor = await self._factor_agent.extract_next_factor(
            case_description=state["query"],
            config=self._config,
            existing_factors=existing_factors,
            source_context=source_context,
            factor_number=factor_number,
            rejected_factors=rejected_factors,
        )

        return {
            "id": factor.id,
            "text": factor.description,
            "type": factor.factor_type,
            "_raw_factor": factor.model_dump(),
            "event_data": {
                "factor_type": factor.factor_type,
                "description": factor.description,
                "legal_basis": factor.legal_basis,
                "factor_number": factor_number,
            },
        }

    async def evaluate_item(
        self,
        item: Dict[str, Any],
        evidence,
        state: dict,
    ) -> Dict[str, Any]:
        """Evaluate factor using OutcomeExtractor + LLM weighting."""
        from app.services.predictive_analysis.outcome_extractor import evaluate_evidence_outcomes
        from app.services.predictive_analysis.service import PredictiveAnalysisService

        # Flatten tiered evidence — predictive mode doesn't need two-tier separation
        if isinstance(evidence, dict) and "source" in evidence:
            flat_evidence = evidence.get("source", []) + evidence.get("external", [])
        else:
            flat_evidence = evidence  # Legacy flat list

        factor = PredictionFactor(**item["_raw_factor"])

        # Evaluate evidence outcomes
        matches = await evaluate_evidence_outcomes(factor, flat_evidence, self._config)

        # Weight the factor
        svc = PredictiveAnalysisService.__new__(PredictiveAnalysisService)
        weighted = await svc._weight_factor(
            factor, matches, self._config, state.get("confidence_threshold", 0.7)
        )

        if weighted:
            return {
                "status": "accepted",
                "confidence": weighted.confidence,
                "_weighted_factor": weighted,
            }
        else:
            return {
                "status": "rejected",
                "confidence": 0.0,
                "reason": "Insufficient evidence or below confidence threshold",
            }

    def is_duplicate(self, item: Dict[str, Any], state: dict) -> bool:
        """Check word-overlap dedup."""
        from app.services.predictive_analysis.service import _is_duplicate_factor

        factor = PredictionFactor(**item["_raw_factor"])

        # Build weighted factors list from accepted items
        # We re-check from cache would be too slow, so use all_extracted_items
        all_items = state.get("all_extracted_items", [])
        previous_factors = [
            PredictionFactor(**it["_raw_factor"])
            for it in all_items
            if "_raw_factor" in it
        ]

        # Need existing weighted factors for the original dedup logic
        # We pass empty list — the all_extracted check is the main one
        return _is_duplicate_factor(factor, [], previous_factors)

    async def check_completion(self, state: dict, source_context: str) -> bool:
        """LLM completion check via FactorAgent."""
        existing_factors = await self._cache.get_weighted_factors(
            "", state["session_id"]
        )
        return await self._factor_agent.check_completion(
            case_description=state["query"],
            config=self._config,
            existing_factors=existing_factors,
            source_context=source_context,
        )

    async def on_accepted(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: dict,
    ) -> Dict[str, Any]:
        """Cache weighted factor, return SSE event."""
        weighted: WeightedFactor = evaluation["_weighted_factor"]

        await self._cache.add_weighted_factor(
            "", state["session_id"], weighted
        )
        await self._cache.extend_ttl("", state["session_id"])

        # Serialize supporting matches for frontend display
        serialized_matches = [
            {
                "document_id": m.document_id,
                "document_title": m.document_title,
                "text_excerpt": m.text_excerpt,
                "similarity_score": m.similarity_score,
                "outcome": m.outcome,
                "supports_factor": m.supports_factor,
                "source": m.source,
                "url": m.url,
                "roj": m.roj,
                "ecli": m.ecli,
                "date": m.date,
                "resolution_type": m.resolution_type,
                "ponente": m.ponente,
            }
            for m in weighted.supporting_matches
        ]

        return {
            "event_type": "factor_weighted",
            "factor_id": item["id"],
            "data": {
                "factor_type": weighted.factor_type,
                "description": weighted.description,
                "weight": weighted.weight,
                "confidence": weighted.confidence,
                "outcome": weighted.outcome,
                "outcome_label": self._config.outcome_labels.get(
                    weighted.outcome, weighted.outcome
                ),
                "matches_count": len(weighted.supporting_matches),
                "supporting_matches": serialized_matches,
            },
        }

    async def on_rejected(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: dict,
    ) -> Dict[str, Any]:
        """Return SSE event for rejected factor."""
        return {
            "event_type": "factor_rejected",
            "factor_id": item["id"],
            "data": {
                "factor_type": item.get("type", ""),
                "description": item.get("text", ""),
                "reason": evaluation.get("reason", "Insufficient evidence"),
            },
        }

    async def synthesize(self, state: dict) -> Dict[str, Any]:
        """Aggregate factors into prediction result."""
        from app.services.predictive_analysis.prediction_synthesizer import synthesize_prediction
        from app.core.langfuse_config import langfuse_context

        final_factors = await self._cache.get_weighted_factors(
            "", state["session_id"]
        )

        execution_time_ms = state.get("execution_time_ms", 0)

        result = await synthesize_prediction(
            session_id=state["session_id"],
            factors=final_factors,
            config=self._config,
            case_description=state["query"],
            execution_time_ms=execution_time_ms,
        )

        # Store result in cache
        await self._cache.store_result(
            "", state["session_id"], result
        )

        # Langfuse scores
        try:
            langfuse_context.score("factor_count", len(final_factors))
            langfuse_context.score(
                "rejection_rate",
                state.get("items_rejected", 0) / max(state.get("items_extracted", 1), 1),
            )
            langfuse_context.score("avg_confidence", result.probability)
            langfuse_context.score("execution_time_ms", execution_time_ms)
        except Exception:
            pass

        return {
            "session_id": state["session_id"],
            "probability": result.probability,
            "confidence_interval": result.confidence_interval,
            "primary_outcome": result.primary_outcome,
            "primary_outcome_label": self._config.outcome_labels.get(
                result.primary_outcome, result.primary_outcome
            ),
            "outcome_probabilities": {
                k: {"probability": v, "label": self._config.outcome_labels.get(k, k)}
                for k, v in result.outcome_probabilities.items()
            },
            "factors_extracted": state.get("items_extracted", 0),
            "factors_weighted": state.get("items_accepted", 0),
            "factors_rejected": state.get("items_rejected", 0),
            "recommendation": result.recommendation,
            "disclaimer": result.disclaimer,
            "execution_time_ms": execution_time_ms,
            "sources": list(state.get("sources_map", {}).values()),
        }
