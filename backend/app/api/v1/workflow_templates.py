"""
Workflow Templates API - Admin management of configurable workflow templates
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import uuid

from sqlalchemy.orm import Session
from app.api.dependencies import get_db, get_current_user, require_admin_role
from app.db.models.workflow_template import WorkflowTemplate, WorkflowTemplateField
from app.schemas.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow-templates", tags=["Workflow Templates"])


# Pydantic Models
class WorkflowStepDefinition(BaseModel):
    step_id: str = Field(..., description="Unique step identifier")
    step_name: str = Field(..., description="Human readable step name")
    step_type: str = Field(..., description="Type: activity, decision, manual, approval")
    description: Optional[str] = None
    estimated_duration: Optional[str] = None  # "30 minutes", "2 hours"
    
    # Activity configuration
    activity_type: Optional[str] = None  # "emma_ai_analysis", "document_generation", "notification"
    activity_config: Dict[str, Any] = Field(default_factory=dict)
    
    # Decision logic
    decision_conditions: Dict[str, Any] = Field(default_factory=dict)
    
    # Manual step configuration
    assignee_role: Optional[str] = None  # "hr_manager", "legal_team"
    instructions: Optional[str] = None
    
    # Flow control
    next_steps: Dict[str, str] = Field(default_factory=dict)  # {"success": "step_2", "failure": "step_error"}


class WorkflowTemplateFieldCreate(BaseModel):
    field_name: str = Field(..., description="Internal field name")
    field_label: str = Field(..., description="Display label")
    field_type: str = Field(..., description="text, select, date, file, number, boolean")
    is_required: bool = Field(default=False)
    field_order: int = Field(default=0)
    field_group: Optional[str] = None
    placeholder_text: Optional[str] = None
    help_text: Optional[str] = None
    field_options: List[Dict[str, Any]] = Field(default_factory=list)
    default_value: Optional[str] = None
    validation_rules: Dict[str, Any] = Field(default_factory=dict)
    show_conditions: Dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateCreate(BaseModel):
    name: str = Field(..., description="Template name")
    description: Optional[str] = None
    category: str = Field(..., description="hr, legal, finance, operations")
    estimated_duration: Optional[str] = None
    complexity_level: str = Field(default="intermediate")
    tags: List[str] = Field(default_factory=list)
    
    # Workflow Definition
    workflow_steps: List[WorkflowStepDefinition] = Field(..., description="Workflow steps")
    input_fields: List[WorkflowTemplateFieldCreate] = Field(..., description="Input fields")
    
    # Configuration
    validation_rules: Dict[str, Any] = Field(default_factory=dict)
    notification_config: Dict[str, Any] = Field(default_factory=dict)
    allowed_roles: List[str] = Field(default_factory=list)
    is_public: bool = Field(default=False)
    
    @validator('workflow_steps')
    def validate_workflow_steps(cls, v):
        if not v:
            raise ValueError("At least one workflow step is required")
        
        step_ids = [step.step_id for step in v]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")
        
        return v


class WorkflowTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    estimated_duration: Optional[str] = None
    complexity_level: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None  # "draft", "active", "deprecated"
    
    workflow_steps: Optional[List[WorkflowStepDefinition]] = None
    input_fields: Optional[List[WorkflowTemplateFieldCreate]] = None
    validation_rules: Optional[Dict[str, Any]] = None
    notification_config: Optional[Dict[str, Any]] = None
    allowed_roles: Optional[List[str]] = None


class WorkflowTemplateResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    category: str
    version: str
    status: str
    estimated_duration: Optional[str]
    complexity_level: str
    tags: List[str]
    usage_count: int
    success_rate: int
    is_public: bool
    allowed_roles: List[str]
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]
    
    # Workflow configuration
    workflow_definition: Dict[str, Any]
    input_schema: Dict[str, Any]
    
    class Config:
        from_attributes = True


@router.post("/", response_model=WorkflowTemplateResponse)
async def create_workflow_template(
    template_data: WorkflowTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role)
):
    """Create new workflow template (Admin only)"""
    
    try:
        logger.info(f"Admin {current_user.id} creating workflow template: {template_data.name}")
        
        # Validate workflow definition
        workflow_definition = {
            "version": "1.0",
            "steps": [step.dict() for step in template_data.workflow_steps],
            "start_step": template_data.workflow_steps[0].step_id if template_data.workflow_steps else None
        }
        
        # Create input schema from fields
        input_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for field in template_data.input_fields:
            field_schema = {
                "type": _map_field_type_to_json_schema(field.field_type),
                "title": field.field_label,
                "description": field.help_text or ""
            }
            
            if field.field_options:
                field_schema["enum"] = [opt["value"] for opt in field.field_options]
            
            if field.validation_rules:
                field_schema.update(field.validation_rules)
            
            input_schema["properties"][field.field_name] = field_schema
            
            if field.is_required:
                input_schema["required"].append(field.field_name)
        
        # Create template
        template = WorkflowTemplate(
            tenant_id=current_user.tenant_id,
            name=template_data.name,
            description=template_data.description,
            category=template_data.category,
            version="1.0.0",
            status="draft",
            workflow_definition=workflow_definition,
            input_schema=input_schema,
            validation_rules=template_data.validation_rules,
            notification_config=template_data.notification_config,
            estimated_duration=template_data.estimated_duration,
            complexity_level=template_data.complexity_level,
            tags=template_data.tags,
            is_public=template_data.is_public,
            allowed_roles=template_data.allowed_roles,
            created_by=current_user.id
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        # Create template fields
        for field_data in template_data.input_fields:
            field = WorkflowTemplateField(
                template_id=template.id,
                **field_data.dict()
            )
            db.add(field)
        
        db.commit()
        
        logger.info(f"Created workflow template {template.id} with {len(template_data.input_fields)} fields")
        
        return WorkflowTemplateResponse(
            id=str(template.id),
            tenant_id=template.tenant_id,
            name=template.name,
            description=template.description,
            category=template.category,
            version=template.version,
            status=template.status,
            estimated_duration=template.estimated_duration,
            complexity_level=template.complexity_level,
            tags=template.tags,
            usage_count=template.usage_count,
            success_rate=template.success_rate,
            is_public=template.is_public,
            allowed_roles=template.allowed_roles,
            created_by=template.created_by,
            created_at=template.created_at,
            updated_at=template.updated_at,
            workflow_definition=template.workflow_definition,
            input_schema=template.input_schema
        )
        
    except Exception as e:
        logger.error(f"Error creating workflow template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create workflow template: {str(e)}"
        )


@router.get("/", response_model=List[WorkflowTemplateResponse])
async def list_workflow_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status"),
    is_public: Optional[bool] = Query(None, description="Filter public templates"),
    limit: int = Query(50, description="Max results"),
    offset: int = Query(0, description="Results offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List workflow templates for current tenant"""
    
    try:
        query = db.query(WorkflowTemplate)
        
        # Multi-tenant filter
        if not current_user.is_admin or not is_public:
            query = query.filter(WorkflowTemplate.tenant_id == current_user.tenant_id)
        
        # Apply filters
        if category:
            query = query.filter(WorkflowTemplate.category == category)
        
        if status:
            query = query.filter(WorkflowTemplate.status == status)
        
        if is_public is not None:
            query = query.filter(WorkflowTemplate.is_public == is_public)
        
        # Get results
        templates = query.offset(offset).limit(limit).all()
        
        return [
            WorkflowTemplateResponse(
                id=str(template.id),
                tenant_id=template.tenant_id,
                name=template.name,
                description=template.description,
                category=template.category,
                version=template.version,
                status=template.status,
                estimated_duration=template.estimated_duration,
                complexity_level=template.complexity_level,
                tags=template.tags,
                usage_count=template.usage_count,
                success_rate=template.success_rate,
                is_public=template.is_public,
                allowed_roles=template.allowed_roles,
                created_by=template.created_by,
                created_at=template.created_at,
                updated_at=template.updated_at,
                workflow_definition=template.workflow_definition,
                input_schema=template.input_schema
            )
            for template in templates
        ]
        
    except Exception as e:
        logger.error(f"Error listing workflow templates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list workflow templates: {str(e)}"
        )


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific workflow template"""
    
    try:
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == uuid.UUID(template_id)
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Check access permissions
        if template.tenant_id != current_user.tenant_id and not template.is_public:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return WorkflowTemplateResponse(
            id=str(template.id),
            tenant_id=template.tenant_id,
            name=template.name,
            description=template.description,
            category=template.category,
            version=template.version,
            status=template.status,
            estimated_duration=template.estimated_duration,
            complexity_level=template.complexity_level,
            tags=template.tags,
            usage_count=template.usage_count,
            success_rate=template.success_rate,
            is_public=template.is_public,
            allowed_roles=template.allowed_roles,
            created_by=template.created_by,
            created_at=template.created_at,
            updated_at=template.updated_at,
            workflow_definition=template.workflow_definition,
            input_schema=template.input_schema
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID format")
    except Exception as e:
        logger.error(f"Error getting workflow template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow template: {str(e)}"
        )


@router.put("/{template_id}", response_model=WorkflowTemplateResponse)
async def update_workflow_template(
    template_id: str,
    template_data: WorkflowTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role)
):
    """Update workflow template (Admin only)"""
    
    try:
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == uuid.UUID(template_id),
            WorkflowTemplate.tenant_id == current_user.tenant_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Update fields
        for field, value in template_data.dict(exclude_unset=True).items():
            if field in ["workflow_steps", "input_fields"]:
                continue  # Handle separately
            setattr(template, field, value)
        
        # Update workflow definition if provided
        if template_data.workflow_steps:
            workflow_definition = {
                "version": "1.1",
                "steps": [step.dict() for step in template_data.workflow_steps],
                "start_step": template_data.workflow_steps[0].step_id
            }
            template.workflow_definition = workflow_definition
        
        # Update input schema if provided
        if template_data.input_fields:
            input_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            # Delete existing fields
            db.query(WorkflowTemplateField).filter(
                WorkflowTemplateField.template_id == template.id
            ).delete()
            
            # Create new fields
            for field_data in template_data.input_fields:
                field = WorkflowTemplateField(
                    template_id=template.id,
                    **field_data.dict()
                )
                db.add(field)
                
                # Update schema
                field_schema = {
                    "type": _map_field_type_to_json_schema(field_data.field_type),
                    "title": field_data.field_label
                }
                input_schema["properties"][field_data.field_name] = field_schema
                
                if field_data.is_required:
                    input_schema["required"].append(field_data.field_name)
            
            template.input_schema = input_schema
        
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"Updated workflow template {template_id}")
        
        return WorkflowTemplateResponse(
            id=str(template.id),
            tenant_id=template.tenant_id,
            name=template.name,
            description=template.description,
            category=template.category,
            version=template.version,
            status=template.status,
            estimated_duration=template.estimated_duration,
            complexity_level=template.complexity_level,
            tags=template.tags,
            usage_count=template.usage_count,
            success_rate=template.success_rate,
            is_public=template.is_public,
            allowed_roles=template.allowed_roles,
            created_by=template.created_by,
            created_at=template.created_at,
            updated_at=template.updated_at,
            workflow_definition=template.workflow_definition,
            input_schema=template.input_schema
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID format")
    except Exception as e:
        logger.error(f"Error updating workflow template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update workflow template: {str(e)}"
        )


@router.delete("/{template_id}")
async def delete_workflow_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role)
):
    """Delete workflow template (Admin only)"""
    
    try:
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == uuid.UUID(template_id),
            WorkflowTemplate.tenant_id == current_user.tenant_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Check if template has active executions
        # In production, you might want to prevent deletion of templates with active executions
        
        # Delete template fields first
        db.query(WorkflowTemplateField).filter(
            WorkflowTemplateField.template_id == template.id
        ).delete()
        
        # Delete template
        db.delete(template)
        db.commit()
        
        logger.info(f"Deleted workflow template {template_id}")
        
        return {"message": "Workflow template deleted successfully"}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID format")
    except Exception as e:
        logger.error(f"Error deleting workflow template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete workflow template: {str(e)}"
        )


@router.post("/{template_id}/activate")
async def activate_workflow_template(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role)
):
    """Activate workflow template for use"""
    
    try:
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == uuid.UUID(template_id),
            WorkflowTemplate.tenant_id == current_user.tenant_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        template.status = "active"
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {"message": "Workflow template activated successfully"}
        
    except Exception as e:
        logger.error(f"Error activating workflow template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to activate workflow template: {str(e)}"
        )


def _map_field_type_to_json_schema(field_type: str) -> str:
    """Map UI field types to JSON Schema types"""
    mapping = {
        "text": "string",
        "select": "string",
        "date": "string",
        "file": "string",
        "number": "number",
        "boolean": "boolean",
        "email": "string",
        "phone": "string",
        "url": "string"
    }
    return mapping.get(field_type, "string")