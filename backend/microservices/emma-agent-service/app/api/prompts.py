"""
Prompt Management API — Proxy endpoints that call the main API for database operations.

This module provides REST endpoints for:
- Rules: CRUD and evaluation
- Few-Shot: CRUD, search, and feedback
- Guardrails: CRUD and testing
- Utilities: Cache invalidation, health, Langfuse sync

Architecture:
- Database operations are handled by the main API (backend:8000)
- This service calls the main API via HTTP for all CRUD operations
- Local services (RuleEngine, FewShotRetriever, GuardrailService) handle business logic
"""

import logging
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query

from app.core.config import settings
from app.services.prompt_composer import get_prompt_composer
from app.services.rule_engine import get_rule_engine, RuleContext
from app.services.few_shot_retriever import get_few_shot_retriever
from app.services.guardrail_service import get_guardrail_service
from app.services.langfuse_prompt_client import get_langfuse_prompt_client
from app.schemas.prompts import (
    # Rules
    PromptRuleCreate,
    PromptRuleUpdate,
    PromptRuleResponse,
    PromptRuleListResponse,
    RuleEvaluationRequest,
    RuleEvaluationResult,
    # Few-Shot
    FewShotExampleCreate,
    FewShotExampleUpdate,
    FewShotExampleResponse,
    FewShotExampleListResponse,
    FewShotSearchRequest,
    FewShotSearchResponse,
    FewShotFeedbackRequest,
    FewShotDomain,
    # Guardrails
    GuardrailCreate,
    GuardrailUpdate,
    GuardrailResponse,
    GuardrailListResponse,
    GuardrailTestRequest,
    GuardrailTestResponse,
    GuardrailTestResult,
    GuardrailAction,
    # Utilities
    CacheInvalidateRequest,
    CacheInvalidateResponse,
    PromptHealthResponse,
    LangfuseSyncRequest,
    LangfuseSyncResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])

# Main API base URL
MAIN_API_URL = settings.api_url  # e.g., "http://api:8000"


# ══════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT
# ══════════════════════════════════════════════════════════════════════════════

async def _call_main_api(
    method: str,
    path: str,
    tenant_id: Optional[UUID] = None,
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Call main API with proper headers and error handling."""
    headers = {
        "X-API-Key": settings.MICROSERVICES_API_KEY,
        "Content-Type": "application/json",
    }
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)

    url = f"{MAIN_API_URL}/api/v1/prompts{path}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.HTTPStatusError as e:
            logger.error(f"Main API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=e.response.json() if e.response.content else str(e)
            )
        except httpx.RequestError as e:
            logger.error(f"Main API connection error: {e}")
            raise HTTPException(status_code=503, detail=f"Main API unavailable: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# DEPENDENCIES
# ══════════════════════════════════════════════════════════════════════════════

def get_tenant_id(x_tenant_id: Optional[str] = Header(None)) -> Optional[UUID]:
    """Extract tenant ID from header."""
    if x_tenant_id:
        try:
            return UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    return None


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Verify microservices API key."""
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# RULES ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/rules", response_model=PromptRuleResponse)
async def create_rule(
    rule: PromptRuleCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Create a new prompt injection rule."""
    result = await _call_main_api(
        "POST",
        "/rules",
        tenant_id=tenant_id,
        json_data={
            "rule_name": rule.rule_name,
            "description": rule.description,
            "conditions": rule.conditions.model_dump(exclude_none=True),
            "action_type": rule.action_type.value,
            "action_config": rule.action_config.model_dump(exclude_none=True),
            "priority": rule.priority,
            "is_active": rule.is_active,
        },
    )

    # Invalidate local cache
    get_rule_engine().invalidate_cache(tenant_id)

    return result


@router.get("/rules", response_model=PromptRuleListResponse)
async def list_rules(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    active_only: bool = Query(True),
    _: bool = Depends(verify_api_key),
):
    """List prompt rules for tenant."""
    rules = await _call_main_api(
        "GET",
        "/rules",
        tenant_id=tenant_id,
        params={"active_only": active_only},
    )
    return PromptRuleListResponse(rules=rules, total=len(rules))


@router.put("/rules/{rule_id}", response_model=PromptRuleResponse)
async def update_rule(
    rule_id: UUID,
    rule: PromptRuleUpdate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Update an existing prompt rule."""
    update_data = {}
    if rule.rule_name is not None:
        update_data["rule_name"] = rule.rule_name
    if rule.description is not None:
        update_data["description"] = rule.description
    if rule.conditions is not None:
        update_data["conditions"] = rule.conditions.model_dump(exclude_none=True)
    if rule.action_type is not None:
        update_data["action_type"] = rule.action_type.value
    if rule.action_config is not None:
        update_data["action_config"] = rule.action_config.model_dump(exclude_none=True)
    if rule.priority is not None:
        update_data["priority"] = rule.priority
    if rule.is_active is not None:
        update_data["is_active"] = rule.is_active

    result = await _call_main_api(
        "PUT",
        f"/rules/{rule_id}",
        tenant_id=tenant_id,
        json_data=update_data,
    )

    # Invalidate local cache
    get_rule_engine().invalidate_cache(tenant_id)

    return result


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a prompt rule."""
    result = await _call_main_api(
        "DELETE",
        f"/rules/{rule_id}",
        tenant_id=tenant_id,
    )

    # Invalidate local cache
    get_rule_engine().invalidate_cache(tenant_id)

    return result


@router.post("/rules/evaluate", response_model=RuleEvaluationResult)
async def evaluate_rules(
    context: RuleEvaluationRequest,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Evaluate rules against a mock context for testing."""
    try:
        rule_context = RuleContext(
            document_type=context.document_type,
            action=context.action,
            sector=context.sector,
            domain=context.domain,
            has_docs=context.has_docs,
            user_role=context.user_role,
            locale=context.locale,
            custom=context.custom or {},
        )

        engine = get_rule_engine()
        result = await engine.evaluate(rule_context, tenant_id)

        return result

    except Exception as e:
        logger.error(f"Failed to evaluate rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# FEW-SHOT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/few-shot", response_model=FewShotExampleResponse)
async def create_few_shot_example(
    example: FewShotExampleCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Add a new few-shot example with auto-generated embedding."""
    try:
        retriever = get_few_shot_retriever()

        # Generate embedding locally (we have the embedding model)
        embedding = await retriever._get_embedding(example.question)

        # Call main API with embedding
        result = await _call_main_api(
            "POST",
            "/few-shot",
            tenant_id=tenant_id,
            json_data={
                "question": example.question,
                "answer": example.answer,
                "category": example.category,
                "domain": example.domain.value if example.domain else None,
                "tags": example.tags,
                "quality_score": example.quality_score,
                "embedding": embedding,
            },
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create few-shot example: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/few-shot", response_model=FewShotExampleListResponse)
async def list_few_shot_examples(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    domain: Optional[FewShotDomain] = Query(None),
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: bool = Depends(verify_api_key),
):
    """List few-shot examples with filtering."""
    params = {
        "active_only": active_only,
        "limit": limit,
        "offset": offset,
    }
    if domain:
        params["domain"] = domain.value
    if category:
        params["category"] = category

    examples = await _call_main_api(
        "GET",
        "/few-shot",
        tenant_id=tenant_id,
        params=params,
    )

    return FewShotExampleListResponse(examples=examples, total=len(examples))


@router.post("/few-shot/search", response_model=FewShotSearchResponse)
async def search_few_shot_examples(
    request: FewShotSearchRequest,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Search for similar few-shot examples using semantic similarity."""
    try:
        start_time = time.time()
        retriever = get_few_shot_retriever()

        # Use local retriever for search (has embedding model)
        examples = await retriever.search(
            request.query,
            limit=request.limit,
            tenant_id=tenant_id,
            domain=request.domain,
            category=request.category,
            min_quality_score=request.min_quality_score,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return FewShotSearchResponse(
            examples=[
                FewShotExampleResponse(
                    id=ex.id,
                    tenant_id=tenant_id,
                    question=ex.question,
                    answer=ex.answer,
                    category=ex.category,
                    domain=ex.domain,
                    tags=ex.tags,
                    quality_score=ex.quality_score,
                    usage_count=0,
                    positive_feedback=0,
                    negative_feedback=0,
                    is_active=True,
                    created_at=None,
                    updated_at=None,
                    similarity_score=ex.similarity_score,
                )
                for ex in examples
            ],
            query=request.query,
            search_time_ms=elapsed_ms,
        )

    except Exception as e:
        logger.error(f"Failed to search few-shot examples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/few-shot/{example_id}")
async def delete_few_shot_example(
    example_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a few-shot example."""
    return await _call_main_api(
        "DELETE",
        f"/few-shot/{example_id}",
        tenant_id=tenant_id,
    )


@router.post("/few-shot/feedback")
async def submit_few_shot_feedback(
    request: FewShotFeedbackRequest,
    _: bool = Depends(verify_api_key),
):
    """Submit feedback for a few-shot example."""
    return await _call_main_api(
        "POST",
        f"/few-shot/{request.example_id}/feedback",
        params={"is_positive": request.is_positive},
    )


# ══════════════════════════════════════════════════════════════════════════════
# GUARDRAILS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/guardrails", response_model=GuardrailResponse)
async def create_guardrail(
    guardrail: GuardrailCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Create a new guardrail."""
    result = await _call_main_api(
        "POST",
        "/guardrails",
        tenant_id=tenant_id,
        json_data={
            "guardrail_name": guardrail.guardrail_name,
            "description": guardrail.description,
            "guardrail_type": guardrail.guardrail_type.value,
            "config": guardrail.config.model_dump(exclude_none=True),
            "action_on_match": guardrail.action_on_match.value,
            "applies_to": guardrail.applies_to,
            "priority": guardrail.priority,
            "is_active": guardrail.is_active,
        },
    )

    # Invalidate local cache
    get_guardrail_service().invalidate_cache(tenant_id)

    return result


@router.get("/guardrails", response_model=GuardrailListResponse)
async def list_guardrails(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    active_only: bool = Query(True),
    _: bool = Depends(verify_api_key),
):
    """List guardrails for tenant."""
    guardrails = await _call_main_api(
        "GET",
        "/guardrails",
        tenant_id=tenant_id,
        params={"active_only": active_only},
    )
    return GuardrailListResponse(guardrails=guardrails, total=len(guardrails))


@router.put("/guardrails/{guardrail_id}", response_model=GuardrailResponse)
async def update_guardrail(
    guardrail_id: UUID,
    guardrail: GuardrailUpdate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Update an existing guardrail."""
    update_data = {}
    if guardrail.guardrail_name is not None:
        update_data["guardrail_name"] = guardrail.guardrail_name
    if guardrail.description is not None:
        update_data["description"] = guardrail.description
    if guardrail.guardrail_type is not None:
        update_data["guardrail_type"] = guardrail.guardrail_type.value
    if guardrail.config is not None:
        update_data["config"] = guardrail.config.model_dump(exclude_none=True)
    if guardrail.action_on_match is not None:
        update_data["action_on_match"] = guardrail.action_on_match.value
    if guardrail.applies_to is not None:
        update_data["applies_to"] = guardrail.applies_to
    if guardrail.priority is not None:
        update_data["priority"] = guardrail.priority
    if guardrail.is_active is not None:
        update_data["is_active"] = guardrail.is_active

    result = await _call_main_api(
        "PUT",
        f"/guardrails/{guardrail_id}",
        tenant_id=tenant_id,
        json_data=update_data,
    )

    # Invalidate local cache
    get_guardrail_service().invalidate_cache(tenant_id)

    return result


@router.delete("/guardrails/{guardrail_id}")
async def delete_guardrail(
    guardrail_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a guardrail."""
    result = await _call_main_api(
        "DELETE",
        f"/guardrails/{guardrail_id}",
        tenant_id=tenant_id,
    )

    # Invalidate local cache
    get_guardrail_service().invalidate_cache(tenant_id)

    return result


@router.post("/guardrails/test", response_model=GuardrailTestResponse)
async def test_guardrails(
    request: GuardrailTestRequest,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    _: bool = Depends(verify_api_key),
):
    """Test all applicable guardrails against sample content."""
    try:
        start_time = time.time()
        service = get_guardrail_service()

        result = await service.validate(
            request.content,
            agent_name=request.agent_name,
            tenant_id=tenant_id,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return GuardrailTestResponse(
            results=[
                GuardrailTestResult(
                    guardrail_id=r.guardrail_id,
                    guardrail_name=r.guardrail_name,
                    matched=r.matched,
                    action=r.action,
                    details=r.details,
                    matched_content=r.matched_content,
                )
                for r in result.results
            ],
            overall_action=result.overall_action,
            would_block=result.should_block,
            processing_time_ms=elapsed_ms,
        )

    except Exception as e:
        logger.error(f"Failed to test guardrails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/cache/invalidate", response_model=CacheInvalidateResponse)
async def invalidate_cache(
    request: CacheInvalidateRequest = CacheInvalidateRequest(),
    _: bool = Depends(verify_api_key),
):
    """Invalidate prompt cache (local and Langfuse)."""
    try:
        composer = get_prompt_composer()
        count = composer.invalidate_cache(request.prompt_names)

        return CacheInvalidateResponse(
            invalidated_count=count,
            message=f"Invalidated {count} cached entries",
        )

    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/langfuse", response_model=LangfuseSyncResponse)
async def sync_from_langfuse(
    request: LangfuseSyncRequest = LangfuseSyncRequest(),
    _: bool = Depends(verify_api_key),
):
    """Force sync prompts from Langfuse."""
    try:
        start_time = time.time()
        client = get_langfuse_prompt_client()

        if request.force:
            client.invalidate_cache()

        synced = await client.sync_from_langfuse()
        elapsed_ms = (time.time() - start_time) * 1000

        return LangfuseSyncResponse(
            synced_prompts=synced,
            sync_time_ms=elapsed_ms,
            errors=None,
        )

    except Exception as e:
        logger.error(f"Failed to sync from Langfuse: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=PromptHealthResponse)
async def health_check(
    _: bool = Depends(verify_api_key),
):
    """Get health status of prompt management system."""
    try:
        # Check local components
        composer = get_prompt_composer()
        health = await composer.get_health()

        # Check main API
        try:
            api_health = await _call_main_api("GET", "/health")
            db_connected = api_health.get("database", {}).get("connected", False)
            counts = api_health.get("counts", {})
        except Exception as e:
            logger.warning(f"Main API health check failed: {e}")
            db_connected = False
            counts = {}

        return PromptHealthResponse(
            langfuse_connected=health.get("langfuse_connected", False),
            langfuse_host=settings.langfuse_host,
            database_connected=db_connected,
            use_langfuse_prompts=settings.use_langfuse_prompts,
            cached_prompt_count=health.get("cached_prompt_count", 0),
            rules_count=counts.get("rules", 0),
            few_shot_count=counts.get("few_shot_examples", 0),
            guardrails_count=counts.get("guardrails", 0),
            last_sync=None,
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_yaml(
    _: bool = Depends(verify_api_key),
):
    """Reload YAML prompts (hot reload)."""
    try:
        composer = get_prompt_composer()
        composer.reload_yaml()

        return {"message": "YAML cache cleared, will reload on next access"}

    except Exception as e:
        logger.error(f"Failed to reload YAML: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available")
async def list_available_prompts(
    _: bool = Depends(verify_api_key),
):
    """List all available prompts from Langfuse and YAML."""
    try:
        client = get_langfuse_prompt_client()
        prompts = await client.list_available_prompts()

        return prompts

    except Exception as e:
        logger.error(f"Failed to list available prompts: {e}")
        raise HTTPException(status_code=500, detail=str(e))
