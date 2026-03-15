"""
Prompt Management API — CRUD endpoints for rules, few-shot examples, and guardrails.

This module provides database access for prompt management tables.
Emma Agent Service calls these endpoints via HTTP.

NOTE: Uses synchronous database session (get_db returns Session, not AsyncSession).
"""

import logging
import json
from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.database import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class PromptRuleCreate(BaseModel):
    rule_name: str
    description: Optional[str] = None
    conditions: Dict[str, Any]
    action_type: str
    action_config: Dict[str, Any]
    priority: int = 100
    is_active: bool = True


class PromptRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None
    action_type: Optional[str] = None
    action_config: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class PromptRuleResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    rule_name: str
    description: Optional[str] = None
    conditions: Dict[str, Any]
    action_type: str
    action_config: Dict[str, Any]
    priority: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FewShotExampleCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[List[str]] = None
    quality_score: float = 1.0
    embedding: Optional[List[float]] = None


class FewShotExampleResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    question: str
    answer: str
    category: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[List[str]] = None
    quality_score: float
    usage_count: int = 0
    positive_feedback: int = 0
    negative_feedback: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GuardrailCreate(BaseModel):
    guardrail_name: str
    description: Optional[str] = None
    guardrail_type: str
    config: Dict[str, Any]
    action_on_match: str
    applies_to: Optional[List[str]] = None
    priority: int = 100
    is_active: bool = True
    sector: Optional[str] = None


class GuardrailResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    guardrail_name: str
    description: Optional[str] = None
    guardrail_type: str
    config: Dict[str, Any]
    action_on_match: str
    applies_to: Optional[List[str]] = None
    priority: int
    is_active: bool
    sector: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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
def create_rule(
    rule: PromptRuleCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Create a new prompt injection rule."""
    try:
        query = text("""
            INSERT INTO emma_prompt_rules
                (tenant_id, rule_name, description, conditions, action_type, action_config, priority, is_active)
            VALUES
                (:tenant_id, :rule_name, :description, CAST(:conditions AS jsonb), :action_type, CAST(:action_config AS jsonb), :priority, :is_active)
            RETURNING id, tenant_id, rule_name, description, conditions, action_type, action_config, priority, is_active, created_at, updated_at
        """)

        result = db.execute(
            query,
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "rule_name": rule.rule_name,
                "description": rule.description,
                "conditions": json.dumps(rule.conditions),
                "action_type": rule.action_type,
                "action_config": json.dumps(rule.action_config),
                "priority": rule.priority,
                "is_active": rule.is_active,
            },
        )
        row = result.fetchone()
        db.commit()

        return PromptRuleResponse(
            id=row[0],
            tenant_id=row[1],
            rule_name=row[2],
            description=row[3],
            conditions=row[4],
            action_type=row[5],
            action_config=row[6],
            priority=row[7],
            is_active=row[8],
            created_at=row[9],
            updated_at=row[10],
        )

    except Exception as e:
        logger.error(f"Failed to create rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules", response_model=List[PromptRuleResponse])
def list_rules(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """List prompt rules for tenant."""
    try:
        query = text("""
            SELECT id, tenant_id, rule_name, description, conditions, action_type, action_config, priority, is_active, created_at, updated_at
            FROM emma_prompt_rules
            WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)
              AND (:active_only = false OR is_active = true)
            ORDER BY priority ASC
        """)

        result = db.execute(
            query,
            {"tenant_id": str(tenant_id) if tenant_id else None, "active_only": active_only},
        )
        rows = result.fetchall()

        return [
            PromptRuleResponse(
                id=row[0],
                tenant_id=row[1],
                rule_name=row[2],
                description=row[3],
                conditions=row[4],
                action_type=row[5],
                action_config=row[6],
                priority=row[7],
                is_active=row[8],
                created_at=row[9],
                updated_at=row[10],
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to list rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rules/{rule_id}", response_model=PromptRuleResponse)
def update_rule(
    rule_id: UUID,
    rule: PromptRuleUpdate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Update an existing prompt rule."""
    try:
        updates = []
        params = {"rule_id": str(rule_id), "tenant_id": str(tenant_id) if tenant_id else None}

        if rule.rule_name is not None:
            updates.append("rule_name = :rule_name")
            params["rule_name"] = rule.rule_name
        if rule.description is not None:
            updates.append("description = :description")
            params["description"] = rule.description
        if rule.conditions is not None:
            updates.append("conditions = CAST(:conditions AS jsonb)")
            params["conditions"] = json.dumps(rule.conditions)
        if rule.action_type is not None:
            updates.append("action_type = :action_type")
            params["action_type"] = rule.action_type
        if rule.action_config is not None:
            updates.append("action_config = CAST(:action_config AS jsonb)")
            params["action_config"] = json.dumps(rule.action_config)
        if rule.priority is not None:
            updates.append("priority = :priority")
            params["priority"] = rule.priority
        if rule.is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = rule.is_active

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = now()")

        query = text(f"""
            UPDATE emma_prompt_rules
            SET {", ".join(updates)}
            WHERE id = :rule_id AND (tenant_id = :tenant_id OR tenant_id IS NULL)
            RETURNING id, tenant_id, rule_name, description, conditions, action_type, action_config, priority, is_active, created_at, updated_at
        """)

        result = db.execute(query, params)
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")

        return PromptRuleResponse(
            id=row[0],
            tenant_id=row[1],
            rule_name=row[2],
            description=row[3],
            conditions=row[4],
            action_type=row[5],
            action_config=row[6],
            priority=row[7],
            is_active=row[8],
            created_at=row[9],
            updated_at=row[10],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a prompt rule."""
    try:
        query = text("""
            UPDATE emma_prompt_rules
            SET is_active = false, updated_at = now()
            WHERE id = :rule_id AND (tenant_id = :tenant_id OR tenant_id IS NULL)
            RETURNING id
        """)

        result = db.execute(
            query,
            {"rule_id": str(rule_id), "tenant_id": str(tenant_id) if tenant_id else None},
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Rule not found")

        return {"message": "Rule deactivated", "id": str(rule_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# FEW-SHOT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/few-shot", response_model=FewShotExampleResponse)
def create_few_shot_example(
    example: FewShotExampleCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Add a new few-shot example."""
    try:
        if example.embedding:
            query = text("""
                INSERT INTO emma_few_shot_examples
                    (tenant_id, question, answer, category, domain, tags, quality_score, embedding)
                VALUES
                    (:tenant_id, :question, :answer, :category, :domain, :tags, :quality_score, CAST(:embedding AS vector))
                RETURNING id, tenant_id, question, answer, category, domain, tags, quality_score, usage_count, positive_feedback, negative_feedback, is_active, created_at, updated_at
            """)
            params = {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "question": example.question,
                "answer": example.answer,
                "category": example.category,
                "domain": example.domain,
                "tags": example.tags,
                "quality_score": example.quality_score,
                "embedding": str(example.embedding),
            }
        else:
            query = text("""
                INSERT INTO emma_few_shot_examples
                    (tenant_id, question, answer, category, domain, tags, quality_score)
                VALUES
                    (:tenant_id, :question, :answer, :category, :domain, :tags, :quality_score)
                RETURNING id, tenant_id, question, answer, category, domain, tags, quality_score, usage_count, positive_feedback, negative_feedback, is_active, created_at, updated_at
            """)
            params = {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "question": example.question,
                "answer": example.answer,
                "category": example.category,
                "domain": example.domain,
                "tags": example.tags,
                "quality_score": example.quality_score,
            }

        result = db.execute(query, params)
        row = result.fetchone()
        db.commit()

        return FewShotExampleResponse(
            id=row[0],
            tenant_id=row[1],
            question=row[2],
            answer=row[3],
            category=row[4],
            domain=row[5],
            tags=row[6],
            quality_score=row[7],
            usage_count=row[8],
            positive_feedback=row[9],
            negative_feedback=row[10],
            is_active=row[11],
            created_at=row[12],
            updated_at=row[13],
        )

    except Exception as e:
        logger.error(f"Failed to create few-shot example: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/few-shot", response_model=List[FewShotExampleResponse])
def list_few_shot_examples(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    domain: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """List few-shot examples with filtering."""
    try:
        query = text("""
            SELECT id, tenant_id, question, answer, category, domain, tags,
                   quality_score, usage_count, positive_feedback, negative_feedback,
                   is_active, created_at, updated_at
            FROM emma_few_shot_examples
            WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)
              AND (:domain IS NULL OR domain = :domain)
              AND (:category IS NULL OR category = :category)
              AND (:active_only = false OR is_active = true)
            ORDER BY quality_score DESC, usage_count DESC
            LIMIT :limit OFFSET :offset
        """)

        result = db.execute(
            query,
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "domain": domain,
                "category": category,
                "active_only": active_only,
                "limit": limit,
                "offset": offset,
            },
        )
        rows = result.fetchall()

        return [
            FewShotExampleResponse(
                id=row[0],
                tenant_id=row[1],
                question=row[2],
                answer=row[3],
                category=row[4],
                domain=row[5],
                tags=row[6],
                quality_score=row[7],
                usage_count=row[8],
                positive_feedback=row[9],
                negative_feedback=row[10],
                is_active=row[11],
                created_at=row[12],
                updated_at=row[13],
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to list few-shot examples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/few-shot/search")
def search_few_shot_examples(
    query_text: str,
    embedding: List[float],
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    domain: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
    min_quality_score: float = Query(0.5),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Search for similar few-shot examples using vector similarity."""
    try:
        query = text("""
            SELECT id, tenant_id, question, answer, category, domain, tags,
                   quality_score, usage_count,
                   1 - (embedding <=> CAST(:embedding AS vector)) as similarity_score
            FROM emma_few_shot_examples
            WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)
              AND is_active = true
              AND quality_score >= :min_quality_score
              AND (:domain IS NULL OR domain = :domain)
              AND (:category IS NULL OR category = :category)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        result = db.execute(
            query,
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "embedding": str(embedding),
                "domain": domain,
                "category": category,
                "limit": limit,
                "min_quality_score": min_quality_score,
            },
        )
        rows = result.fetchall()

        return [
            {
                "id": str(row[0]),
                "tenant_id": str(row[1]) if row[1] else None,
                "question": row[2],
                "answer": row[3],
                "category": row[4],
                "domain": row[5],
                "tags": row[6],
                "quality_score": row[7],
                "usage_count": row[8],
                "similarity_score": float(row[9]) if row[9] else None,
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to search few-shot examples: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/few-shot/{example_id}")
def delete_few_shot_example(
    example_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a few-shot example."""
    try:
        query = text("""
            UPDATE emma_few_shot_examples
            SET is_active = false, updated_at = now()
            WHERE id = :example_id AND (tenant_id = :tenant_id OR tenant_id IS NULL)
            RETURNING id
        """)

        result = db.execute(
            query,
            {"example_id": str(example_id), "tenant_id": str(tenant_id) if tenant_id else None},
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Example not found")

        return {"message": "Example deactivated", "id": str(example_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete few-shot example: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/few-shot/{example_id}/feedback")
def submit_few_shot_feedback(
    example_id: UUID,
    is_positive: bool,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Submit feedback for a few-shot example."""
    try:
        field = "positive_feedback" if is_positive else "negative_feedback"
        query = text(f"""
            UPDATE emma_few_shot_examples
            SET {field} = {field} + 1, usage_count = usage_count + 1, updated_at = now()
            WHERE id = :example_id
            RETURNING id
        """)

        result = db.execute(query, {"example_id": str(example_id)})
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Example not found")

        return {"message": "Feedback recorded", "example_id": str(example_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# GUARDRAILS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/guardrails", response_model=GuardrailResponse)
def create_guardrail(
    guardrail: GuardrailCreate,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Create a new guardrail."""
    try:
        query = text("""
            INSERT INTO emma_guardrails
                (tenant_id, guardrail_name, description, guardrail_type, config, action_on_match, applies_to, priority, is_active, sector)
            VALUES
                (:tenant_id, :guardrail_name, :description, :guardrail_type, CAST(:config AS jsonb), :action_on_match, :applies_to, :priority, :is_active, :sector)
            RETURNING id, tenant_id, guardrail_name, description, guardrail_type, config, action_on_match, applies_to, priority, is_active, sector, created_at, updated_at
        """)

        result = db.execute(
            query,
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "guardrail_name": guardrail.guardrail_name,
                "description": guardrail.description,
                "guardrail_type": guardrail.guardrail_type,
                "config": json.dumps(guardrail.config),
                "action_on_match": guardrail.action_on_match,
                "applies_to": guardrail.applies_to,
                "priority": guardrail.priority,
                "is_active": guardrail.is_active,
                "sector": guardrail.sector,
            },
        )
        row = result.fetchone()
        db.commit()

        return GuardrailResponse(
            id=row[0],
            tenant_id=row[1],
            guardrail_name=row[2],
            description=row[3],
            guardrail_type=row[4],
            config=row[5],
            action_on_match=row[6],
            applies_to=row[7],
            priority=row[8],
            is_active=row[9],
            sector=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    except Exception as e:
        logger.error(f"Failed to create guardrail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guardrails", response_model=List[GuardrailResponse])
def list_guardrails(
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    active_only: bool = Query(True),
    sector: Optional[str] = Query(None, description="Filter by sector (legal, medical, documental). Returns sector-specific + global guardrails."),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """List guardrails for tenant, optionally filtered by sector."""
    try:
        query = text("""
            SELECT id, tenant_id, guardrail_name, description, guardrail_type, config, action_on_match, applies_to, priority, is_active, sector, created_at, updated_at
            FROM emma_guardrails
            WHERE (tenant_id = :tenant_id OR tenant_id IS NULL)
              AND (:active_only = false OR is_active = true)
              AND (:sector IS NULL OR sector = :sector OR sector IS NULL)
            ORDER BY priority ASC
        """)

        result = db.execute(
            query,
            {
                "tenant_id": str(tenant_id) if tenant_id else None,
                "active_only": active_only,
                "sector": sector,
            },
        )
        rows = result.fetchall()

        return [
            GuardrailResponse(
                id=row[0],
                tenant_id=row[1],
                guardrail_name=row[2],
                description=row[3],
                guardrail_type=row[4],
                config=row[5],
                action_on_match=row[6],
                applies_to=row[7],
                priority=row[8],
                is_active=row[9],
                sector=row[10],
                created_at=row[11],
                updated_at=row[12],
            )
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Failed to list guardrails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/guardrails/{guardrail_id}")
def delete_guardrail(
    guardrail_id: UUID,
    tenant_id: Optional[UUID] = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Delete (deactivate) a guardrail."""
    try:
        query = text("""
            UPDATE emma_guardrails
            SET is_active = false, updated_at = now()
            WHERE id = :guardrail_id AND (tenant_id = :tenant_id OR tenant_id IS NULL)
            RETURNING id
        """)

        result = db.execute(
            query,
            {"guardrail_id": str(guardrail_id), "tenant_id": str(tenant_id) if tenant_id else None},
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Guardrail not found")

        return {"message": "Guardrail deactivated", "id": str(guardrail_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete guardrail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/health")
def health_check(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Get health status of prompt management tables."""
    try:
        counts = {}

        # Count rules
        result = db.execute(text("SELECT COUNT(*) FROM emma_prompt_rules WHERE is_active = true"))
        counts["rules"] = result.scalar() or 0

        # Count few-shot examples
        result = db.execute(text("SELECT COUNT(*) FROM emma_few_shot_examples WHERE is_active = true"))
        counts["few_shot_examples"] = result.scalar() or 0

        # Count guardrails
        result = db.execute(text("SELECT COUNT(*) FROM emma_guardrails WHERE is_active = true"))
        counts["guardrails"] = result.scalar() or 0

        return {
            "status": "healthy",
            "database": {"connected": True},
            "counts": counts,
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": {"connected": False, "error": str(e)},
            "counts": {},
        }
