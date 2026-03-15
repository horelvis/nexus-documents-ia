"""
Outcome Extractor — Evaluates each document match against a factor.

For each piece of evidence found, the LLM evaluates:
- Does it support the factor?
- What outcome does it suggest? (using sector-specific outcome labels)
- How confident is the assessment?

This is the "verifier" equivalent from Verified Generation,
but instead of true/false verification, it produces outcome classifications.

Prompts are managed via LangfusePromptClient with YAML fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from app.agents.langgraph.sectors.predictive_config import PredictiveConfig
from app.core.langfuse_config import observe
from app.schemas.predictive_analysis import PredictionFactor, VerificationMatch
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)

# ─── Fallback prompts (Spanish) ───

FALLBACK_OUTCOME_SYSTEM = (
    "Eres un evaluador de evidencias para análisis predictivo.\n\n"
    "Para cada pieza de evidencia, determina:\n"
    "1. Si apoya o contradice el factor analítico\n"
    "2. Qué resultado sugiere\n"
    "3. Tu nivel de confianza\n\n"
    "Responde SOLO con un objeto JSON (sin markdown, sin explicación):\n"
    '{{"supports_factor": true/false, "outcome": "una de las claves de resultado", '
    '"confidence": 0.0-1.0, "reason": "razón breve en español"}}\n\n'
    "Resultados disponibles: {outcome_display}\n\n"
    "Reglas:\n"
    "- Basa tu evaluación estrictamente en el texto de la evidencia\n"
    "- Considera cómo la evidencia se relaciona con el factor específico\n"
    "- Escribe la razón SIEMPRE en español\n"
    "- NUNCA uses etiquetas <think>. Responde directamente con JSON."
)

FALLBACK_OUTCOME_USER = (
    "FACTOR A EVALUAR:\n"
    "Tipo: {factor_type}\n"
    "Descripción: {factor_description}\n"
    "Base legal: {legal_basis}\n\n"
    "EVIDENCIA:\n{doc_excerpt}\n\n"
    "Evalúa esta evidencia respecto al factor. Responde solo con JSON."
)


@observe(name="predictive.evaluate_evidence")
async def evaluate_evidence_outcomes(
    factor: PredictionFactor,
    evidence: List[dict],
    config: PredictiveConfig,
) -> List[VerificationMatch]:
    """
    Evaluate each piece of evidence against a factor using LLM.

    Args:
        factor: The factor being analyzed
        evidence: Raw evidence dicts from Weaviate/web search
        config: Sector predictive config (for outcome labels)

    Returns:
        List of VerificationMatch with outcome classifications
    """
    if not evidence:
        return []

    client = get_langfuse_prompt_client()
    outcome_keys = list(config.outcome_labels.keys())
    outcome_display = ", ".join(f'"{k}" ({v})' for k, v in config.outcome_labels.items())

    # System prompt (once per factor, reused across evidence items)
    sys_cached = await client.get_prompt(
        "emma_predictive_outcome_system",
        variables={"outcome_display": outcome_display},
        fallback=FALLBACK_OUTCOME_SYSTEM.format(outcome_display=outcome_display),
    )
    system_prompt = sys_cached.content if sys_cached else FALLBACK_OUTCOME_SYSTEM.format(
        outcome_display=outcome_display
    )

    matches: List[VerificationMatch] = []

    for ev in evidence:
        excerpt = ev.get("text_excerpt", "")[:1500]
        if not excerpt:
            continue

        # User prompt (per evidence item)
        user_variables = {
            "factor_type": factor.factor_type,
            "factor_description": factor.description,
            "legal_basis": factor.legal_basis or "N/A",
            "doc_excerpt": excerpt,
        }
        user_cached = await client.get_prompt(
            "emma_predictive_outcome_user",
            variables=user_variables,
            fallback=FALLBACK_OUTCOME_USER.format(**user_variables),
        )
        user_prompt = user_cached.content if user_cached else FALLBACK_OUTCOME_USER.format(
            **user_variables
        )

        # Evaluate with LLM
        evaluation = await _call_llm_evaluation(system_prompt, user_prompt, outcome_keys)

        matches.append(VerificationMatch(
            document_id=ev.get("document_id", ""),
            document_title=ev.get("document_title"),
            chunk_id=ev.get("chunk_id"),
            text_excerpt=excerpt[:500],
            similarity_score=ev.get("similarity_score", 0.0),
            outcome=evaluation.get("outcome", outcome_keys[0]),
            supports_factor=evaluation.get("supports_factor", False),
            source=ev.get("source", "internal"),
            url=ev.get("url"),
            roj=ev.get("roj"),
            ecli=ev.get("ecli"),
            date=ev.get("date"),
            resolution_type=ev.get("resolution_type"),
            ponente=ev.get("ponente"),
        ))

    logger.info(
        f"✅ Evaluated {len(matches)} evidence items for factor [{factor.factor_type}]"
    )
    return matches


async def _call_llm_evaluation(
    system_prompt: str,
    user_prompt: str,
    valid_outcomes: List[str],
) -> dict:
    """Call LLM for evidence evaluation, parse JSON response."""
    evaluation = {
        "supports_factor": False,
        "outcome": valid_outcomes[0] if valid_outcomes else "positive",
        "confidence": 0.5,
        "reason": "Evaluación LLM fallida",
    }

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        from app.agents.llm_models import get_planner_model

        model = get_planner_model().bind(temperature=0.1, max_tokens=300)
        llm_response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        if llm_response and llm_response.content:
            content = llm_response.content.strip()
            # Clean thinking tags
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
            if '<think>' in content:
                content = content[:content.find('<think>')]
            content = content.strip()

            # Clean markdown
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            # Parse JSON
            parsed = False
            try:
                result = json.loads(content)
                parsed = True
            except json.JSONDecodeError:
                json_match = re.search(r'\{[^{}]*"supports_factor"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        parsed = True
                    except json.JSONDecodeError:
                        pass

            if parsed:
                outcome = result.get("outcome", valid_outcomes[0])
                if outcome not in valid_outcomes:
                    outcome = valid_outcomes[0]
                evaluation = {
                    "supports_factor": result.get("supports_factor", False),
                    "outcome": outcome,
                    "confidence": float(result.get("confidence", 0.5)),
                    "reason": result.get("reason", ""),
                }
            else:
                logger.warning(f"⚠️ Failed to parse outcome evaluation: {content[:200]}")

    except Exception as e:
        logger.error(f"❌ Outcome evaluation LLM call failed: {e}")

    return evaluation
