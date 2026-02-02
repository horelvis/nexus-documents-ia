"""
Factor Agent — Extracts factors one at a time using LLM.

Adapts WriterAgent from Verified Generation. Instead of generating claims,
it extracts analytical factors parametrized by sector config.

Each factor is short, focused, and includes a factor_type from the sector's
factor_types list. The agent builds on previously extracted factors to avoid
repetition.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

import httpx
import yaml

from app.core.config import settings
from app.schemas.predictive_analysis import PredictionFactor, WeightedFactor
from app.agents.langgraph.sectors.predictive_config import PredictiveConfig

logger = logging.getLogger(__name__)

# Load prompts from YAML
_prompts_cache: Optional[dict] = None


def _load_prompts() -> dict:
    global _prompts_cache
    if _prompts_cache is None:
        prompts_path = Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "predictive_prompts.yaml"
        if prompts_path.exists():
            with open(prompts_path, "r", encoding="utf-8") as f:
                _prompts_cache = yaml.safe_load(f) or {}
        else:
            logger.warning(f"⚠️ Predictive prompts not found at {prompts_path}")
            _prompts_cache = {}
    return _prompts_cache


def _get_prompt(key: str, fallback: str = "") -> str:
    """Get a prompt by dot-separated key (e.g., 'predictive.legal.factor_extraction')."""
    prompts = _load_prompts()
    parts = key.split(".")
    current = prompts
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return fallback
    return current if isinstance(current, str) else fallback


class FactorAgent:
    """
    Extracts analytical factors one at a time using LLM.

    Each factor is typed according to sector config and includes
    a legal/protocol/standard basis when applicable.
    """

    def __init__(
        self,
        temperature: float = 0.3,
        max_tokens: int = 300,
    ):
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def extract_next_factor(
        self,
        case_description: str,
        config: PredictiveConfig,
        existing_factors: List[WeightedFactor],
        source_context: str,
        factor_number: Optional[int] = None,
    ) -> PredictionFactor:
        """Extract the next factor for analysis."""
        if factor_number is None:
            factor_number = len(existing_factors) + 1

        # Build prompts from sector config
        system_prompt = self._build_system_prompt(config)
        user_prompt = self._build_user_prompt(
            case_description, config, existing_factors, source_context, factor_number
        )

        raw_text = await self._call_llm(system_prompt, user_prompt)
        logger.info(f"🔍 Raw factor extraction ({len(raw_text)} chars): {raw_text[:300]}")

        # Parse structured response
        factor = self._parse_factor_response(
            raw_text, case_description, config, factor_number
        )

        logger.info(
            f"📝 Extracted factor #{factor_number}: [{factor.factor_type}] {factor.description[:80]}..."
        )
        return factor

    async def check_completion(
        self,
        case_description: str,
        config: PredictiveConfig,
        existing_factors: List[WeightedFactor],
        source_context: str,
    ) -> bool:
        """Check if all relevant factors have been extracted."""
        if len(existing_factors) < 3:
            return False

        factors_text = self._format_existing_factors(existing_factors)
        check_prompt = f"""Determine if the factor analysis is COMPLETE.

CASE DESCRIPTION:
{case_description}

SOURCE CONTEXT:
{source_context[:2000]}

FACTORS EXTRACTED SO FAR:
{factors_text}

AVAILABLE FACTOR TYPES: {', '.join(config.factor_types)}

Is the analysis complete? Answer ONLY "YES" or "NO".
- YES: All relevant factors from the documents have been identified
- NO: There are more significant factors to extract"""

        response = await self._call_llm(
            "You are a completeness checker. Answer only YES or NO.",
            check_prompt,
        )

        response = response.strip().upper()
        is_complete = "YES" in response

        logger.info(
            f"🏁 Factor completion check: {is_complete} "
            f"(factors={len(existing_factors)}, response={response[:20]})"
        )
        return is_complete

    def _build_system_prompt(self, config: PredictiveConfig) -> str:
        """Build system prompt from sector config."""
        # Try to load from YAML first
        prompt_key = f"{config.system_prompt_key}.factor_extraction"
        yaml_prompt = _get_prompt(prompt_key)
        if yaml_prompt:
            return yaml_prompt

        # Fallback: construct dynamically
        factor_types_str = ", ".join(config.factor_types)
        return f"""You are an expert analytical agent that extracts critical factors for predictive analysis.

CRITICAL RULES:
1. Extract EXACTLY ONE factor at a time
2. Each factor must be from these types: {factor_types_str}
3. Factors must be grounded in the source documents
4. Include specific references (articles, clauses, standards) when available
5. Keep factors concise and focused (2-3 sentences max)
6. Write in the same language as the source documents
7. DO NOT use <think> tags or reasoning blocks

OUTPUT FORMAT (JSON):
{{"factor_type": "one of the types above", "description": "clear description of the factor", "legal_basis": "specific reference or null"}}

Output ONLY the JSON object, nothing else."""

    def _build_user_prompt(
        self,
        case_description: str,
        config: PredictiveConfig,
        existing_factors: List[WeightedFactor],
        source_context: str,
        factor_number: int,
    ) -> str:
        """Build user prompt with context."""
        if existing_factors:
            factors_text = self._format_existing_factors(existing_factors)
            return f"""Extract the NEXT analytical factor.

CASE DESCRIPTION:
{case_description}

SOURCE CONTEXT:
{source_context[:4000]}

PREVIOUSLY EXTRACTED FACTORS (don't repeat these):
{factors_text}

AVAILABLE FACTOR TYPES: {', '.join(config.factor_types)}
FACTOR NUMBER: {factor_number}

Extract ONE new factor as JSON. Output the JSON only."""
        else:
            return f"""Extract the FIRST analytical factor.

CASE DESCRIPTION:
{case_description}

SOURCE CONTEXT:
{source_context[:4000]}

AVAILABLE FACTOR TYPES: {', '.join(config.factor_types)}

Extract ONE factor as JSON. Output the JSON only."""

    def _format_existing_factors(self, factors: List[WeightedFactor]) -> str:
        if not factors:
            return "(No factors extracted yet)"
        lines = []
        for i, f in enumerate(factors, 1):
            lines.append(f"{i}. [{f.factor_type}] {f.description}")
        return "\n".join(lines)

    def _parse_factor_response(
        self,
        raw_text: str,
        case_description: str,
        config: PredictiveConfig,
        factor_number: int,
    ) -> PredictionFactor:
        """Parse LLM response into PredictionFactor."""
        # Clean thinking tags
        text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL)
        if '<think>' in text:
            text = text[:text.find('<think>')]
        text = text.strip()

        # Try JSON parse
        factor_type = config.factor_types[0]  # default
        description = text
        legal_basis = None

        # Try to extract JSON
        json_match = re.search(r'\{[^{}]*"factor_type"[^{}]*\}', text, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*?\}', text, re.DOTALL)

        if json_match:
            try:
                parsed = json.loads(json_match.group())
                ft = parsed.get("factor_type", "")
                if ft in config.factor_types:
                    factor_type = ft
                description = parsed.get("description", description)
                legal_basis = parsed.get("legal_basis")
            except json.JSONDecodeError:
                pass

        # Clean description
        description = description.replace('**', '').replace('`', '').strip('"\'')
        if not description or len(description) < 10:
            description = f"Factor analítico #{factor_number} extraído del caso."

        return PredictionFactor(
            factor_type=factor_type,
            description=description,
            legal_basis=legal_basis,
            source_query=case_description,
            extraction_order=factor_number,
        )

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call LLM via shared client with fallback to raw vLLM."""
        try:
            from app.agents.llm_client import get_llm_client
            llm_client = await get_llm_client()
            response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                enable_thinking=False,
            )
            if response and response.content:
                return response.content.strip()
        except Exception as e:
            logger.warning(f"⚠️ LLMClient failed ({e}), falling back to raw vLLM")

        # Fallback: direct vLLM
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": settings.vllm_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
                response = await client.post(
                    f"{settings.vllm_base_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
                raise Exception(f"vLLM error: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ vLLM call failed: {e}")
            raise


# =============================================================================
# Singleton
# =============================================================================

_factor_agent: Optional[FactorAgent] = None


def get_factor_agent() -> FactorAgent:
    global _factor_agent
    if _factor_agent is None:
        _factor_agent = FactorAgent(temperature=settings.verified_claim_temperature)
    return _factor_agent
