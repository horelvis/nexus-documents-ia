"""Workflow Templates Management API"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from app.core.config import settings

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
    """Get all workflow templates for a tenant"""
    try:
        # Import AI-enhanced templates
        from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
        
        # Get AI-enhanced templates
        ai_templates = get_all_ai_enhanced_templates()
        
        # Convert to response format
        response_templates = []
        
        for template in ai_templates:
            response_templates.append({
                "id": template["id"],
                "name": template["name"],
                "description": template["description"],
                "workflow_definition": template["workflow_definition"],
                "tenant_id": template["tenant_id"],
                "is_active": True,
                "created_at": template.get("created_at", datetime.now().isoformat()),
                "updated_at": template.get("updated_at", datetime.now().isoformat())
            })
        
        # Also include legacy template for backward compatibility
        legacy_template = {
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
                        "next_steps": {
                            "success": "end"
                        }
                    }
                ]
            },
            "tenant_id": tenant_id or "default",
            "is_active": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        response_templates.append(legacy_template)
        
        logger.info(f"Returning {len(response_templates)} workflow templates (including {len(ai_templates)} AI-enhanced)")
        return response_templates
        
    except Exception as e:
        logger.error(f"Error getting workflow templates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow templates: {str(e)}")


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(template_id: str):
    """Get a specific workflow template"""
    try:
        # Import AI-enhanced templates
        from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
        
        # Get all available templates
        ai_templates = get_all_ai_enhanced_templates()
        
        # Search for the requested template
        for template in ai_templates:
            if template["id"] == template_id:
                return {
                    "id": template["id"],
                    "name": template["name"],
                    "description": template["description"],
                    "workflow_definition": template["workflow_definition"],
                    "tenant_id": template["tenant_id"],
                    "is_active": True,
                    "created_at": template.get("created_at", datetime.now().isoformat()),
                    "updated_at": template.get("updated_at", datetime.now().isoformat())
                }
        
        # Handle legacy template
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
                            "next_steps": {
                                "success": "end"
                            }
                        }
                    ]
                },
                "tenant_id": "default",
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        else:
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