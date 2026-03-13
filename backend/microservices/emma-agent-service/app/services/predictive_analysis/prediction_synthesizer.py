"""
Prediction Synthesizer — Aggregates weighted factors into a prediction.

Uses a hybrid approach:
1. Statistical: Weighted average of outcome ratios across factors
2. LLM: Natural language synthesis for recommendation

Produces:
- Overall probability for primary outcome
- Confidence interval
- Outcome probabilities breakdown
- Natural language recommendation

Prompts are managed via LangfusePromptClient with YAML fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from app.agents.langgraph.sectors.predictive_config import PredictiveConfig
from app.core.langfuse_config import observe
from app.schemas.predictive_analysis import PredictionResult, WeightedFactor
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)

# ─── Fallback prompts (Spanish) ───

FALLBACK_REC_SYSTEM = (
    "Eres un analista experto redactando recomendaciones basadas en factores predictivos.\n"
    "Escribe una recomendación concisa (3-5 frases) SIEMPRE en ESPAÑOL.\n"
    "Sé equilibrado, mencionando factores a favor y en contra.\n"
    "NO uses etiquetas <think>. Responde directamente con la recomendación."
)

FALLBACK_REC_USER = (
    "DESCRIPCIÓN DEL CASO:\n{case_description}\n\n"
    "FACTORES ANALIZADOS:\n{factors_summary}\n\n"
    "RESULTADOS PREDICHOS:\n{outcome_summary}\n\n"
    "PREDICCIÓN PRINCIPAL: {primary_label} ({primary_probability})\n\n"
    "Escribe una recomendación concisa (3-5 frases) en español. Sé específico sobre los factores clave."
)


@observe(name="predictive.synthesize")
async def synthesize_prediction(
    session_id: str,
    factors: List[WeightedFactor],
    config: PredictiveConfig,
    case_description: str,
    execution_time_ms: int = 0,
) -> PredictionResult:
    """
    Synthesize a prediction from weighted factors.

    Args:
        session_id: Analysis session ID
        factors: List of weighted factors
        config: Sector predictive config
        case_description: Original case description
        execution_time_ms: Total execution time

    Returns:
        PredictionResult with probabilities, recommendation, and disclaimer
    """
    outcome_keys = list(config.outcome_labels.keys())

    # Determine active sector
    import os
    active_sector = os.getenv("ACTIVE_SECTOR", "").strip().lower() or None

    # --- Handle insufficient evidence (no weighted factors) ---
    if not factors:
        logger.warning("⚠️ No weighted factors — insufficient evidence for prediction")
        n = len(outcome_keys)
        uniform = {k: round(1.0 / n, 3) for k in outcome_keys}
        return PredictionResult(
            session_id=session_id,
            probability=0.0,
            confidence_interval=[0.0, round(1.0 / n, 3)],
            primary_outcome=outcome_keys[0] if outcome_keys else "unknown",
            outcome_probabilities=uniform,
            factors=[],
            recommendation=(
                "No se encontró evidencia suficiente en los documentos disponibles para generar "
                "una predicción fiable. Los factores extraídos no superaron el umbral de confianza "
                "requerido. Se recomienda aportar documentación adicional (contratos, informes "
                "periciales, resoluciones judiciales) y repetir el análisis."
            ),
            disclaimer=config.disclaimer,
            sector=active_sector,
            execution_time_ms=execution_time_ms,
        )

    # --- Step 1: Statistical aggregation ---
    outcome_probs = _compute_outcome_probabilities(factors, outcome_keys)

    # Primary outcome = highest probability
    primary_outcome = max(outcome_probs, key=outcome_probs.get)
    primary_prob = outcome_probs[primary_outcome]

    # Confidence interval based on factor confidence spread
    ci_lower, ci_upper = _compute_confidence_interval(factors, primary_prob)

    # --- Step 2: LLM recommendation ---
    recommendation = await _generate_recommendation(
        factors, config, case_description, outcome_probs, primary_outcome
    )

    result = PredictionResult(
        session_id=session_id,
        probability=round(primary_prob, 3),
        confidence_interval=[round(ci_lower, 3), round(ci_upper, 3)],
        primary_outcome=primary_outcome,
        outcome_probabilities={k: round(v, 3) for k, v in outcome_probs.items()},
        factors=factors,
        recommendation=recommendation,
        disclaimer=config.disclaimer,
        sector=active_sector,
        execution_time_ms=execution_time_ms,
    )

    logger.info(
        f"✅ Prediction synthesized: primary={primary_outcome} ({primary_prob:.1%}), "
        f"CI=[{ci_lower:.1%}, {ci_upper:.1%}], factors={len(factors)}"
    )

    return result


def _compute_outcome_probabilities(
    factors: List[WeightedFactor],
    outcome_keys: List[str],
) -> Dict[str, float]:
    """
    Compute outcome probabilities using weighted average of factor outcomes.

    Each factor contributes proportionally to its weight.
    """
    if not factors:
        # Uniform distribution if no factors
        n = len(outcome_keys)
        return {k: 1.0 / n for k in outcome_keys}

    # Accumulate weighted votes
    outcome_scores: Dict[str, float] = {k: 0.0 for k in outcome_keys}
    total_weight = 0.0

    for factor in factors:
        weight = factor.weight * factor.confidence
        total_weight += weight

        if factor.outcome_ratio:
            # Use detailed ratio from evidence
            for outcome_key, ratio in factor.outcome_ratio.items():
                if outcome_key in outcome_scores:
                    outcome_scores[outcome_key] += weight * ratio
        else:
            # Use single outcome vote
            if factor.outcome in outcome_scores:
                outcome_scores[factor.outcome] += weight

    # Normalize to probabilities
    if total_weight > 0:
        outcome_probs = {k: v / total_weight for k, v in outcome_scores.items()}
    else:
        n = len(outcome_keys)
        outcome_probs = {k: 1.0 / n for k in outcome_keys}

    # Ensure probabilities sum to 1.0
    total = sum(outcome_probs.values())
    if total > 0 and abs(total - 1.0) > 0.001:
        outcome_probs = {k: v / total for k, v in outcome_probs.items()}

    return outcome_probs


def _compute_confidence_interval(
    factors: List[WeightedFactor],
    primary_prob: float,
) -> tuple[float, float]:
    """
    Compute confidence interval for the primary probability.

    Uses the spread of factor confidences to estimate uncertainty.
    """
    if not factors:
        return (max(0.0, primary_prob - 0.25), min(1.0, primary_prob + 0.25))

    # Average confidence across factors
    avg_confidence = sum(f.confidence for f in factors) / len(factors)

    # Higher average confidence → narrower interval
    # Base spread: 0.15 at avg_confidence=1.0, 0.30 at avg_confidence=0.5
    spread = 0.30 * (1.0 - avg_confidence * 0.5)

    ci_lower = max(0.0, primary_prob - spread)
    ci_upper = min(1.0, primary_prob + spread)

    return (ci_lower, ci_upper)


async def _generate_recommendation(
    factors: List[WeightedFactor],
    config: PredictiveConfig,
    case_description: str,
    outcome_probs: Dict[str, float],
    primary_outcome: str,
) -> str:
    """Generate natural language recommendation using LLM."""
    client = get_langfuse_prompt_client()

    # Build factors summary
    factors_summary = "\n".join(
        f"- [{f.factor_type}] {f.description} (weight: {f.weight:.2f}, outcome: {f.outcome})"
        for f in factors
    )

    # Build outcome summary
    outcome_summary = ", ".join(
        f"{config.outcome_labels.get(k, k)}: {v:.1%}"
        for k, v in sorted(outcome_probs.items(), key=lambda x: x[1], reverse=True)
    )

    primary_label = config.outcome_labels.get(primary_outcome, primary_outcome)
    primary_probability = f"{outcome_probs.get(primary_outcome, 0):.1%}"

    # System prompt
    sys_cached = await client.get_prompt(
        "emma_predictive_recommendation_system",
        fallback=FALLBACK_REC_SYSTEM,
    )
    system_prompt = sys_cached.content if sys_cached else FALLBACK_REC_SYSTEM

    # User prompt
    user_variables = {
        "case_description": case_description[:2000],
        "factors_summary": factors_summary,
        "outcome_summary": outcome_summary,
        "primary_label": primary_label,
        "primary_probability": primary_probability,
    }
    user_cached = await client.get_prompt(
        "emma_predictive_recommendation_user",
        variables=user_variables,
        fallback=FALLBACK_REC_USER.format(**user_variables),
    )
    user_prompt = user_cached.content if user_cached else FALLBACK_REC_USER.format(
        **user_variables
    )

    try:
        from app.agents.llm_router import get_llm_router
        from app.agents.llm_client import ModelRole

        router = await get_llm_router()
        response = await router.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
            enable_thinking=False,
            role=ModelRole.CHAT,
        )

        if response and response.content:
            text = response.content.strip()
            # Clean thinking tags
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            if '<think>' in text:
                text = text[:text.find('<think>')]
            return text.strip()

    except Exception as e:
        logger.error(f"❌ Recommendation generation failed: {e}")

    # Fallback recommendation
    return (
        f"Basado en el análisis de {len(factors)} factores, "
        f"la predicción principal es '{primary_label}' "
        f"con una probabilidad del {outcome_probs.get(primary_outcome, 0):.0%}. "
        f"Se recomienda una revisión detallada por un profesional cualificado."
    )
