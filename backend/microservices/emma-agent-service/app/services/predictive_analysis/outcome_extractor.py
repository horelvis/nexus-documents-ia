"""
Outcome Extractor — Evaluates each document match against a factor.

For each piece of evidence found, the LLM evaluates:
- Does it support the factor?
- What outcome does it suggest? (using sector-specific outcome labels)
- How confident is the assessment?

This is the "verifier" equivalent from Verified Generation,
but instead of true/false verification, it produces outcome classifications.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from app.agents.langgraph.sectors.predictive_config import PredictiveConfig
from app.schemas.predictive_analysis import PredictionFactor, VerificationMatch

logger = logging.getLogger(__name__)


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

    outcome_keys = list(config.outcome_labels.keys())
    outcome_display = ", ".join(f'"{k}" ({v})' for k, v in config.outcome_labels.items())

    system_prompt = (
        "You are an evidence evaluator for predictive analysis.\n\n"
        "For each piece of evidence, determine:\n"
        "1. Whether it supports or contradicts the analytical factor\n"
        "2. What outcome it suggests\n"
        "3. Your confidence level\n\n"
        "Respond ONLY with a JSON object (no markdown, no explanation):\n"
        '{"supports_factor": true/false, "outcome": "one of the outcome keys", '
        '"confidence": 0.0-1.0, "reason": "brief reason"}\n\n'
        f"Available outcomes: {outcome_display}\n\n"
        "Rules:\n"
        "- Base assessment strictly on the evidence text\n"
        "- Consider how the evidence relates to the specific factor\n"
        "- NEVER use <think> tags. Output JSON directly."
    )

    matches: List[VerificationMatch] = []

    for ev in evidence:
        excerpt = ev.get("text_excerpt", "")[:1500]
        if not excerpt:
            continue

        user_prompt = (
            f"FACTOR TO EVALUATE:\n"
            f"Type: {factor.factor_type}\n"
            f"Description: {factor.description}\n"
            f"Legal basis: {factor.legal_basis or 'N/A'}\n\n"
            f"EVIDENCE:\n{excerpt}\n\n"
            "Evaluate this evidence against the factor. Respond with JSON only."
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
        "reason": "LLM evaluation failed",
    }

    try:
        from app.agents.llm_client import get_llm_client

        llm_client = await get_llm_client()
        llm_response = await llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=300,
            enable_thinking=False,
        )

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
