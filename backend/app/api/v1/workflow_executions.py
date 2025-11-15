"""
Workflow Executions API - User workflow execution and management
"""
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import uuid
import httpx

from sqlalchemy.orm import Session
from app.api.dependencies import get_db, get_current_user
from app.db.workflow_template_models import (
    WorkflowTemplate,
    WorkflowExecution,
    WorkflowExecutionStep,
)
from app.schemas.user import User
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow-executions", tags=["Workflow Executions"])


# Pydantic Models
class WorkflowExecutionCreate(BaseModel):
    template_id: str = Field(..., description="Workflow template ID")
    input_data: Dict[str, Any] = Field(..., description="User input data for workflow")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")


class WorkflowExecutionResponse(BaseModel):
    id: str
    template_id: str
    template_name: str
    template_version: str
    tenant_id: str
    temporalio_workflow_id: str
    input_data: Dict[str, Any]
    current_step: Optional[str]
    status: str
    progress_percentage: int
    output_data: Optional[Dict[str, Any]]
    generated_documents: List[str]
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    estimated_completion: Optional[datetime]
    initiated_by: str
    assigned_to: Optional[str]
    
    class Config:
        from_attributes = True


class ManualTaskResponse(BaseModel):
    task_id: str
    execution_id: str
    step_id: str
    step_name: str
    instructions: str
    assignee_role: str
    status: str
    created_at: datetime
    assigned_to: Optional[str]


class ManualTaskCompletion(BaseModel):
    result: Dict[str, Any] = Field(..., description="Manual task completion result")
    notes: Optional[str] = None


async def _call_temporalio_service(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Helper to call Temporalio service"""
    
    temporalio_url = settings.TEMPORALIO_SERVICE_URL or "http://temporalio-service:8000"
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}",
                "Content-Type": "application/json"
            }
            
            if method == "POST":
                response = await client.post(
                    f"{temporalio_url}{endpoint}",
                    json=data,
                    headers=headers,
                    timeout=60.0
                )
            else:
                response = await client.get(
                    f"{temporalio_url}{endpoint}",
                    headers=headers,
                    timeout=30.0
                )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Temporalio service error: {response.text}"
                )
                
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Temporalio service unavailable"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Temporalio service timeout"
        )


@router.post("/", response_model=WorkflowExecutionResponse)
async def start_workflow_execution(
    execution_data: WorkflowExecutionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start workflow execution from template"""
    
    try:
        # Get template
        template = db.query(WorkflowTemplate).filter(
            WorkflowTemplate.id == uuid.UUID(execution_data.template_id)
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Check access permissions
        if template.tenant_id != current_user.tenant_id and not template.is_public:
            raise HTTPException(status_code=403, detail="Access denied to template")
        
        # Check role permissions
        if template.allowed_roles and current_user.role not in template.allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient role permissions")
        
        # Validate input data against template schema
        _validate_input_data(execution_data.input_data, template.input_schema)
        
        # Create execution record
        execution_id = str(uuid.uuid4())
        temporalio_workflow_id = f"dynamic_workflow_{execution_id[:8]}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        execution = WorkflowExecution(
            id=uuid.UUID(execution_id),
            tenant_id=current_user.tenant_id,
            template_id=template.id,
            template_version=template.version,
            temporalio_workflow_id=temporalio_workflow_id,
            input_data=execution_data.input_data,
            execution_context=execution_data.context,
            status="running",
            initiated_by=current_user.id
        )
        
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # Start Temporalio workflow
        workflow_input = {
            "workflow_type": "dynamic_workflow",
            "input_data": {
                "template_id": str(template.id),
                "template_name": template.name,
                "template_version": template.version,
                "tenant_id": current_user.tenant_id,
                "user_id": current_user.id,
                "execution_id": execution_id,
                "workflow_definition": template.workflow_definition,
                "user_input_data": execution_data.input_data,
                "context": execution_data.context
            },
            "workflow_id": temporalio_workflow_id
        }
        
        temporalio_result = await _call_temporalio_service(
            "/workflows/start",
            method="POST",
            data=workflow_input
        )
        
        if not temporalio_result.get("success"):
            # Update execution status
            execution.status = "failed"
            execution.error_message = "Failed to start Temporalio workflow"
            db.commit()
            
            raise HTTPException(
                status_code=500,
                detail="Failed to start workflow execution"
            )
        
        # Update template usage
        template.usage_count += 1
        db.commit()
        
        logger.info(f"Started workflow execution {execution_id} from template {template.name}")
        
        return WorkflowExecutionResponse(
            id=str(execution.id),
            template_id=str(execution.template_id),
            template_name=template.name,
            template_version=execution.template_version,
            tenant_id=execution.tenant_id,
            temporalio_workflow_id=execution.temporalio_workflow_id,
            input_data=execution.input_data,
            current_step=execution.current_step,
            status=execution.status,
            progress_percentage=execution.progress_percentage,
            output_data=execution.output_data,
            generated_documents=execution.generated_documents,
            error_message=execution.error_message,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            estimated_completion=execution.estimated_completion,
            initiated_by=execution.initiated_by,
            assigned_to=execution.assigned_to
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID format")
    except Exception as e:
        logger.error(f"Error starting workflow execution: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow execution: {str(e)}"
        )


@router.get("/", response_model=List[WorkflowExecutionResponse])
async def list_workflow_executions(
    status: Optional[str] = Query(None, description="Filter by status"),
    template_id: Optional[str] = Query(None, description="Filter by template ID"),
    limit: int = Query(50, description="Max results"),
    offset: int = Query(0, description="Results offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List workflow executions for current user/tenant"""
    
    try:
        query = db.query(WorkflowExecution, WorkflowTemplate).join(
            WorkflowTemplate, WorkflowExecution.template_id == WorkflowTemplate.id
        ).filter(
            WorkflowExecution.tenant_id == current_user.tenant_id
        )
        
        # Apply filters
        if status:
            query = query.filter(WorkflowExecution.status == status)
        
        if template_id:
            query = query.filter(WorkflowExecution.template_id == uuid.UUID(template_id))
        
        # Get results
        results = query.offset(offset).limit(limit).all()
        
        executions_response = []
        for execution, template in results:
            executions_response.append(WorkflowExecutionResponse(
                id=str(execution.id),
                template_id=str(execution.template_id),
                template_name=template.name,
                template_version=execution.template_version,
                tenant_id=execution.tenant_id,
                temporalio_workflow_id=execution.temporalio_workflow_id,
                input_data=execution.input_data,
                current_step=execution.current_step,
                status=execution.status,
                progress_percentage=execution.progress_percentage,
                output_data=execution.output_data,
                generated_documents=execution.generated_documents,
                error_message=execution.error_message,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                estimated_completion=execution.estimated_completion,
                initiated_by=execution.initiated_by,
                assigned_to=execution.assigned_to
            ))
        
        return executions_response
        
    except Exception as e:
        logger.error(f"Error listing workflow executions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list workflow executions: {str(e)}"
        )


@router.get("/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_workflow_execution(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific workflow execution with current status"""
    
    try:
        # Get execution from database
        execution = db.query(WorkflowExecution, WorkflowTemplate).join(
            WorkflowTemplate, WorkflowExecution.template_id == WorkflowTemplate.id
        ).filter(
            WorkflowExecution.id == uuid.UUID(execution_id),
            WorkflowExecution.tenant_id == current_user.tenant_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        execution_obj, template = execution
        
        # Get current status from Temporalio
        try:
            temporalio_status = await _call_temporalio_service(
                f"/workflows/status/{execution_obj.temporalio_workflow_id}"
            )
            
            # Update execution with current status
            if temporalio_status.get("status"):
                execution_obj.status = temporalio_status["status"]
                if temporalio_status.get("result"):
                    execution_obj.output_data = temporalio_status["result"]
                if temporalio_status["status"] == "completed":
                    execution_obj.completed_at = datetime.utcnow()
                    execution_obj.progress_percentage = 100
                
                db.commit()
        except:
            # Continue with database status if Temporalio unavailable
            pass
        
        return WorkflowExecutionResponse(
            id=str(execution_obj.id),
            template_id=str(execution_obj.template_id),
            template_name=template.name,
            template_version=execution_obj.template_version,
            tenant_id=execution_obj.tenant_id,
            temporalio_workflow_id=execution_obj.temporalio_workflow_id,
            input_data=execution_obj.input_data,
            current_step=execution_obj.current_step,
            status=execution_obj.status,
            progress_percentage=execution_obj.progress_percentage,
            output_data=execution_obj.output_data,
            generated_documents=execution_obj.generated_documents,
            error_message=execution_obj.error_message,
            started_at=execution_obj.started_at,
            completed_at=execution_obj.completed_at,
            estimated_completion=execution_obj.estimated_completion,
            initiated_by=execution_obj.initiated_by,
            assigned_to=execution_obj.assigned_to
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid execution ID format")
    except Exception as e:
        logger.error(f"Error getting workflow execution: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow execution: {str(e)}"
        )


@router.post("/{execution_id}/cancel")
async def cancel_workflow_execution(
    execution_id: str,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel workflow execution"""
    
    try:
        execution = db.query(WorkflowExecution).filter(
            WorkflowExecution.id == uuid.UUID(execution_id),
            WorkflowExecution.tenant_id == current_user.tenant_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        if execution.status in ["completed", "failed", "cancelled"]:
            raise HTTPException(status_code=400, detail="Cannot cancel completed workflow")
        
        # Cancel in Temporalio
        try:
            await _call_temporalio_service(
                f"/workflows/cancel/{execution.temporalio_workflow_id}",
                method="POST",
                data={"reason": reason}
            )
        except:
            pass  # Continue with database update even if Temporalio call fails
        
        # Update execution
        execution.status = "cancelled"
        execution.error_message = f"Cancelled by user: {reason}" if reason else "Cancelled by user"
        execution.completed_at = datetime.utcnow()
        
        db.commit()
        
        return {"message": "Workflow execution cancelled successfully"}
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid execution ID format")
    except Exception as e:
        logger.error(f"Error cancelling workflow execution: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow execution: {str(e)}"
        )


@router.get("/{execution_id}/logs")
async def get_workflow_execution_logs(
    execution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workflow execution logs and progress"""
    
    try:
        execution = db.query(WorkflowExecution).filter(
            WorkflowExecution.id == uuid.UUID(execution_id),
            WorkflowExecution.tenant_id == current_user.tenant_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Get execution log from Temporalio
        try:
            logs_response = await _call_temporalio_service(
                f"/workflows/query/{execution.temporalio_workflow_id}",
                method="POST",
                data={"query_type": "get_execution_log"}
            )
            
            execution_log = logs_response.get("result", [])
        except:
            execution_log = []
        
        # Get execution steps from database
        steps = db.query(WorkflowExecutionStep).filter(
            WorkflowExecutionStep.execution_id == execution.id
        ).order_by(WorkflowExecutionStep.started_at).all()
        
        return {
            "execution_id": str(execution.id),
            "status": execution.status,
            "current_step": execution.current_step,
            "progress_percentage": execution.progress_percentage,
            "execution_log": execution_log,
            "steps": [
                {
                    "step_id": step.step_id,
                    "step_name": step.step_name,
                    "step_type": step.step_type,
                    "status": step.status,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "duration_seconds": step.duration_seconds,
                    "assigned_to": step.assigned_to,
                    "error_message": step.error_message
                }
                for step in steps
            ],
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid execution ID format")
    except Exception as e:
        logger.error(f"Error getting workflow logs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow logs: {str(e)}"
        )


def _validate_input_data(input_data: Dict[str, Any], input_schema: Dict[str, Any]) -> None:
    """Validate user input against template schema"""
    
    required_fields = input_schema.get("required", [])
    properties = input_schema.get("properties", {})
    
    # Check required fields
    for field in required_fields:
        if field not in input_data or input_data[field] is None:
            raise HTTPException(
                status_code=400,
                detail=f"Required field '{field}' is missing or null"
            )
    
    # Validate field types (basic validation)
    for field, value in input_data.items():
        if field in properties:
            field_schema = properties[field]
            field_type = field_schema.get("type", "string")
            
            if field_type == "string" and not isinstance(value, str):
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field}' must be a string"
                )
            elif field_type == "number" and not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field}' must be a number"
                )
            elif field_type == "boolean" and not isinstance(value, bool):
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field}' must be a boolean"
                )
            
            # Check enum values
            if "enum" in field_schema and value not in field_schema["enum"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Field '{field}' must be one of: {field_schema['enum']}"
                )
