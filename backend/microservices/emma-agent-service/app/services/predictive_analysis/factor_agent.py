"""
Factor Agent — Extracts factors one at a time using LLM.

Adapts WriterAgent from Verified Generation. Instead of generating claims,
it extracts analytical factors parametrized by sector config.

Each factor is short, focused, and includes a factor_type from the sector's
factor_types list. The agent builds on previously extracted factors to avoid
repetition.

Prompts are managed via LangfusePromptClient with YAML fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Optional

import httpx

from app.core.config import settings
from app.core.langfuse_config import observe
from app.schemas.predictive_analysis import PredictionFactor, WeightedFactor
from app.agents.langgraph.sectors.predictive_config import PredictiveConfig
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)


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

    @observe(name="predictive.extract_factor")
    async def extract_next_factor(
        self,
        case_description: str,
        config: PredictiveConfig,
        existing_factors: List[WeightedFactor],
        source_context: str,
        factor_number: Optional[int] = None,
        rejected_factors: Optional[List[PredictionFactor]] = None,
    ) -> PredictionFactor:
        """Extract the next factor for analysis."""
        if factor_number is None:
            factor_number = len(existing_factors) + 1

        # Build prompts from Langfuse/YAML with fallback
        system_prompt = await self._build_system_prompt(config)
        user_prompt = await self._build_user_prompt(
            case_description, config, existing_factors, source_context, factor_number,
            rejected_factors=rejected_factors,
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

    @observe(name="predictive.check_completion")
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

        client = get_langfuse_prompt_client()
        factors_text = self._format_existing_factors(existing_factors)

        variables = {
            "case_description": case_description,
            "source_context": source_context[:2000],
            "factors_text": factors_text,
            "factor_types": ", ".join(config.factor_types),
        }

        # System prompt
        sys_cached = await client.get_prompt(
            "emma_predictive_completion_system",
        )
        system_prompt = sys_cached.content

        # User prompt
        user_cached = await client.get_prompt(
            "emma_predictive_completion_user",
            variables=variables,
        )
        user_prompt = user_cached.content

        response = await self._call_llm(system_prompt, user_prompt)

        response = response.strip().upper()
        # Retrocompatible: accept both Spanish and English
        is_complete = "SÍ" in response or "SI" in response or "YES" in response

        logger.info(
            f"🏁 Factor completion check: {is_complete} "
            f"(factors={len(existing_factors)}, response={response[:20]})"
        )
        return is_complete

    async def _build_system_prompt(self, config: PredictiveConfig) -> str:
        """Build system prompt from Langfuse/YAML with inline fallback."""
        client = get_langfuse_prompt_client()
        factor_types_str = ", ".join(config.factor_types)

        cached = await client.get_prompt(
            "emma_predictive_factor_system",
            variables={"factor_types": factor_types_str},
        )
        return cached.content

    async def _build_user_prompt(
        self,
        case_description: str,
        config: PredictiveConfig,
        existing_factors: List[WeightedFactor],
        source_context: str,
        factor_number: int,
        rejected_factors: Optional[List[PredictionFactor]] = None,
    ) -> str:
        """Build user prompt from Langfuse/YAML with inline fallback."""
        client = get_langfuse_prompt_client()
        factor_types_str = ", ".join(config.factor_types)

        # Combine weighted + rejected factors into context so LLM doesn't repeat
        all_previous = self._format_existing_factors(existing_factors)
        if rejected_factors:
            rejected_text = "\n".join(
                f"- [{f.factor_type}] {f.description} (RECHAZADO — sin evidencia suficiente)"
                for f in rejected_factors
            )
            all_previous += f"\n\nFACTORES YA RECHAZADOS (no repetir, busca otros diferentes):\n{rejected_text}"

        has_previous = bool(existing_factors) or bool(rejected_factors)

        if has_previous:
            variables = {
                "case_description": case_description,
                "source_context": source_context[:4000],
                "previous_factors": all_previous,
                "factor_types": factor_types_str,
                "factor_number": str(factor_number),
            }
            cached = await client.get_prompt(
                "emma_predictive_factor_user_next",
                variables=variables,
            )
            return cached.content
        else:
            variables = {
                "case_description": case_description,
                "source_context": source_context[:4000],
                "factor_types": factor_types_str,
            }
            cached = await client.get_prompt(
                "emma_predictive_factor_user_first",
                variables=variables,
            )
            return cached.content

    def _format_existing_factors(self, factors: List[WeightedFactor]) -> str:
        if not factors:
            return "(No hay factores extraídos aún)"
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
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_chat_model

            model = get_chat_model().bind(
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            if response and response.content:
                return response.content.strip()
        except Exception as e:
            logger.warning(f"⚠️ LLM router failed ({e}), falling back to raw vLLM")

        # Fallback: direct vLLM
        try:
            async with httpx.AsyncClient(timeout=settings.agent_raw_vllm_timeout_seconds) as client:
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
# Singleton (with asyncio.Lock for race-safe initialization)
# =============================================================================

_factor_agent: Optional[FactorAgent] = None
_factor_agent_lock: Optional["asyncio.Lock"] = None


def _get_factor_lock() -> "asyncio.Lock":
    """Lazy lock creation (must be called inside a running event loop)."""
    global _factor_agent_lock
    if _factor_agent_lock is None:
        _factor_agent_lock = asyncio.Lock()
    return _factor_agent_lock


def get_factor_agent() -> FactorAgent:
    """Get the singleton FactorAgent (sync — init is cheap, no I/O)."""
    global _factor_agent
    if _factor_agent is None:
        _factor_agent = FactorAgent(temperature=settings.verified_claim_temperature)
    return _factor_agent


async def get_factor_agent_async() -> FactorAgent:
    """Get the singleton FactorAgent (async — race-safe)."""
    global _factor_agent
    if _factor_agent is None:
        async with _get_factor_lock():
            if _factor_agent is None:
                _factor_agent = FactorAgent(temperature=settings.verified_claim_temperature)
    return _factor_agent
