"""
Engine Templates API - Admin management of configurable workflow templates
"""
import asyncio
import base64
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator, validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, require_admin_role
from app.db.models import Document
from app.db.workflow_template_models import WorkflowTemplate, WorkflowTemplateField
from app.schemas.user import User
from app.services.template_editor_client import TemplateEditorClient
from app.services.template_storage_service import (
    TemplateStorageService,
    ODT_MIME_TYPE,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["engine-templates"])


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
    
    # Template file handling (ODT)
    template_file_name: Optional[str] = Field(None, description="Filename of the uploaded template (.odt)")
    template_file_base64: Optional[str] = Field(None, description="Base64-encoded ODT file contents")
    template_file_mime: Optional[str] = Field(None, description="MIME type for the template payload")
    source_document_id: Optional[str] = Field(
        None, description="Existing document ID (ODT) to copy as template"
    )
    
    @validator('workflow_steps')
    def validate_workflow_steps(cls, v):
        if not v:
            raise ValueError("At least one workflow step is required")
        
        step_ids = [step.step_id for step in v]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Step IDs must be unique")
        
        return v
    
    @model_validator(mode="after")
    def validate_template_sources(cls, values):
        file_b64 = values.template_file_base64
        file_name = values.template_file_name
        source_doc = values.source_document_id
        
        if file_b64 and source_doc:
            raise ValueError("Provide either template_file_base64 or source_document_id, not both")
        
        if file_b64 and not file_name:
            raise ValueError("template_file_name is required when uploading a template file")
        
        if file_b64 and not values.template_file_mime:
            values.template_file_mime = ODT_MIME_TYPE
        
        if source_doc and not isinstance(source_doc, str):
            raise ValueError("source_document_id must be a string")
        
        return values


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
    
    # Optional template file updates
    template_file_name: Optional[str] = Field(None, description="Filename of the uploaded template (.odt)")
    template_file_base64: Optional[str] = Field(None, description="Base64-encoded ODT file contents")
    template_file_mime: Optional[str] = Field(None, description="MIME type for the template payload")
    source_document_id: Optional[str] = Field(
        None, description="Existing document ID (ODT) to copy as template"
    )
    
    @model_validator(mode="after")
    def validate_template_sources(cls, values):
        file_b64 = values.template_file_base64
        file_name = values.template_file_name
        source_doc = values.source_document_id
        
        if file_b64 and source_doc:
            raise ValueError("Provide either template_file_base64 or source_document_id, not both")
        
        if file_b64 and not file_name:
            raise ValueError("template_file_name is required when uploading a template file")
        
        if file_b64 and not values.template_file_mime:
            values.template_file_mime = ODT_MIME_TYPE
        
        return values


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
    
    # Template file metadata
    template_file_path: Optional[str] = None
    template_file_name: Optional[str] = None
    template_file_mime: Optional[str] = None
    template_file_size: Optional[int] = None
    template_file_updated_at: Optional[datetime] = None
    template_source_document_id: Optional[str] = None
    
    class Config:
        from_attributes = True


class TemplateEditSessionStartRequest(BaseModel):
    """Optional metadata for audit when opening template in Google Docs."""
    reason: Optional[str] = Field(None, description="Reason for editing the template")


class TemplateEditSessionStartResponse(BaseModel):
    """Proxy response for template edit sessions."""
    id: str
    template_id: str
    template_name: str
    google_doc_id: str
    google_doc_url: str
    google_doc_edit_url: str
    expires_at: datetime
    status: str

    class Config:
        extra = "allow"


class TemplateEditSessionFinishRequest(BaseModel):
    force_sync: bool = Field(False, description="Force storing the result even if no diff detected")


class TemplateEditSessionFinishResponse(BaseModel):
    session_id: str
    status: str
    changes_detected: bool
    cleanup_success: bool
    completed_at: datetime
    sync_result: Optional[Dict[str, Any]] = None
    updated_file: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


class DocumentToTemplateRequest(BaseModel):
    """Request payload to bootstrap a template from an existing document."""
    document_id: str = Field(..., description="Document ID (must be an ODT file)")
    name: Optional[str] = Field(None, description="Optional template name override")
    description: Optional[str] = Field(None, description="Optional template description override")
    category: Optional[str] = Field(None, description="Optional category override")
    tags: Optional[List[str]] = Field(None, description="Optional tags override")


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
        
        # Handle optional template file storage
        template_file_result = None
        if template_data.template_file_base64 or template_data.source_document_id:
            storage_service = TemplateStorageService(
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id),
                db_session=db
            )

            if template_data.template_file_base64:
                template_file_result = storage_service.save_base64_file(
                    template_id=str(template.id),
                    original_name=template_data.template_file_name,
                    file_base64=template_data.template_file_base64,
                    mime_type=template_data.template_file_mime or ODT_MIME_TYPE
                )
            elif template_data.source_document_id:
                source_document = _get_tenant_document(
                    db=db,
                    tenant_id=current_user.tenant_id,
                    document_id=template_data.source_document_id
                )
                template_file_result = storage_service.copy_from_document(
                    template_id=str(template.id),
                    document=source_document
                )
        if template_file_result:
            _apply_template_file_result(template, template_file_result)
            db.commit()
            db.refresh(template)
        
        logger.info(
            "Created workflow template %s with %d fields",
            template.id,
            len(template_data.input_fields),
        )
        
        return _build_template_response(template)
        
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
        
        return [_build_template_response(template) for template in templates]
        
    except Exception as e:
        logger.error("Error listing workflow templates", exc_info=e)
        raise HTTPException(
            status_code=500,
            detail="Failed to list workflow templates"
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
        
        return _build_template_response(template)
        
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
        
        # Handle optional template file updates
        template_file_result = None
        if template_data.template_file_base64 or template_data.source_document_id:
            storage_service = TemplateStorageService(
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id),
                db_session=db
            )
            if template_data.template_file_base64:
                template_file_result = await asyncio.to_thread(
                    storage_service.save_base64_file,
                    str(template.id),
                    template_data.template_file_name,
                    template_data.template_file_base64,
                    template_data.template_file_mime or ODT_MIME_TYPE
                )
            elif template_data.source_document_id:
                source_document = _get_tenant_document(
                    db=db,
                    tenant_id=current_user.tenant_id,
                    document_id=template_data.source_document_id
                )
                template_file_result = await asyncio.to_thread(
                    storage_service.copy_from_document,
                    str(template.id),
                    source_document
                )
        
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        
        if template_file_result:
            _apply_template_file_result(template, template_file_result)
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"Updated workflow template {template_id}")
        
        return _build_template_response(template)
        
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
        
        # Cleanup template file in storage (best effort)
        storage_service = TemplateStorageService(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            db_session=db
        )
        storage_service.delete_template_file(template.template_file_path)
        
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


@router.post("/from-document", response_model=WorkflowTemplateResponse)
async def create_template_from_document(
    payload: DocumentToTemplateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role)
):
    """Bootstrap a workflow template using an existing tenant document (ODT)."""
    document = _get_tenant_document(
        db=db,
        tenant_id=current_user.tenant_id,
        document_id=payload.document_id,
    )

    template_name = payload.name or document.title or document.filename
    template_description = payload.description or document.description or f"Plantilla basada en {document.filename}"
    template_category = payload.category or document.category or "operations"
    template_tags: List[str] = []

    if payload.tags is not None:
        template_tags = payload.tags
    elif document.tags_array:
        template_tags = document.tags_array
    else:
        try:
            template_tags = [tag.name for tag in (document.tags or []) if getattr(tag, "name", None)]
        except Exception:
            template_tags = []

    default_step = {
        "step_id": "prepare_document",
        "step_name": "Preparar documento",
        "step_type": "manual",
        "description": "Personaliza la plantilla en Google Docs antes de publicarla.",
        "instructions": "Abre la plantilla en Google Docs desde NexusDocs y aplica tus cambios.",
        "next_steps": {},
    }

    workflow_definition = {
        "version": "1.0",
        "steps": [default_step],
        "start_step": default_step["step_id"],
    }

    template = WorkflowTemplate(
        tenant_id=str(current_user.tenant_id),
        name=template_name,
        description=template_description,
        category=template_category,
        version="1.0.0",
        status="draft",
        workflow_definition=workflow_definition,
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
        validation_rules={},
        notification_config={},
        estimated_duration=document.document_metadata.get("estimated_duration")
        if isinstance(document.document_metadata, dict)
        else None,
        complexity_level="intermediate",
        tags=template_tags,
        is_public=False,
        allowed_roles=[],
        created_by=current_user.id,
    )

    db.add(template)
    try:
        db.flush()
        storage_service = TemplateStorageService(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            db_session=db,
        )
        file_result = storage_service.copy_from_document(
            template_id=str(template.id),
            document=document,
        )
        _apply_template_file_result(template, file_result)
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)
        logger.info(
            "Template %s created from document %s for tenant %s",
            template.id,
            document.id,
            current_user.tenant_id,
        )
        return _build_template_response(template)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error(
            "Error creating template from document %s: %s", payload.document_id, exc
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to convert document into template",
        ) from exc


@router.post("/{template_id}/edit-sessions", response_model=TemplateEditSessionStartResponse)
async def start_template_edit_session(
    template_id: str,
    _request: TemplateEditSessionStartRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a Google Docs editing session for a template."""
    template = _get_template_for_tenant(db, template_id, current_user.tenant_id)
    user_email = _require_user_email(current_user)
    if _request and _request.reason:
        logger.info(
            "User %s requested template edit for %s (%s)",
            current_user.id,
            template_id,
            _request.reason
        )

    template_file_base64: Optional[str] = None
    template_file_name = template.template_file_name or f"{template.name}.odt"
    template_file_mime = template.template_file_mime or ODT_MIME_TYPE

    if template.template_file_path:
        storage_service = TemplateStorageService(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            db_session=db
        )
        template_bytes = await asyncio.to_thread(
            storage_service.download_template_file,
            template.template_file_path
        )
        template_file_base64 = base64.b64encode(template_bytes).decode("utf-8")
    else:
        logger.info(
            "Template %s has no stored ODT file. Creating blank Google Doc for editing.",
            template_id,
        )

    payload = {
        "template_id": str(template.id),
        "template_name": template.name,
        "template_file_base64": template_file_base64,
        "template_file_name": template_file_name,
        "template_file_mime": template_file_mime,
        "user_id": str(current_user.id),
        "user_email": user_email,
        "tenant_id": str(current_user.tenant_id),
    }
    editor_client = TemplateEditorClient()
    session = await editor_client.create_edit_session(payload)
    return TemplateEditSessionStartResponse(**session)


@router.post(
    "/{template_id}/edit-sessions/{session_id}/finish",
    response_model=TemplateEditSessionFinishResponse
)
async def finish_template_edit_session(
    template_id: str,
    session_id: str,
    finish_request: TemplateEditSessionFinishRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Finalize a Google Docs session and persist the updated ODT file."""
    template = _get_template_for_tenant(db, template_id, current_user.tenant_id)
    editor_client = TemplateEditorClient()
    result = await editor_client.finish_edit_session(
        session_id=session_id,
        user_id=str(current_user.id),
        force_sync=finish_request.force_sync
    )

    updated_file = result.get("updated_file")
    if updated_file and updated_file.get("base64"):
        storage_service = TemplateStorageService(
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            db_session=db
        )
        template_file_result = await asyncio.to_thread(
            storage_service.save_base64_file,
            str(template.id),
            updated_file.get("file_name") or template.template_file_name or f"{template.name}.odt",
            updated_file["base64"],
            updated_file.get("mime_type") or template.template_file_mime or ODT_MIME_TYPE,
        )
        _apply_template_file_result(template, template_file_result)
        template.updated_by = current_user.id
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)

    sanitized_updated_file = None
    if updated_file:
        sanitized_updated_file = {
            "file_name": updated_file.get("file_name"),
            "mime_type": updated_file.get("mime_type"),
            "size": updated_file.get("size"),
            "content_hash": updated_file.get("content_hash"),
        }
    response_payload = dict(result)
    response_payload["updated_file"] = sanitized_updated_file
    return TemplateEditSessionFinishResponse(**response_payload)


def _get_template_for_tenant(
    db: Session, template_id: str, tenant_id: uuid.UUID
) -> WorkflowTemplate:
    """Fetch template ensuring it belongs to the tenant."""
    try:
        template_uuid = uuid.UUID(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid template ID format") from exc
    
    template = (
        db.query(WorkflowTemplate)
        .filter(
            WorkflowTemplate.id == template_uuid,
            WorkflowTemplate.tenant_id == str(tenant_id),
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return template


def _require_user_email(user: User) -> str:
    if not user.email:
        raise HTTPException(
            status_code=400,
            detail="User email is required to request Google Docs editing access",
        )
    return user.email


def _build_template_response(template: WorkflowTemplate) -> WorkflowTemplateResponse:
    """Helper to keep API responses consistent."""
    return WorkflowTemplateResponse(
        id=str(template.id),
        tenant_id=str(template.tenant_id),
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
        created_by=str(template.created_by),
        created_at=template.created_at,
        updated_at=template.updated_at,
        workflow_definition=template.workflow_definition,
        input_schema=template.input_schema,
        template_file_path=template.template_file_path,
        template_file_name=template.template_file_name,
        template_file_mime=template.template_file_mime,
        template_file_size=template.template_file_size,
        template_file_updated_at=template.template_file_updated_at,
        template_source_document_id=str(template.template_source_document_id)
        if template.template_source_document_id
        else None,
    )


def _apply_template_file_result(
    template: WorkflowTemplate, file_result: Dict[str, Any]
) -> None:
    """Persist metadata from storage upload into the template model."""
    template.template_file_path = file_result["path"]
    template.template_file_name = file_result["original_name"]
    template.template_file_mime = file_result["mime_type"]
    template.template_file_size = file_result["size"]
    template.template_file_updated_at = file_result["updated_at"]
    source_document_id = file_result.get("source_document_id")
    template.template_source_document_id = (
        uuid.UUID(source_document_id) if source_document_id else None
    )


def _get_tenant_document(db: Session, tenant_id, document_id: str) -> Document:
    """Fetch a document ensuring it belongs to the tenant."""
    try:
        document_uuid = uuid.UUID(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid source_document_id") from exc
    
    document = (
        db.query(Document)
        .filter(Document.id == document_uuid, Document.tenant_id == tenant_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Source document not found")
    
    return document


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
