"""
Predictive Analysis Service — Stop-and-Go Factor Orchestration.

Mirrors Verified Generation's architecture but for predictive analysis:
1. FactorAgent extracts ONE factor
2. Weaviate + graph + web search for supporting documents
3. OutcomeExtractor evaluates each match → sector outcome labels
4. LLM weights the factor's impact
5. Repeat until max_factors or completion
6. PredictionSynthesizer aggregates → probability + recommendation

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    STOP-AND-GO LOOP                              │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │   ┌────────────┐    ┌────────────────┐    ┌────────────────┐   │
    │   │ 1. Factor  │───▶│ 2. Search +    │───▶│ 3. Weight +    │   │
    │   │ Extract    │    │ Evaluate       │    │ Cache (Redis)  │   │
    │   │ ONE Factor │    │ (Weaviate/Web) │    │ Store Weighted │   │
    │   └────────────┘    └────────────────┘    └────────────────┘   │
    │        │                                         │              │
    │        │◀────────────────────────────────────────┘              │
    │        │     (Context for next factor)                          │
    │                                                                  │
    │   ┌────────────────────────────────────────────────────────┐    │
    │   │ 4. Synthesize: aggregate → probability + recommend     │    │
    │   └────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings
from app.schemas.predictive_analysis import (
    PredictionFactor,
    PredictionRequest,
    PredictionResponse,
    PredictionResult,
    PredictiveEvent,
    PredictiveEventType,
    VerificationMatch,
    WeightedFactor,
)
from app.agents.langgraph.sectors.predictive_config import (
    PredictiveConfig,
    get_predictive_config,
)

from .predictive_cache import PredictiveCache, get_predictive_cache
from .factor_agent import FactorAgent, get_factor_agent
from .outcome_extractor import evaluate_evidence_outcomes
from .prediction_synthesizer import synthesize_prediction

logger = logging.getLogger(__name__)


def _is_duplicate_factor(
    new_factor: PredictionFactor,
    existing: List[WeightedFactor],
    threshold: float = 0.65,
) -> bool:
    """Check if a factor is too similar to any existing factor using word overlap."""
    if not existing:
        return False

    new_words = set(new_factor.description.lower().split())
    if len(new_words) < 3:
        return False

    for ef in existing:
        existing_words = set(ef.description.lower().split())
        if not existing_words:
            continue
        intersection = new_words & existing_words
        union = new_words | existing_words
        similarity = len(intersection) / len(union) if union else 0
        if similarity >= threshold:
            return True
        # Also check same factor_type + high overlap
        if ef.factor_type == new_factor.factor_type and similarity >= 0.5:
            return True

    return False


class PredictiveAnalysisService:
    """Orchestrates predictive analysis with stop-and-go factor loop."""

    def __init__(
        self,
        factor_agent: Optional[FactorAgent] = None,
        cache: Optional[PredictiveCache] = None,
    ):
        self._factor_agent = factor_agent
        self._cache = cache
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        if self._factor_agent is None:
            self._factor_agent = get_factor_agent()
        if self._cache is None:
            self._cache = get_predictive_cache()
            await self._cache.connect()
        self._initialized = True
        logger.info("✅ PredictiveAnalysisService initialized")

    async def analyze(
        self, request: PredictionRequest
    ) -> AsyncGenerator[PredictiveEvent, None]:
        """
        Run predictive analysis with streaming progress events.

        This is the main SSE entry point.
        """
        await self.initialize()

        start_time = time.time()
        session_id = request.session_id or str(uuid.uuid4())

        # Resolve sector config
        config = get_predictive_config(request.sector_override)

        # Clear existing session
        await self._cache.clear_session(request.tenant_id, session_id)

        # Store metadata
        from datetime import datetime, timezone
        await self._cache.store_session_metadata(
            request.tenant_id, session_id,
            {
                "case_description": request.case_description,
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "session_id": session_id,
                "sector": config.system_prompt_key,
            },
        )

        # Hydrate uploaded texts
        uploaded_texts: list[dict] = []
        if request.uploaded_file_ids:
            try:
                from app.services.upload_context_service import upload_context_service
                uploaded_texts = upload_context_service.get_texts(request.uploaded_file_ids)
                if uploaded_texts:
                    logger.info(f"📎 Hydrated {len(uploaded_texts)} uploaded doc(s) for predictive analysis")
            except Exception as e:
                logger.warning(f"⚠️ Failed to hydrate uploads: {e}")

        # Get source context
        source_context = await self._get_source_context(
            query=request.case_description,
            tenant_id=request.tenant_id,
            document_ids=request.context_document_ids,
            collections=request.collections,
            uploaded_texts=uploaded_texts,
        )

        yield PredictiveEvent(
            event_type=PredictiveEventType.PROGRESS,
            data={
                "message": "Context retrieved, starting factor extraction...",
                "session_id": session_id,
            },
            progress_percent=10,
        )

        # Statistics
        factors_extracted = 0
        factors_weighted = 0
        factors_rejected = 0
        duplicate_streak = 0
        max_factors = min(request.max_factors, config.max_factors)

        # Stop-and-go loop
        while factors_extracted < max_factors:
            # Get existing factors
            existing_factors = await self._cache.get_weighted_factors(
                request.tenant_id, session_id
            )

            # Check completion
            if len(existing_factors) >= 3:
                is_complete = await self._factor_agent.check_completion(
                    case_description=request.case_description,
                    config=config,
                    existing_factors=existing_factors,
                    source_context=source_context,
                )
                if is_complete:
                    logger.info(f"🏁 Factor extraction complete at {len(existing_factors)} factors")
                    break

            # Extract next factor
            factors_extracted += 1
            factor_position = len(existing_factors) + 1

            try:
                factor = await self._factor_agent.extract_next_factor(
                    case_description=request.case_description,
                    config=config,
                    existing_factors=existing_factors,
                    source_context=source_context,
                    factor_number=factor_position,
                )
            except Exception as e:
                logger.error(f"❌ Factor extraction failed: {e}")
                yield PredictiveEvent(
                    event_type=PredictiveEventType.ERROR,
                    data={"error": f"Factor extraction failed: {str(e)}"},
                )
                break

            # Deduplicate: skip if too similar to an existing factor
            if _is_duplicate_factor(factor, existing_factors):
                logger.info(
                    f"⏭️ Skipping duplicate factor #{factor_position}: {factor.description[:60]}..."
                )
                duplicate_streak += 1
                if duplicate_streak >= 2:
                    logger.info("🏁 Stopping extraction: consecutive duplicates detected")
                    break
                continue
            duplicate_streak = 0

            yield PredictiveEvent(
                event_type=PredictiveEventType.FACTOR_EXTRACTED,
                factor_id=factor.id,
                data={
                    "factor_type": factor.factor_type,
                    "description": factor.description,
                    "legal_basis": factor.legal_basis,
                    "factor_number": factor_position,
                },
                progress_percent=min(80, 10 + (factors_extracted * 70 // max_factors)),
            )

            # Search for evidence
            yield PredictiveEvent(
                event_type=PredictiveEventType.FACTOR_VERIFICATION_STARTED,
                factor_id=factor.id,
                data={"message": "Searching for supporting documents..."},
            )

            try:
                evidence = await self._search_evidence(
                    factor=factor,
                    tenant_id=request.tenant_id,
                    collections=request.collections,
                    uploaded_texts=uploaded_texts,
                    config=config,
                )

                # Evaluate evidence outcomes
                matches = await evaluate_evidence_outcomes(factor, evidence, config)

                # Weight the factor
                weighted = await self._weight_factor(
                    factor, matches, config, request.confidence_threshold
                )

                if weighted:
                    await self._cache.add_weighted_factor(
                        request.tenant_id, session_id, weighted
                    )
                    factors_weighted += 1

                    yield PredictiveEvent(
                        event_type=PredictiveEventType.FACTOR_WEIGHTED,
                        factor_id=factor.id,
                        data={
                            "factor_type": weighted.factor_type,
                            "description": weighted.description,
                            "weight": weighted.weight,
                            "confidence": weighted.confidence,
                            "outcome": weighted.outcome,
                            "outcome_label": config.outcome_labels.get(weighted.outcome, weighted.outcome),
                            "matches_count": len(weighted.supporting_matches),
                        },
                    )
                else:
                    factors_rejected += 1
                    yield PredictiveEvent(
                        event_type=PredictiveEventType.FACTOR_REJECTED,
                        factor_id=factor.id,
                        data={
                            "factor_type": factor.factor_type,
                            "description": factor.description,
                            "reason": "Insufficient evidence or below confidence threshold",
                        },
                    )

            except Exception as e:
                logger.error(f"❌ Factor verification failed: {e}")
                factors_rejected += 1
                yield PredictiveEvent(
                    event_type=PredictiveEventType.FACTOR_REJECTED,
                    factor_id=factor.id,
                    data={"error": str(e)},
                )

            await self._cache.extend_ttl(request.tenant_id, session_id)

        # Synthesize prediction
        yield PredictiveEvent(
            event_type=PredictiveEventType.SYNTHESIS_STARTED,
            data={"message": "Synthesizing prediction..."},
            progress_percent=85,
        )

        final_factors = await self._cache.get_weighted_factors(
            request.tenant_id, session_id
        )
        execution_time_ms = int((time.time() - start_time) * 1000)

        result = await synthesize_prediction(
            session_id=session_id,
            factors=final_factors,
            config=config,
            case_description=request.case_description,
            execution_time_ms=execution_time_ms,
        )

        # Store result in cache
        await self._cache.store_result(request.tenant_id, session_id, result)

        yield PredictiveEvent(
            event_type=PredictiveEventType.PREDICTION_COMPLETE,
            data={
                "session_id": session_id,
                "probability": result.probability,
                "confidence_interval": result.confidence_interval,
                "primary_outcome": result.primary_outcome,
                "primary_outcome_label": config.outcome_labels.get(
                    result.primary_outcome, result.primary_outcome
                ),
                "outcome_probabilities": {
                    k: {"probability": v, "label": config.outcome_labels.get(k, k)}
                    for k, v in result.outcome_probabilities.items()
                },
                "factors_extracted": factors_extracted,
                "factors_weighted": factors_weighted,
                "factors_rejected": factors_rejected,
                "recommendation": result.recommendation,
                "disclaimer": result.disclaimer,
                "execution_time_ms": execution_time_ms,
            },
            progress_percent=100,
        )

    async def analyze_sync(self, request: PredictionRequest) -> PredictionResponse:
        """Synchronous analysis — waits for complete result."""
        final_event = None
        async for event in self.analyze(request):
            if event.event_type == PredictiveEventType.PREDICTION_COMPLETE:
                final_event = event

        if not final_event:
            raise Exception("Predictive analysis did not complete")

        data = final_event.data
        session_id = data.get("session_id", "")

        # Reconstruct result from cache
        result = await self._cache.get_result(request.tenant_id, session_id)
        if not result:
            raise Exception("Result not found in cache")

        return PredictionResponse(
            session_id=session_id,
            case_description=request.case_description,
            result=result,
            factors_extracted=data.get("factors_extracted", 0),
            factors_weighted=data.get("factors_weighted", 0),
            factors_rejected=data.get("factors_rejected", 0),
            execution_time_ms=data.get("execution_time_ms", 0),
        )

    async def _get_source_context(
        self,
        query: str,
        tenant_id: str,
        document_ids: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        uploaded_texts: Optional[list[dict]] = None,
    ) -> str:
        """Get source context — same pattern as Verified Generation."""
        context_parts: list[str] = []

        # Priority 1: Uploaded documents
        if uploaded_texts:
            for t in uploaded_texts:
                filename = t.get("filename", "Uploaded document")
                text = t.get("text", "")[:3000]
                if text:
                    context_parts.append(f"[{filename}]\n{text}")

        # Priority 2: Weaviate
        if not context_parts:
            sanitized_tenant = tenant_id.replace("-", "_")
            collection_name = (
                collections[0] if collections
                else f"Nouxcube_{sanitized_tenant}_documents"
            )
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-Key": settings.MICROSERVICES_API_KEY,
                        },
                        json={
                            "query": query,
                            "tenant_id": tenant_id,
                            "limit": 10,
                            "search_type": "hybrid",
                            "is_admin": True,
                        },
                    )
                    if response.status_code == 200:
                        results = response.json().get("results", [])
                        for r in results[:5]:
                            title = r.get("title", "Document")
                            content = r.get("content", "")[:2000]
                            context_parts.append(f"[{title}]\n{content}")
            except Exception as e:
                logger.error(f"❌ Weaviate source context failed: {e}")

        return "\n\n---\n\n".join(context_parts)

    async def _search_evidence(
        self,
        factor: PredictionFactor,
        tenant_id: str,
        collections: Optional[List[str]] = None,
        uploaded_texts: Optional[list[dict]] = None,
        config: Optional[PredictiveConfig] = None,
    ) -> list[dict]:
        """Search Weaviate + web for evidence supporting/contradicting a factor."""
        SIMILARITY_THRESHOLD = 0.60
        evidence: list[dict] = []

        # Weaviate search
        sanitized_tenant = tenant_id.replace("-", "_")
        safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
        candidate_collections = (
            [collections[0]] if collections
            else [
                f"Nouxcube_{sanitized_tenant}_documents",
                f"Nouxcube_{safe_tenant}_knowledge",
            ]
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for collection_name in candidate_collections:
                    response = await client.post(
                        f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                        headers={
                            "Content-Type": "application/json",
                            "X-API-Key": settings.MICROSERVICES_API_KEY,
                        },
                        json={
                            "query": factor.description,
                            "tenant_id": tenant_id,
                            "limit": 5,
                            "search_type": "hybrid",
                            "is_admin": True,
                        },
                    )
                    if response.status_code == 200:
                        results = response.json().get("results", [])
                        for r in results:
                            distance = r.get("distance", 1.0)
                            similarity = 1.0 - min(distance, 1.0)
                            if similarity >= SIMILARITY_THRESHOLD:
                                evidence.append({
                                    "document_id": r.get("document_id", ""),
                                    "document_title": r.get("title", ""),
                                    "chunk_id": r.get("chunk_id"),
                                    "text_excerpt": r.get("content", "")[:500],
                                    "similarity_score": round(similarity, 3),
                                    "source": "internal",
                                })
                        if evidence:
                            break
        except Exception as e:
            logger.error(f"❌ Weaviate evidence search failed: {e}")

        # Uploaded documents (RLM-powered filtering)
        if not evidence and uploaded_texts:
            try:
                from app.services.verified_generation.service import _rlm_filter_evidence
                evidence = await _rlm_filter_evidence(
                    factor.description, uploaded_texts, max_evidence=5
                )
            except Exception as e:
                logger.warning(f"⚠️ RLM evidence filtering failed: {e}")

        # Web search (if configured)
        if (config and "web" in config.verification_sources
                and settings.web_search_enabled and len(evidence) < 5):
            try:
                from app.services.web_search import get_web_search_client
                import hashlib
                web_client = get_web_search_client()
                web_results = await asyncio.wait_for(
                    web_client.search(factor.description, max_results=3),
                    timeout=10.0,
                )
                for wr in web_results:
                    url_hash = hashlib.md5(wr.url.encode()).hexdigest()[:12]
                    evidence.append({
                        "document_id": f"web:{url_hash}",
                        "document_title": wr.title,
                        "chunk_id": None,
                        "text_excerpt": wr.snippet[:500],
                        "similarity_score": 0.65,
                        "source": "web",
                        "url": wr.url,
                    })
            except asyncio.TimeoutError:
                logger.warning("⏱️ Web search timed out")
            except Exception as e:
                logger.warning(f"Web search failed (non-fatal): {e}")

        logger.info(f"🔍 Found {len(evidence)} evidence items for factor [{factor.factor_type}]")
        return evidence

    async def _weight_factor(
        self,
        factor: PredictionFactor,
        matches: List[VerificationMatch],
        config: PredictiveConfig,
        confidence_threshold: float,
    ) -> Optional[WeightedFactor]:
        """
        Weight a factor using LLM evaluation + statistical outcome ratio.

        Returns None if below confidence threshold.
        """
        if not matches:
            return None

        # Compute outcome ratio from matches
        outcome_keys = list(config.outcome_labels.keys())
        outcome_counts: Dict[str, int] = {k: 0 for k in outcome_keys}
        supporting_count = 0

        for m in matches:
            if m.outcome in outcome_counts:
                outcome_counts[m.outcome] += 1
            if m.supports_factor:
                supporting_count += 1

        total_matches = len(matches)
        outcome_ratio = {k: v / total_matches for k, v in outcome_counts.items()} if total_matches > 0 else {}

        # Determine primary outcome for this factor
        primary_outcome = max(outcome_counts, key=outcome_counts.get) if outcome_counts else outcome_keys[0]

        # LLM weight evaluation
        weight, confidence = await self._llm_weight_factor(
            factor, matches, config
        )

        if confidence < confidence_threshold:
            logger.info(
                f"⚠️ Factor [{factor.factor_type}] below threshold "
                f"(confidence={confidence:.2f} < {confidence_threshold})"
            )
            return None

        return WeightedFactor(
            id=factor.id,
            factor_type=factor.factor_type,
            description=factor.description,
            legal_basis=factor.legal_basis,
            weight=weight,
            confidence=confidence,
            outcome=primary_outcome,
            outcome_ratio=outcome_ratio,
            supporting_matches=matches[:5],  # Cap stored matches
            extraction_order=factor.extraction_order,
        )

    async def _llm_weight_factor(
        self,
        factor: PredictionFactor,
        matches: List[VerificationMatch],
        config: PredictiveConfig,
    ) -> tuple[float, float]:
        """Use LLM to determine factor weight and confidence."""
        matches_summary = "\n".join(
            f"- [{m.outcome}] {m.text_excerpt[:200]}..."
            for m in matches[:5]
        )

        system_prompt = (
            "You are an expert analyst evaluating the weight of a factor in predictive analysis.\n\n"
            "Respond ONLY with a JSON object:\n"
            '{"weight": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
            "weight: How impactful is this factor? (0=negligible, 1=decisive)\n"
            "confidence: How certain are you? (0=no evidence, 1=strong evidence)\n"
            "NEVER use <think> tags."
        )

        user_prompt = (
            f"FACTOR: [{factor.factor_type}] {factor.description}\n"
            f"Legal basis: {factor.legal_basis or 'N/A'}\n\n"
            f"SUPPORTING EVIDENCE ({len(matches)} matches):\n{matches_summary}\n\n"
            "Evaluate the weight and confidence. JSON only."
        )

        try:
            from app.agents.llm_client import get_llm_client
            llm_client = await get_llm_client()
            response = await llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=200,
                enable_thinking=False,
            )

            if response and response.content:
                content = response.content.strip()
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                if '<think>' in content:
                    content = content[:content.find('<think>')]
                content = content.strip()

                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                try:
                    result = json.loads(content)
                    return (
                        float(result.get("weight", 0.5)),
                        float(result.get("confidence", 0.5)),
                    )
                except json.JSONDecodeError:
                    json_match = re.search(r'\{[^{}]*"weight"[^{}]*\}', content)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            return (
                                float(result.get("weight", 0.5)),
                                float(result.get("confidence", 0.5)),
                            )
                        except json.JSONDecodeError:
                            pass

        except Exception as e:
            logger.error(f"❌ LLM factor weighting failed: {e}")

        # Fallback: heuristic based on match count
        return (
            min(0.3 + len(matches) * 0.1, 0.8),
            min(0.4 + len(matches) * 0.1, 0.7),
        )


# =============================================================================
# Singleton
# =============================================================================

_predictive_service: Optional[PredictiveAnalysisService] = None


def get_predictive_analysis_service() -> PredictiveAnalysisService:
    global _predictive_service
    if _predictive_service is None:
        _predictive_service = PredictiveAnalysisService()
    return _predictive_service


async def initialize_predictive_analysis_service() -> PredictiveAnalysisService:
    service = get_predictive_analysis_service()
    await service.initialize()
    return service
