"""
Tenant expert management routes for MEN service.

Endpoints for managing tenant-specific experts:
- GET /men/tenants/{tenant_id}/experts
- POST /men/tenants/{tenant_id}/experts/register
- POST /men/tenants/{tenant_id}/experts/train
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from ..core.security import verify_api_key
from ..services import get_men_system

from .schemas import (
    TenantExpertsResponse,
    ExpertInfo,
    RegisterExpertRequest,
    RegisterExpertResponse,
    TrainingRequest,
    TrainingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/men/tenants", tags=["MEN Tenants"])


@router.get("/{tenant_id}/experts", response_model=TenantExpertsResponse)
async def list_tenant_experts(
    tenant_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    List all experts available for a tenant.

    Returns:
    - Tenant-specific experts (trained on tenant data)
    - Generic experts (fallback for all tenants)
    """
    try:
        men_system = get_men_system()

        if not men_system.tenant_manager:
            raise HTTPException(
                status_code=503,
                detail="Expert management is disabled"
            )

        tenant_experts = men_system.tenant_manager.get_tenant_experts(tenant_id)
        generic_experts = men_system.tenant_manager.get_generic_experts()

        return TenantExpertsResponse(
            tenant_id=tenant_id,
            experts=[
                ExpertInfo(
                    domain=e.domain,
                    tenant_id=e.tenant_id,
                    path=e.path,
                    is_generic=e.is_generic,
                    document_types=e.document_types
                ) for e in tenant_experts
            ],
            generic_experts=[
                ExpertInfo(
                    domain=e.domain,
                    tenant_id=e.tenant_id,
                    path=e.path,
                    is_generic=e.is_generic,
                    document_types=e.document_types
                ) for e in generic_experts
            ]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list experts: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list experts: {str(e)}"
        )


@router.post("/{tenant_id}/experts/register", response_model=RegisterExpertResponse)
async def register_expert(
    tenant_id: str,
    request: RegisterExpertRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Register a new expert for a tenant.

    Use this after manually training a LoRA adapter
    to make it available for the tenant.

    The path should point to a directory containing
    the LoRA adapter files (adapter_config.json, etc.).
    """
    try:
        men_system = get_men_system()

        if not men_system.tenant_manager:
            raise HTTPException(
                status_code=503,
                detail="Expert management is disabled"
            )

        expert = men_system.tenant_manager.register_expert(
            tenant_id=tenant_id,
            domain=request.domain,
            path=request.path,
            document_types=request.document_types
        )

        return RegisterExpertResponse(
            message=f"Expert '{request.domain}' registered for tenant '{tenant_id}'",
            expert=ExpertInfo(
                domain=expert.domain,
                tenant_id=expert.tenant_id,
                path=expert.path,
                is_generic=expert.is_generic,
                document_types=expert.document_types
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register expert: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register expert: {str(e)}"
        )


@router.post("/{tenant_id}/experts/train", response_model=TrainingResponse)
async def train_expert(
    tenant_id: str,
    request: TrainingRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key)
):
    """
    Start training a new expert for a tenant.

    Training options:
    - Provide training_data: Custom examples [{input, output}, ...]
    - Set use_synthetic=True: Generate synthetic examples for the domain

    Training runs in the background. Use the status endpoint
    to check progress.

    Note: Training requires GPU and may take several minutes
    depending on data size and num_epochs.
    """
    try:
        men_system = get_men_system()

        if not men_system.tenant_manager:
            raise HTTPException(
                status_code=503,
                detail="Expert management is disabled"
            )

        # Import training module
        from ..services.training import train_expert_async

        # Start training in background
        background_tasks.add_task(
            train_expert_async,
            tenant_id=tenant_id,
            domain=request.domain,
            training_data=request.training_data,
            use_synthetic=request.use_synthetic,
            num_epochs=request.num_epochs
        )

        return TrainingResponse(
            status="started",
            tenant_id=tenant_id,
            domain=request.domain,
            expert_path=None,
            message=f"Training started for domain '{request.domain}'. Check status endpoint for progress."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start training: {str(e)}"
        )


@router.get("/domains")
async def list_all_domains(_: bool = Depends(verify_api_key)):
    """
    List all available domains across all experts.

    Returns unique domain names that have at least one
    expert (generic or tenant-specific).
    """
    try:
        men_system = get_men_system()

        if not men_system.tenant_manager:
            return {"domains": men_system.config.domains}

        domains = men_system.tenant_manager.get_all_domains()

        return {
            "domains": domains,
            "supported_domains": men_system.config.domains
        }

    except Exception as e:
        logger.error(f"Failed to list domains: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list domains: {str(e)}"
        )
