"""Workflow Templates Management API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from app.core.config import settings
import httpx

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


# Pydantic Models
class WorkflowTemplateCreate(BaseModel):
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    workflow_definition: Dict[str, Any] = Field(..., description="Workflow definition")
    tenant_id: str = Field(..., description="Tenant ID")
    is_active: bool = Field(True, description="Whether template is active")


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    workflow_definition: Dict[str, Any]
    tenant_id: str
    is_active: bool
    created_at: str
    updated_at: str


@router.get("/", response_model=List[WorkflowTemplateResponse])
async def get_workflow_templates(tenant_id: Optional[str] = None):
    """Get workflow templates, preferring Core DB, with AI static fallback"""
    try:
        response_templates: List[Dict[str, Any]] = []

        # Try Core first (service-to-service, if allowed)
        core_url = f"{settings.api_core_url}/api/v1/workflow-templates?limit=100"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
                resp = await client.get(core_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    for tpl in data:
                        response_templates.append({
                            "id": tpl.get("id"),
                            "name": tpl.get("name"),
                            "description": tpl.get("description"),
                            "workflow_definition": tpl.get("workflow_definition", {}),
                            "tenant_id": tpl.get("tenant_id", tenant_id or "default"),
                            "is_active": tpl.get("status", "draft") != "deprecated",
                            "created_at": tpl.get("created_at", datetime.now().isoformat()),
                            "updated_at": tpl.get("updated_at", datetime.now().isoformat()),
                        })
                    logger.info(f"Loaded {len(response_templates)} templates from Core")
                else:
                    logger.info(f"Core template list unavailable ({resp.status_code}); falling back to local AI templates")
        except Exception as core_err:
            logger.info(f"Core template list fetch failed: {core_err}; using local AI templates")

        # Always include AI-enhanced templates as fallback/supplement
        from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
        ai_templates = get_all_ai_enhanced_templates()
        for template in ai_templates:
            response_templates.append({
                "id": template["id"],
                "name": template["name"],
                "description": template["description"],
                "workflow_definition": template["workflow_definition"],
                "tenant_id": template.get("tenant_id", tenant_id or "default"),
                "is_active": True,
                "created_at": template.get("created_at", datetime.now().isoformat()),
                "updated_at": template.get("updated_at", datetime.now().isoformat())
            })

        # Include legacy example template
        response_templates.append({
            "id": "legal-advisory-template",
            "name": "Asesoría Legal (Legacy)",
            "description": "Template legacy para consultas de asesoría legal",
            "workflow_definition": {
                "start_step": "intake",
                "steps": [
                    {
                        "step_id": "intake",
                        "step_name": "Recopilación de Información",
                        "step_type": "activity",
                        "activity_type": "emma_ai_legal_analysis",
                        "activity_config": {
                            "case_type": "{{user_input_data.case_type}}",
                            "client_name": "{{user_input_data.client_name}}",
                            "description": "{{user_input_data.description}}"
                        },
                        "next_steps": {"success": "end"}
                    }
                ]
            },
            "tenant_id": tenant_id or "default",
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })

        logger.info(f"Returning {len(response_templates)} workflow templates (Core+AI)")
        return response_templates

    except Exception as e:
        logger.error(f"Error getting workflow templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow templates: {str(e)}")


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(template_id: str):
    """Get specific workflow template, preferring Core, with AI/legacy fallback"""
    try:
        # Try Core
        core_url = f"{settings.api_core_url}/api/v1/workflow-templates/{template_id}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
                resp = await client.get(core_url, headers=headers)
                if resp.status_code == 200:
                    tpl = resp.json()
                    return {
                        "id": tpl.get("id", template_id),
                        "name": tpl.get("name", template_id),
                        "description": tpl.get("description"),
                        "workflow_definition": tpl.get("workflow_definition", {}),
                        "tenant_id": tpl.get("tenant_id", "default"),
                        "is_active": tpl.get("status", "draft") != "deprecated",
                        "created_at": tpl.get("created_at", datetime.now().isoformat()),
                        "updated_at": tpl.get("updated_at", datetime.now().isoformat()),
                    }
        except Exception as core_err:
            logger.info(f"Core template fetch failed: {core_err}; trying local AI templates")

        # Try local AI templates
        from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
        ai_templates = get_all_ai_enhanced_templates()
        for template in ai_templates:
            if template["id"] == template_id:
                return {
                    "id": template["id"],
                    "name": template["name"],
                    "description": template["description"],
                    "workflow_definition": template["workflow_definition"],
                    "tenant_id": template.get("tenant_id", "default"),
                    "is_active": True,
                    "created_at": template.get("created_at", datetime.now().isoformat()),
                    "updated_at": template.get("updated_at", datetime.now().isoformat()),
                }

        # Legacy fallback
        if template_id == "legal-advisory-template":
            return {
                "id": "legal-advisory-template",
                "name": "Asesoría Legal (Legacy)",
                "description": "Template legacy para consultas de asesoría legal",
                "workflow_definition": {
                    "start_step": "intake",
                    "steps": [
                        {
                            "step_id": "intake",
                            "step_name": "Recopilación de Información",
                            "step_type": "activity",
                            "activity_type": "emma_ai_legal_analysis",
                            "activity_config": {
                                "case_type": "{{user_input_data.case_type}}",
                                "client_name": "{{user_input_data.client_name}}",
                                "description": "{{user_input_data.description}}"
                            },
                            "next_steps": {"success": "end"}
                        }
                    ]
                },
                "tenant_id": "default",
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

        raise HTTPException(status_code=404, detail="Template not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow template: {str(e)}")


@router.post("/", response_model=WorkflowTemplateResponse)
async def create_workflow_template(template: WorkflowTemplateCreate):
    """Create a new workflow template"""
    try:
        # TODO: Implement actual database creation
        template_id = f"template-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            "id": template_id,
            "name": template.name,
            "description": template.description,
            "workflow_definition": template.workflow_definition,
            "tenant_id": template.tenant_id,
            "is_active": template.is_active,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error creating workflow template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create workflow template: {str(e)}")


@router.put("/{template_id}", response_model=WorkflowTemplateResponse)
async def update_workflow_template(template_id: str, template: WorkflowTemplateCreate):
    """Update an existing workflow template"""
    try:
        # TODO: Implement actual database update
        return {
            "id": template_id,
            "name": template.name,
            "description": template.description,
            "workflow_definition": template.workflow_definition,
            "tenant_id": template.tenant_id,
            "is_active": template.is_active,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating workflow template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update workflow template: {str(e)}")


@router.delete("/{template_id}")
async def delete_workflow_template(template_id: str):
    """Delete a workflow template"""
    try:
        # TODO: Implement actual database deletion
        return {"message": f"Template {template_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting workflow template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete workflow template: {str(e)}")
