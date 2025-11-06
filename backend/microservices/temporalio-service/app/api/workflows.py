"""Workflow execution and management endpoints"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import uuid

from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedException

from app.core.config import settings
from app.core.temporalio_client import temporalio_client
from app.workflows.contract_renewal import ContractRenewalWorkflow, ContractRenewalInput
from app.workflows.employee_onboarding import EmployeeOnboardingWorkflow, EmployeeOnboardingInput

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


# Pydantic Models
class WorkflowStartRequest(BaseModel):
    workflow_type: str = Field(..., description="Type of workflow to start")
    input_data: Dict[str, Any] = Field(..., description="Workflow input data")
    workflow_id: Optional[str] = Field(None, description="Custom workflow ID")
    task_queue: Optional[str] = Field(None, description="Custom task queue")


class WorkflowStartResponse(BaseModel):
    success: bool
    workflow_id: str
    workflow_type: str
    status: str
    message: str
    started_at: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    workflow_type: str
    status: str  # "running", "completed", "failed", "cancelled"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class WorkflowQueryRequest(BaseModel):
    query_type: str = Field(..., description="Type of query to execute")
    query_args: Optional[Dict[str, Any]] = Field(default_factory=dict)


def verify_api_key(authorization: Optional[str] = Depends(security)) -> bool:
    """Verify API key authorization"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    token = authorization.credentials
    if token != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True


@router.post("/start", response_model=WorkflowStartResponse)
async def start_workflow(
    request: WorkflowStartRequest,
    _: bool = Depends(verify_api_key)
):
    """Start a new workflow execution"""
    
    try:
        # Generate workflow ID if not provided
        workflow_id = request.workflow_id or f"{request.workflow_type}_{uuid.uuid4().hex[:8]}"
        task_queue = request.task_queue or settings.TEMPORALIO_TASK_QUEUE
        
        logger.info(f"Starting workflow: {request.workflow_type} with ID: {workflow_id}")
        
        # Select workflow class and prepare input
        if request.workflow_type == "contract_renewal":
            workflow_class = ContractRenewalWorkflow
            workflow_input = ContractRenewalInput(**request.input_data)
            
        elif request.workflow_type == "employee_onboarding":
            workflow_class = EmployeeOnboardingWorkflow
            workflow_input = EmployeeOnboardingInput(**request.input_data)
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown workflow type: {request.workflow_type}"
            )
        
        # Start the workflow
        handle = await temporalio_client.client.start_workflow(
            workflow_class.run,
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
            retry_policy=RetryPolicy(maximum_attempts=3)
        )
        
        started_at = datetime.utcnow().isoformat()
        
        return WorkflowStartResponse(
            success=True,
            workflow_id=workflow_id,
            workflow_type=request.workflow_type,
            status="running",
            message=f"Workflow {request.workflow_type} started successfully",
            started_at=started_at
        )
        
    except WorkflowAlreadyStartedException:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow with ID {workflow_id} is already running"
        )
        
    except Exception as e:
        logger.error(f"Error starting workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start workflow: {str(e)}"
        )


@router.get("/status/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    workflow_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get workflow execution status and result"""
    
    try:
        logger.info(f"Getting status for workflow: {workflow_id}")
        
        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Check if workflow is still running
        workflow_result = None
        workflow_error = None
        completed_at = None
        
        try:
            # This will raise an exception if workflow is still running
            workflow_result = await handle.result()
            completed_at = datetime.utcnow().isoformat()
            status = "completed"
            
        except Exception as e:
            # Workflow might still be running or failed
            try:
                # Try to get workflow info
                description = await handle.describe()
                if description.status.name == "RUNNING":
                    status = "running"
                elif description.status.name == "FAILED":
                    status = "failed"
                    workflow_error = str(e)
                elif description.status.name == "CANCELLED":
                    status = "cancelled"
                else:
                    status = "unknown"
                    
            except Exception as desc_error:
                logger.error(f"Error getting workflow description: {desc_error}")
                status = "unknown"
                workflow_error = str(e)
        
        # Try to determine workflow type from ID
        workflow_type = "unknown"
        if workflow_id.startswith("contract_renewal"):
            workflow_type = "contract_renewal"
        elif workflow_id.startswith("employee_onboarding"):
            workflow_type = "employee_onboarding"
        
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            status=status,
            result=workflow_result.__dict__ if workflow_result else None,
            error=workflow_error,
            created_at=datetime.utcnow().isoformat(),  # Approximation
            completed_at=completed_at
        )
        
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}")
        raise HTTPException(
            status_code=404,
            detail=f"Workflow {workflow_id} not found or error retrieving status"
        )


@router.post("/query/{workflow_id}")
async def query_workflow(
    workflow_id: str,
    request: WorkflowQueryRequest,
    _: bool = Depends(verify_api_key)
):
    """Execute a query against a running workflow"""
    
    try:
        logger.info(f"Querying workflow {workflow_id} with query: {request.query_type}")
        
        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Execute query based on type
        if request.query_type == "get_workflow_state":
            result = await handle.query("get_workflow_state")
            
        elif request.query_type == "get_execution_log":
            result = await handle.query("get_execution_log")
            
        elif request.query_type == "get_onboarding_progress":
            result = await handle.query("get_onboarding_progress")
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown query type: {request.query_type}"
            )
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "query_type": request.query_type,
            "result": result,
            "queried_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error querying workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query workflow: {str(e)}"
        )


@router.post("/signal/{workflow_id}")
async def signal_workflow(
    workflow_id: str,
    signal_name: str,
    signal_args: Optional[Dict[str, Any]] = None,
    _: bool = Depends(verify_api_key)
):
    """Send a signal to a running workflow"""
    
    try:
        logger.info(f"Sending signal {signal_name} to workflow {workflow_id}")
        
        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Send signal
        if signal_args:
            await handle.signal(signal_name, **signal_args)
        else:
            await handle.signal(signal_name)
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "signal_name": signal_name,
            "message": f"Signal {signal_name} sent successfully",
            "signaled_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error sending signal to workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send signal: {str(e)}"
        )


@router.post("/cancel/{workflow_id}")
async def cancel_workflow(
    workflow_id: str,
    reason: Optional[str] = None,
    _: bool = Depends(verify_api_key)
):
    """Cancel a running workflow"""
    
    try:
        logger.info(f"Cancelling workflow {workflow_id}")
        
        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Cancel workflow
        await handle.cancel()
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": f"Workflow cancelled successfully",
            "reason": reason,
            "cancelled_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error cancelling workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel workflow: {str(e)}"
        )


@router.get("/list")
async def list_workflows(
    workflow_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    _: bool = Depends(verify_api_key)
):
    """List workflows with optional filtering"""
    
    try:
        logger.info(f"Listing workflows with type: {workflow_type}, status: {status}")
        
        # Build query
        query = ""
        if workflow_type:
            query += f"WorkflowType = '{workflow_type}'"
        if status:
            if query:
                query += " AND "
            query += f"ExecutionStatus = '{status.upper()}'"
        
        # List workflows
        workflows = []
        async for workflow in temporalio_client.client.list_workflows(query=query):
            workflows.append({
                "workflow_id": workflow.id,
                "workflow_type": workflow.workflow_type,
                "status": workflow.status.name,
                "start_time": workflow.start_time.isoformat() if workflow.start_time else None,
                "execution_time": workflow.execution_time.isoformat() if workflow.execution_time else None,
                "task_queue": workflow.task_queue
            })
            
            if len(workflows) >= limit:
                break
        
        return {
            "success": True,
            "workflows": workflows,
            "count": len(workflows),
            "query": query,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list workflows: {str(e)}"
        )


@router.post("/contract-renewal/demo")
async def demo_contract_renewal_temporalio(
    fast: bool = True,
    _: bool = Depends(verify_api_key)
):
    """Demo contract renewal using Temporalio workflow"""
    
    try:
        # Prepare demo data
        demo_input = ContractRenewalInput(
            contract_id="demo_contract_temporalio_001",
            tenant_id="demo_tenant",
            user_id="demo_user",
            employee_name="Ana González Demo",
            contract_type="temporal",
            expiration_date="2025-02-15",
            position="Desarrolladora Senior",
            performance_rating="Excelente",
            current_salary="45000",
            force_regenerate=True
        )
        
        # Generate unique workflow ID
        workflow_id = f"contract_renewal_demo_{uuid.uuid4().hex[:8]}"
        
        # Start the workflow
        handle = await temporalio_client.client.start_workflow(
            ContractRenewalWorkflow.run,
            demo_input,
            id=workflow_id,
            task_queue=settings.TEMPORALIO_TASK_QUEUE,
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        if fast:
            # Return immediately without waiting for completion
            return {
                "success": True,
                "message": "Demo contract renewal workflow started with Temporalio",
                "workflow_id": workflow_id,
                "status": "running",
                "demo_mode": "fast",
                "note": "Use /workflows/status/{workflow_id} to check progress",
                "started_at": datetime.utcnow().isoformat()
            }
        else:
            # Wait for completion (full demo)
            try:
                result = await handle.result()
                return {
                    "success": True,
                    "message": "Demo contract renewal workflow completed",
                    "workflow_id": workflow_id,
                    "status": "completed",
                    "demo_mode": "full",
                    "result": result.__dict__,
                    "completed_at": datetime.utcnow().isoformat()
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": "Demo workflow failed",
                    "workflow_id": workflow_id,
                    "error": str(e),
                    "failed_at": datetime.utcnow().isoformat()
                }
        
    except Exception as e:
        logger.error(f"Error in demo workflow: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Demo workflow failed: {str(e)}"
        )