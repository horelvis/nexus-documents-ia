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
from app.core.langfuse_config import trace_context, langfuse_context, observe
from app.services.langfuse_prompt_client import get_langfuse_prompt_client
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


from app.services.shared.deduplication import is_duplicate_with_type


def _is_duplicate_factor(
    new_factor: PredictionFactor,
    weighted: List[WeightedFactor],
    all_extracted: Optional[List[PredictionFactor]] = None,
    threshold: float = settings.predictive_duplicate_threshold,
) -> bool:
    """Check if a factor is too similar to any previously extracted factor.

    Checks against BOTH weighted (accepted) and all previously extracted
    factors (including rejected), so the LLM doesn't retry the same factor.
    """
    items = [(ef.description, ef.factor_type) for ef in weighted]
    items += [(ef.description, ef.factor_type) for ef in (all_extracted or [])]
    return is_duplicate_with_type(
        new_factor.description, new_factor.factor_type, items,
        threshold=threshold,
    )


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

        This is the main SSE entry point. Delegates to the StopAndGo
        LangGraph which handles the extract→verify→decide loop.
        """
        await self.initialize()

        start_time = time.time()
        session_id = request.session_id or str(uuid.uuid4())

        # Resolve sector config
        config = get_predictive_config(request.sector_override)

        import os
        sector = os.getenv("ACTIVE_SECTOR", "").strip().lower() or config.system_prompt_key

        with trace_context(
            "predictive.analyze",
            session_id=session_id,
            metadata={"tenant_id": str(request.tenant_id), "sector": sector},
            input={"case_description": request.case_description[:500]},
            tags=["predictive", f"sector:{sector}"],
        ):
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

            # Build initial state for the stop-and-go graph
            from app.agents.langgraph.stop_and_go import (
                get_stop_and_go_graph,
                stream_stop_and_go,
                create_initial_state,
            )

            max_factors = min(request.max_factors, config.max_factors)

            initial_state = create_initial_state(
                session_id=session_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                query=request.case_description,
                mode="predictive",
                max_items=max_factors,
                confidence_threshold=request.confidence_threshold,
                uploaded_texts=uploaded_texts,
                collections=request.collections,
                context_document_ids=request.context_document_ids,
                mode_config={
                    "sector_override": request.sector_override,
                    "verification_sources": config.verification_sources,
                },
            )

            graph = get_stop_and_go_graph()

            # Map graph events → PredictiveEvent SSE types
            EVENT_TYPE_MAP = {
                "progress": PredictiveEventType.PROGRESS,
                "predictive_item_extracted": PredictiveEventType.FACTOR_EXTRACTED,
                "predictive_verification_started": PredictiveEventType.FACTOR_VERIFICATION_STARTED,
                "factor_weighted": PredictiveEventType.FACTOR_WEIGHTED,
                "factor_rejected": PredictiveEventType.FACTOR_REJECTED,
                "predictive_complete": PredictiveEventType.PREDICTION_COMPLETE,
                "section_advanced": PredictiveEventType.PROGRESS,
                "error": PredictiveEventType.ERROR,
            }

            async for event in stream_stop_and_go(graph, initial_state):
                event_type_str = event.get("event_type", "progress")
                mapped_type = EVENT_TYPE_MAP.get(event_type_str)

                if mapped_type is None:
                    continue

                # Compute execution_time_ms for the final event
                if mapped_type == PredictiveEventType.PREDICTION_COMPLETE:
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    data = event.get("data", {})
                    data["execution_time_ms"] = execution_time_ms
                    yield PredictiveEvent(
                        event_type=mapped_type,
                        data=data,
                        progress_percent=100,
                    )
                else:
                    yield PredictiveEvent(
                        event_type=mapped_type,
                        factor_id=event.get("factor_id") or event.get("item_id"),
                        data=event.get("data", {}),
                        progress_percent=event.get("progress_percent"),
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
        similarity_threshold = settings.predictive_similarity_threshold
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
                            if similarity >= similarity_threshold:
                                evidence.append({
                                    "document_id": r.get("document_id", ""),
                                    "document_title": r.get("title", ""),
                                    "chunk_id": r.get("chunk_id"),
                                    "text_excerpt": r.get("content", "")[:settings.predictive_evidence_excerpt_limit],
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
                        "text_excerpt": wr.snippet[:settings.predictive_evidence_excerpt_limit],
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

    @observe(name="predictive.weight_factor")
    async def _llm_weight_factor(
        self,
        factor: PredictionFactor,
        matches: List[VerificationMatch],
        config: PredictiveConfig,
    ) -> tuple[float, float]:
        """Use LLM to determine factor weight and confidence."""
        client = get_langfuse_prompt_client()
        matches_summary = "\n".join(
            f"- [{m.outcome}] {m.text_excerpt[:200]}..."
            for m in matches[:5]
        )

        # System prompt via Langfuse/YAML
        _FALLBACK_WEIGHT_SYSTEM = (
            "Eres un analista experto evaluando el peso de un factor en análisis predictivo.\n\n"
            "Responde SOLO con un objeto JSON:\n"
            '{"weight": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
            "weight: ¿Qué tan impactante es este factor? (0=insignificante, 1=decisivo)\n"
            "confidence: ¿Qué tan seguro estás? (0=sin evidencia, 1=evidencia sólida)\n"
            "NUNCA uses etiquetas <think>."
        )
        sys_cached = await client.get_prompt(
            "emma_predictive_weight_system",
            fallback=_FALLBACK_WEIGHT_SYSTEM,
        )
        system_prompt = sys_cached.content if sys_cached else _FALLBACK_WEIGHT_SYSTEM

        # User prompt via Langfuse/YAML
        _FALLBACK_WEIGHT_USER = (
            "FACTOR: [{factor_type}] {factor_description}\n"
            "Base legal: {legal_basis}\n\n"
            "EVIDENCIA DE APOYO ({match_count} coincidencias):\n{matches_summary}\n\n"
            "Evalúa el peso y la confianza. Solo JSON."
        )
        user_variables = {
            "factor_type": factor.factor_type,
            "factor_description": factor.description,
            "legal_basis": factor.legal_basis or "N/A",
            "match_count": str(len(matches)),
            "matches_summary": matches_summary,
        }
        user_cached = await client.get_prompt(
            "emma_predictive_weight_user",
            variables=user_variables,
            fallback=_FALLBACK_WEIGHT_USER.format(**user_variables),
        )
        user_prompt = user_cached.content if user_cached else _FALLBACK_WEIGHT_USER.format(
            **user_variables
        )

        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_planner_model

            model = get_planner_model().bind(temperature=0.1, max_tokens=200)
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])

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
                        float(result.get("weight", settings.predictive_fallback_weight)),
                        float(result.get("confidence", settings.predictive_fallback_confidence)),
                    )
                except json.JSONDecodeError:
                    json_match = re.search(r'\{[^{}]*"weight"[^{}]*\}', content)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            return (
                                float(result.get("weight", settings.predictive_fallback_weight)),
                                float(result.get("confidence", settings.predictive_fallback_confidence)),
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
