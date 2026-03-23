"""
Prompt Management API — CRUD endpoints for rules and guardrails.

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
