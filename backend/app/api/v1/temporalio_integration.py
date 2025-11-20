"""
Temporalio Integration API - Bridge between Core API and Temporalio Service
Replaces custom BPMN AI with durable Temporalio workflows
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, Literal
from datetime import datetime
import logging
import httpx

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.cache import cache
from app.data.ai_workflow_catalog import (
    list_ai_workflows,
    get_ai_workflow,
    build_workflow_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/temporalio", tags=["Temporalio Workflows"])

WORKFLOW_SUMMARY_CACHE_KEY = "temporalio:workflows:summary"
WORKFLOW_SUMMARY_CACHE_TTL = 45  # seconds


# Pydantic Models
class ContractRenewalRequest(BaseModel):
    contract_id: str = Field(..., description="ID del contrato a renovar")
    tenant_id: str = Field(..., description="ID del tenant")
    user_id: str = Field(..., description="ID del usuario que solicita")
    employee_name: str = Field(..., description="Nombre del empleado")
    contract_type: str = Field(..., description="Tipo de contrato")
    expiration_date: str = Field(..., description="Fecha de expiración")
    position: str = Field(..., description="Posición del empleado")
    performance_rating: Optional[str] = Field(None, description="Rating de rendimiento")
    current_salary: Optional[str] = Field(None, description="Salario actual")
    force_regenerate: bool = Field(False, description="Forzar regeneración")


class EmployeeOnboardingRequest(BaseModel):
    employee_id: str = Field(..., description="ID del empleado")
    tenant_id: str = Field(..., description="ID del tenant")
    hr_user_id: str = Field(..., description="ID del usuario de HR")
    employee_name: str = Field(..., description="Nombre del empleado")
    position: str = Field(..., description="Posición")
    department: str = Field(..., description="Departamento")
    start_date: str = Field(..., description="Fecha de inicio")
    manager_id: str = Field(..., description="ID del manager")
    contract_type: str = Field(..., description="Tipo de contrato")
    salary: str = Field(..., description="Salario")
    work_location: str = Field(..., description="Ubicación de trabajo")
    equipment_needs: Optional[List[str]] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    success: bool
    workflow_id: str
    workflow_type: str
    status: str
    message: str
    started_at: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowExecutionStartRequest(BaseModel):
    template_id: str = Field(..., description="ID del template AI a ejecutar")
    tenant_id: Optional[str] = Field(None, description="ID del tenant que ejecuta")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Datos de entrada para el workflow")
    workflow_id: Optional[str] = Field(None, description="ID personalizado de workflow")
    task_queue: Optional[str] = Field(None, description="Task queue temporalio custom")

    @field_validator("tenant_id", "workflow_id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, value):
        from uuid import UUID
        if isinstance(value, UUID):
            return str(value)
        return value


class AIWorkflowFieldOption(BaseModel):
    label: str
    value: str


class AIWorkflowField(BaseModel):
    name: str
    label: str
    type: Literal["text", "textarea", "select", "number"]
    required: bool = True
    placeholder: Optional[str] = None
    helper_text: Optional[str] = None
    default_value: Optional[str] = None
    options: Optional[List[AIWorkflowFieldOption]] = None


class AIWorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    template_id: str
    tags: List[str] = Field(default_factory=list)
    estimated_duration: Optional[str] = None
    complexity: Optional[str] = None
    fields: List[AIWorkflowField]


class AIWorkflowExecutionRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict, description="Valores capturados desde el frontend")


async def _call_temporalio_service(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Helper function to call Temporalio service"""
    
    temporalio_url = settings.TEMPORALIO_SERVICE_URL or "http://temporalio-service:8000"
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
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
    except Exception as e:
        logger.error(f"Error calling Temporalio service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Temporalio service error: {str(e)}"
        )


def _invalidate_workflow_summary_cache() -> None:
    """Invalidate cached workflow summary to reflect new TemporalIO data."""
    try:
        cache.delete(WORKFLOW_SUMMARY_CACHE_KEY)
    except Exception as exc:
        logger.warning(f"Failed to invalidate workflow summary cache: {exc}")


async def _get_workflow_summary() -> Dict[str, Any]:
    """Fetch workflow summary with short-lived caching to avoid spamming TemporalIO."""
    cached = cache.get(WORKFLOW_SUMMARY_CACHE_KEY)
    if cached:
        return cached

    try:
        # Call /workflows/list instead of /workflows (which doesn't exist)
        data = await _call_temporalio_service("/workflows/list?limit=100")
        workflows = data.get("workflows", [])
    except HTTPException as e:
        # If service is down or error, return empty summary to avoid crashing dashboard
        logger.error(f"Error fetching workflows for summary: {e}")
        workflows = []
    except Exception as e:
        logger.error(f"Unexpected error fetching workflows for summary: {e}")
        workflows = []

    active_count = 0
    for workflow in workflows:
        status = (workflow.get("status") or "").lower()
        if status in {"running", "in-progress", "in_progress"}:
            active_count += 1

    summary = {
        "active": active_count,
        "total": len(workflows),
        "last_synced": datetime.utcnow().isoformat() + "Z",
    }

    try:
        cache.set(WORKFLOW_SUMMARY_CACHE_KEY, summary, ttl=WORKFLOW_SUMMARY_CACHE_TTL)
    except Exception as exc:
        logger.warning(f"Failed to cache workflow summary: {exc}")

    return summary


@router.get("/health")
async def temporalio_health():
    """Check Temporalio service health"""
    
    try:
        health_status = await _call_temporalio_service("/health")
        
        if health_status.get("status") == "healthy":
            return JSONResponse(
                status_code=200,
                content={
                    "status": "healthy",
                    "service": "temporalio-integration", 
                    "temporalio_service": health_status
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "service": "temporalio-integration",
                    "temporalio_service": health_status,
                    "message": "Temporalio service is degraded"
                }
            )
            
    except Exception as e:
        logger.error(f"Temporalio health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@router.get("/workflows/summary")
async def get_workflow_summary(current_user = Depends(get_current_user)):
    """Lightweight workflow summary for dashboard badges."""
    try:
        return await _get_workflow_summary()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching workflow summary: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow summary: {str(exc)}"
        )


@router.post("/contract-renewal", response_model=WorkflowResponse)
async def start_contract_renewal_workflow(
    request: ContractRenewalRequest,
    current_user = Depends(get_current_user)
):
    """Start contract renewal workflow using Temporalio"""
    
    try:
        logger.info(f"Starting Temporalio contract renewal for {request.contract_id}")
        
        # Prepare workflow data
        workflow_data = {
            "workflow_type": "contract_renewal",
            "input_data": request.dict(),
            "workflow_id": f"renewal_{request.contract_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        }
        
        # Start workflow via Temporalio service
        result = await _call_temporalio_service(
            "/workflows/start",
            method="POST",
            data=workflow_data
        )

        _invalidate_workflow_summary_cache()
        
        return WorkflowResponse(
            success=result.get("success", True),
            workflow_id=result.get("workflow_id"),
            workflow_type=result.get("workflow_type"),
            status=result.get("status"),
            message=result.get("message"),
            started_at=result.get("started_at")
        )
        
    except Exception as e:
        logger.error(f"Error starting contract renewal workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start contract renewal workflow: {str(e)}"
        )


@router.post("/employee-onboarding", response_model=WorkflowResponse)
async def start_employee_onboarding_workflow(
    request: EmployeeOnboardingRequest,
    current_user = Depends(get_current_user)
):
    """Start employee onboarding workflow using Temporalio"""
    
    try:
        logger.info(f"Starting Temporalio onboarding for {request.employee_name}")
        
        # Prepare workflow data
        workflow_data = {
            "workflow_type": "employee_onboarding",
            "input_data": request.dict(),
            "workflow_id": f"onboarding_{request.employee_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        }
        
        # Start workflow via Temporalio service
        result = await _call_temporalio_service(
            "/workflows/start",
            method="POST",
            data=workflow_data
        )

        _invalidate_workflow_summary_cache()
        
        return WorkflowResponse(
            success=result.get("success", True),
            workflow_id=result.get("workflow_id"),
            workflow_type=result.get("workflow_type"),
            status=result.get("status"),
            message=result.get("message"),
            started_at=result.get("started_at")
        )
        
    except Exception as e:
        logger.error(f"Error starting onboarding workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start onboarding workflow: {str(e)}"
        )


@router.get("/workflow/{workflow_id}/status", response_model=WorkflowResponse)
async def get_workflow_status(
    workflow_id: str,
    current_user = Depends(get_current_user)
):
    """Get workflow execution status"""
    
    try:
        result = await _call_temporalio_service(f"/workflows/status/{workflow_id}")
        
        return WorkflowResponse(
            success=True,
            workflow_id=result.get("workflow_id"),
            workflow_type=result.get("workflow_type"),
            status=result.get("status"),
            message=f"Workflow status: {result.get('status')}",
            started_at=result.get("created_at", ""),
            result=result.get("result"),
            error=result.get("error")
        )
        
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get workflow status: {str(e)}"
        )


@router.post("/workflow/{workflow_id}/query")
async def query_workflow(
    workflow_id: str,
    query_type: str,
    query_args: Optional[Dict[str, Any]] = None,
    current_user = Depends(get_current_user)
):
    """Query workflow state"""
    
    try:
        query_data = {
            "query_type": query_type,
            "query_args": query_args or {}
        }
        
        result = await _call_temporalio_service(
            f"/workflows/query/{workflow_id}",
            method="POST",
            data=query_data
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error querying workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query workflow: {str(e)}"
        )


@router.post("/workflow/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    reason: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Cancel workflow execution"""
    
    try:
        cancel_data = {"reason": reason} if reason else {}
        
        result = await _call_temporalio_service(
            f"/workflows/cancel/{workflow_id}",
            method="POST",
            data=cancel_data
        )

        _invalidate_workflow_summary_cache()
        
        return result
        
    except Exception as e:
        logger.error(f"Error cancelling workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow: {str(e)}"
        )


@router.get("/workflows")
async def list_workflows(
    workflow_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    current_user = Depends(get_current_user)
):
    """List workflows with filtering"""
    
    try:
        params = []
        if workflow_type:
            params.append(f"workflow_type={workflow_type}")
        if status:
            params.append(f"status={status}")
        if limit != 50:
            params.append(f"limit={limit}")
        
        query_string = "&" + "&".join(params) if params else ""
        
        result = await _call_temporalio_service(f"/workflows/list{query_string}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list workflows: {str(e)}"
        )


@router.get("/workflow-templates")
async def list_ai_workflow_templates(current_user = Depends(get_current_user)):
    """List AI-enhanced workflow templates through backend proxy."""
    try:
        templates = await _call_temporalio_service("/workflow-templates")
        return templates
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching AI workflow templates: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow templates: {str(exc)}"
        )


@router.get("/workflow-templates/{template_id}")
async def get_ai_workflow_template(
    template_id: str,
    current_user = Depends(get_current_user)
):
    """Fetch single AI workflow template."""
    try:
        template = await _call_temporalio_service(f"/workflow-templates/{template_id}")
        return template
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching workflow template {template_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow template: {str(exc)}"
        )


@router.post("/workflow-executions/start")
async def start_ai_workflow_execution(
    request: WorkflowExecutionStartRequest,
    current_user = Depends(get_current_user)
):
    """Start AI agent workflow via Temporalio microservice."""
    try:
        payload = request.dict()
        payload["tenant_id"] = request.tenant_id or getattr(current_user, "tenant_id", None)

        if not payload.get("tenant_id"):
            raise HTTPException(status_code=400, detail="tenant_id is required to start workflow")

        result = await _call_temporalio_service(
            "/workflow-executions/start",
            method="POST",
            data=payload
        )

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error starting AI workflow execution: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow execution: {str(exc)}"
        )


@router.get("/workflow-executions/{workflow_id}")
async def get_ai_workflow_execution(
    workflow_id: str,
    current_user = Depends(get_current_user)
):
    """Get AI workflow execution status."""
    try:
        result = await _call_temporalio_service(f"/workflow-executions/{workflow_id}")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching workflow execution {workflow_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow execution: {str(exc)}"
        )


@router.post("/workflow-executions/{workflow_id}/cancel")
async def cancel_ai_workflow_execution(
    workflow_id: str,
    reason: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    """Cancel AI workflow execution."""
    try:
        payload = {"reason": reason} if reason else {}
        result = await _call_temporalio_service(
            f"/workflow-executions/{workflow_id}/cancel",
            method="POST",
            data=payload
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error cancelling workflow execution {workflow_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow execution: {str(exc)}"
        )


@router.get("/workflow-executions/{workflow_id}/history")
async def get_ai_workflow_execution_history(
    workflow_id: str,
    current_user = Depends(get_current_user)
):
    """Get workflow execution history from Temporalio microservice."""
    try:
        return await _call_temporalio_service(f"/workflow-executions/{workflow_id}/history")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching workflow history {workflow_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow execution history: {str(exc)}"
        )


@router.post("/demo/contract-renewal")
async def demo_contract_renewal_temporalio(
    fast: bool = True
):
    """Demo contract renewal using Temporalio (public endpoint for testing)"""
    
    try:
        logger.info(f"🚀 Starting Temporalio demo contract renewal (fast={fast})")
        
        # Call Temporalio service demo endpoint
        result = await _call_temporalio_service(
            f"/workflows/contract-renewal/demo?fast={fast}",
            method="POST"
        )

        _invalidate_workflow_summary_cache()
        
        return {
            **result,
            "demo_type": "temporalio_workflow",
            "architecture_note": "✅ Using Temporalio for durable workflow execution",
            "performance_note": f"{'⚡ Fast mode: immediate response' if fast else '🐌 Full mode: complete execution'}"
        }
        
    except Exception as e:
        logger.error(f"Error in Temporalio demo: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Temporalio demo failed: {str(e)}"
        )


@router.get("/ai-workflows", response_model=List[AIWorkflowTemplateResponse])
async def list_ai_agent_workflows(current_user = Depends(get_current_user)):
    """Expose curated AI workflows with form metadata."""
    return list_ai_workflows()


@router.post("/ai-workflows/{workflow_id}/execute")
async def execute_ai_agent_workflow(
    workflow_id: str,
    request: AIWorkflowExecutionRequest,
    current_user = Depends(get_current_user)
):
    """Execute a curated AI workflow without exposing raw JSON handling to the frontend."""
    workflow_def = get_ai_workflow(workflow_id)
    if not workflow_def:
        raise HTTPException(status_code=404, detail=f"AI workflow {workflow_id} not found")

    field_values = request.payload or {}
    missing_fields = []
    for field in workflow_def.get("fields", []):
        if field.get("required", True) and not field_values.get(field["name"]):
            missing_fields.append(field["label"] or field["name"])

    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Faltan campos obligatorios: {', '.join(missing_fields)}"
        )

    normalized_payload = build_workflow_payload(workflow_id, field_values)
    tenant_id = field_values.get("tenant_id") or getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id es obligatorio para ejecutar workflows")

    start_payload = {
        "template_id": workflow_def["template_id"],
        "tenant_id": tenant_id,
        "input_data": normalized_payload,
    }

    return await _call_temporalio_service(
        "/workflow-executions/start",
        method="POST",
        data=start_payload
    )
