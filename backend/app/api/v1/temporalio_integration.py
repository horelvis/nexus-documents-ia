"""
Temporalio Integration API - Bridge between Core API and Temporalio Service
Replaces custom BPMN AI with durable Temporalio workflows
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import httpx

from app.api.dependencies import get_current_user
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/temporalio", tags=["Temporalio Workflows"])


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


async def _call_temporalio_service(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Helper function to call Temporalio service"""
    
    temporalio_url = "http://temporalio-service:8010"
    
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
    except Exception as e:
        logger.error(f"Error calling Temporalio service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Temporalio service error: {str(e)}"
        )


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