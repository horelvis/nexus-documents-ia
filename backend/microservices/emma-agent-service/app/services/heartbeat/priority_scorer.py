"""Priority Scorer — Multi-factor scoring for proactive insights.

Calculates a priority score (0.0-1.0) for each insight based on:
- Insight type base priority (configurable per tenant via HeartbeatConfig)
- Urgency level
- LLM confidence
- Time sensitivity (e.g., days until contract expiry)
- Tenant activity level
"""
import logging
from typing import Dict, List, Optional

from app.schemas.heartbeat import (
    ProactiveInsightCreate,
    TenantContext,
)

logger = logging.getLogger(__name__)

# Default base priority by insight type (string keys, 0.0-1.0)
# These are used when no tenant-specific type_priorities are configured.
DEFAULT_TYPE_PRIORITIES: Dict[str, float] = {
    "contract_expiration": 0.85,
    "compliance_alert": 0.80,
    "risk_alert": 0.75,
    "deadline_approaching": 0.70,
    "anomaly_detected": 0.60,
    "task_reminder": 0.55,
    "document_update": 0.50,
    "activity_summary": 0.40,
}

# Urgency multipliers (string keys)
URGENCY_MULTIPLIER: Dict[str, float] = {
    "critical": 1.20,
    "high": 1.10,
    "medium": 1.00,
    "low": 0.85,
}


class PriorityScorer:
    """Calculates priority scores for proactive insights."""

    def score_insights(
        self,
        insights: List[ProactiveInsightCreate],
        context: TenantContext,
        type_priorities: Optional[Dict[str, float]] = None,
    ) -> List[ProactiveInsightCreate]:
        """Score all insights and return sorted by priority.

        Args:
            insights: List of insight candidates from LLM
            context: Tenant context for additional scoring factors
            type_priorities: Optional per-tenant priority overrides
                (merged with DEFAULT_TYPE_PRIORITIES)

        Returns:
            Insights with priority_score set, sorted descending
        """
        # Merge defaults with tenant-specific overrides
        effective_priorities = {**DEFAULT_TYPE_PRIORITIES, **(type_priorities or {})}

        scored = []
        for insight in insights:
            score = self._calculate_score(insight, context, effective_priorities)
            insight.priority_score = min(1.0, max(0.0, score))  # Clamp to 0-1
            scored.append(insight)

        # Sort by priority (highest first)
        scored.sort(key=lambda i: i.priority_score, reverse=True)

        return scored

    def _calculate_score(
        self,
        insight: ProactiveInsightCreate,
        context: TenantContext,
        type_priorities: Dict[str, float],
    ) -> float:
        """Calculate priority score for a single insight."""
        # Start with base priority for the insight type (default 0.50 for unknown types)
        base = type_priorities.get(insight.insight_type, 0.50)

        # Apply urgency multiplier (resolve enum to string value)
        urgency_str = insight.urgency.value if hasattr(insight.urgency, 'value') else str(insight.urgency)
        urgency_mult = URGENCY_MULTIPLIER.get(urgency_str, 1.0)
        score = base * urgency_mult

        # Factor in LLM confidence (weight: 20%)
        confidence_factor = 0.8 + (insight.confidence * 0.2)
        score *= confidence_factor

        # Time sensitivity bonus for contracts
        if insight.insight_type == "contract_expiration":
            score = self._apply_contract_time_bonus(score, insight, context)

        # Activity-based adjustment
        score = self._apply_activity_adjustment(score, context)

        # Novelty bonus (if few insights sent recently)
        score = self._apply_novelty_bonus(score, context)

        return score

    def _apply_contract_time_bonus(
        self,
        score: float,
        insight: ProactiveInsightCreate,
        context: TenantContext,
    ) -> float:
        """Apply time-based bonus for contract expirations."""
        # Find matching contract in context
        for contract in context.contracts_expiring_7d:
            if contract.document_id in insight.related_documents:
                days = contract.days_until_expiry or 30
                if days <= 3:
                    return score * 1.25  # Critical: 25% boost
                elif days <= 7:
                    return score * 1.15  # High: 15% boost

        for contract in context.contracts_expiring_30d:
            if contract.document_id in insight.related_documents:
                days = contract.days_until_expiry or 30
                if days <= 14:
                    return score * 1.05  # Moderate: 5% boost

        return score

    def _apply_activity_adjustment(
        self,
        score: float,
        context: TenantContext,
    ) -> float:
        """Adjust score based on tenant activity level.

        Higher activity = users are engaged, insights more likely useful.
        Very low activity = might need a summary to re-engage.
        """
        active_users = context.user_activity.active_users_24h
        queries = context.user_activity.total_queries_24h

        if active_users == 0 and queries == 0:
            # No activity - boost activity summaries, reduce others slightly
            return score * 0.95
        elif active_users >= 5 or queries >= 20:
            # High activity - users are engaged, insights valuable
            return score * 1.05

        return score

    def _apply_novelty_bonus(
        self,
        score: float,
        context: TenantContext,
    ) -> float:
        """Apply bonus if few insights have been sent recently.

        Prevents notification fatigue while ensuring important
        insights still get through.
        """
        if context.insights_delivered_today == 0:
            # First insight of the day - small boost
            return score * 1.05
        elif context.insights_delivered_today >= 4:
            # Already sent several - raise the bar
            return score * 0.90

        return score

    def filter_by_threshold(
        self,
        insights: List[ProactiveInsightCreate],
        threshold: float,
    ) -> List[ProactiveInsightCreate]:
        """Filter insights below the priority threshold.

        Args:
            insights: Scored insights
            threshold: Minimum priority score to keep (0.0-1.0)

        Returns:
            Insights meeting the threshold
        """
        return [i for i in insights if i.priority_score >= threshold]


# Global singleton
priority_scorer = PriorityScorer()
