"""Workflow Executions Management API"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
import uuid

from temporalio.client import WorkflowHandle
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from app.core.config import settings
import httpx
from app.core.temporalio_client import temporalio_client
from app.workflows.dynamic_workflow import DynamicWorkflow, DynamicWorkflowInput

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer(auto_error=False)


# Pydantic Models
class WorkflowExecutionRequest(BaseModel):
    template_id: str = Field(..., description="Template ID to execute")
    input_data: Dict[str, Any] = Field(..., description="Workflow input data")
    tenant_id: str = Field(..., description="Tenant ID")
    workflow_id: Optional[str] = Field(None, description="Custom workflow ID")
    task_queue: Optional[str] = Field(None, description="Custom task queue")


class WorkflowExecutionResponse(BaseModel):
    success: bool
    workflow_id: str
    template_id: str
    status: str
    message: str
    started_at: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: str
    template_id: str
    tenant_id: str
    status: str  # "running", "completed", "failed", "cancelled"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None


@router.post("/start", response_model=WorkflowExecutionResponse)
async def start_workflow_execution(request: WorkflowExecutionRequest):
    """Start a new workflow execution from a template"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Generate workflow ID if not provided
        workflow_id = request.workflow_id or f"{request.template_id}-{uuid.uuid4().hex[:8]}"
        
        # Resolve template definition: try Core API first, fallback to local AI templates
        template_definition = None

        # Attempt fetch from Core (service-to-service)
        core_url = f"{settings.api_core_url}/api/v1/engine-templates/{request.template_id}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                # Prefer X-API-Key header (some core routes support microservice keys)
                headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}
                resp = await client.get(core_url, headers=headers)
                if resp.status_code == 200:
                    core_tpl = resp.json()
                    template_definition = {
                        "id": core_tpl.get("id", request.template_id),
                        "name": core_tpl.get("name", request.template_id),
                        "version": core_tpl.get("version", "1.0"),
                        "workflow_definition": core_tpl.get("workflow_definition"),
                    }
                else:
                    logger.info(f"Core template fetch not available ({resp.status_code}); using local templates")
        except Exception as core_err:
            logger.info(f"Core template fetch failed: {core_err}. Falling back to local templates")

        if not template_definition:
            from app.data.workflow_templates_ai import get_all_ai_enhanced_templates
            ai_templates = get_all_ai_enhanced_templates()
            for template in ai_templates:
                if template["id"] == request.template_id:
                    template_definition = template
                    break

        # Fallback to legacy template if still not found
        if not template_definition and request.template_id == "legal-advisory-template":
            template_definition = {
                "id": "legal-advisory-template",
                "name": "Asesoría Legal (Legacy)",
                "workflow_definition": {
                    "start_step": "intake",
                    "steps": [
                        {
                            "step_id": "intake",
                            "step_name": "Recopilación de Información",
                            "step_type": "activity",
                            "activity_type": "emma_ai_legal_analysis",
                            "activity_config": {},
                            "next_steps": {"success": "end"}
                        }
                    ]
                }
            }

        if not template_definition:
            raise HTTPException(status_code=404, detail=f"Template {request.template_id} not found")
        
        # Prepare workflow input with correct field names
        workflow_input = DynamicWorkflowInput(
            template_id=request.template_id,
            template_name=template_definition.get("name", "Unknown Template"),
            template_version=template_definition.get("version", "1.0"),
            tenant_id=request.tenant_id,
            user_id="test-user",  # TODO: Get from auth context
            execution_id=workflow_id,
            workflow_definition=template_definition["workflow_definition"],
            user_input_data=request.input_data,  # Correct field name
            context={}
        )

        # Start the workflow
        task_queue = request.task_queue or settings.temporalio_task_queue
        
        search_attributes = {}
        if request.tenant_id:
            search_attributes["TenantId"] = [request.tenant_id]
            # Provide fallback for clusters where TenantId is not registered yet
            search_attributes["CustomStringField"] = [request.tenant_id]
        if request.template_id:
            search_attributes["TemplateId"] = [request.template_id]

        handle = await temporalio_client.client.start_workflow(
            DynamicWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
            # Search Attributes to enable tenant-level isolation in queries
            search_attributes=search_attributes,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3
            )
        )

        logger.info(f"Started workflow {workflow_id} from template {request.template_id}")
        
        return WorkflowExecutionResponse(
            success=True,
            workflow_id=workflow_id,
            template_id=request.template_id,
            status="running",
            message=f"Workflow {workflow_id} started successfully",
            started_at=datetime.now().isoformat()
        )

    except WorkflowAlreadyStartedError:
        raise HTTPException(status_code=409, detail=f"Workflow with ID {workflow_id} already exists")
    except Exception as e:
        logger.error(f"Error starting workflow: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """Get the status of a workflow execution"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Get workflow handle
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        
        # Check if workflow exists and get its status
        try:
            describe = await handle.describe()
            
            # Determine status
            if describe.status.name == "RUNNING":
                status = "running"
                result = None
                error = None
                completed_at = None
            elif describe.status.name == "COMPLETED":
                status = "completed"
                try:
                    result = await handle.result()
                    if hasattr(result, 'dict'):
                        result = result.dict()
                    elif hasattr(result, '__dict__'):
                        result = result.__dict__
                except:
                    result = {"message": "Workflow completed successfully"}
                error = None
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            elif describe.status.name == "FAILED":
                status = "failed"
                result = None
                error = "Workflow execution failed"
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            elif describe.status.name == "CANCELLED":
                status = "cancelled"
                result = None
                error = "Workflow was cancelled"
                completed_at = describe.close_time.isoformat() if describe.close_time else None
            else:
                status = describe.status.name.lower()
                result = None
                error = None
                completed_at = None

            return WorkflowStatusResponse(
                workflow_id=workflow_id,
                template_id="unknown",  # TODO: Extract from workflow metadata
                tenant_id="unknown",  # TODO: Extract from workflow metadata
                status=status,
                result=result,
                error=error,
                created_at=describe.start_time.isoformat() if describe.start_time else datetime.now().isoformat(),
                completed_at=completed_at,
                progress=None  # TODO: Implement progress tracking
            )

        except Exception as e:
            # Workflow might not exist
            logger.warning(f"Workflow {workflow_id} not found or error getting status: {e}")
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow status for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow status: {str(e)}")


@router.post("/{workflow_id}/cancel")
async def cancel_workflow_execution(workflow_id: str):
    """Cancel a running workflow execution"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Get workflow handle and cancel
        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        await handle.cancel()
        
        logger.info(f"Cancelled workflow {workflow_id}")
        return {"message": f"Workflow {workflow_id} cancelled successfully"}

    except Exception as e:
        logger.error(f"Error cancelling workflow {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel workflow: {str(e)}")


@router.get("/", response_model=List[WorkflowStatusResponse])
async def list_workflow_executions(
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    limit: int = 50
):
    """List workflow executions with optional filtering via Temporal Visibility API"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        # Build Temporal visibility query
        clauses = []
        if workflow_type:
            # Temporal expects the registered type name
            clauses.append(f"WorkflowType = '{workflow_type}'")
        if status:
            clauses.append(f"ExecutionStatus = '{status.upper()}'")
        # If tenant_id tagging is used as search attribute, filter it (optional)
        # This will be effective only if workflows set Search Attributes like CustomStringField
        if tenant_id:
            # Prefer dedicated search attribute TenantId; include fallback to CustomStringField
            tenant_clause = f"(TenantId = '{tenant_id}' OR CustomStringField = '{tenant_id}')"
            clauses.append(tenant_clause)

        query = " AND ".join(clauses)

        results: List[WorkflowStatusResponse] = []
        async for wf in temporalio_client.client.list_workflows(query=query):
            try:
                # Describe to enrich with times and status when possible
                handle = temporalio_client.client.get_workflow_handle(wf.id, run_id=wf.run_id)
                desc = await handle.describe()
                # Map status
                if desc.status.name == "RUNNING":
                    st = "running"
                elif desc.status.name == "COMPLETED":
                    st = "completed"
                elif desc.status.name == "FAILED":
                    st = "failed"
                elif desc.status.name == "CANCELLED":
                    st = "cancelled"
                else:
                    st = desc.status.name.lower()

                results.append(
                    WorkflowStatusResponse(
                        workflow_id=wf.id,
                        template_id="unknown",
                        tenant_id="unknown",
                        status=st,
                        result=None,
                        error=None,
                        created_at=(desc.start_time.isoformat() if desc.start_time else datetime.utcnow().isoformat()),
                        completed_at=(desc.close_time.isoformat() if desc.close_time else None),
                        progress=None,
                    )
                )
                if len(results) >= limit:
                    break
            except Exception as enrich_err:
                logger.warning(f"Could not enrich workflow {wf.id}: {enrich_err}")
                # Fallback minimal info
                results.append(
                    WorkflowStatusResponse(
                        workflow_id=wf.id,
                        template_id="unknown",
                        tenant_id="unknown",
                        status=wf.status.name.lower() if hasattr(wf.status, 'name') else "unknown",
                        result=None,
                        error=None,
                        created_at=(wf.start_time.isoformat() if getattr(wf, 'start_time', None) else datetime.utcnow().isoformat()),
                        completed_at=None,
                        progress=None,
                    )
                )
                if len(results) >= limit:
                    break

        logger.info(f"Visibility list returned {len(results)} items. Query='{query}'")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing workflow executions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list workflow executions: {str(e)}")


@router.get("/{workflow_id}/history")
async def get_workflow_history(workflow_id: str):
    """Get the execution history (raw events) via Temporal service API"""
    try:
        if not temporalio_client.is_initialized:
            raise HTTPException(status_code=503, detail="Temporalio client not initialized")

        handle = temporalio_client.client.get_workflow_handle(workflow_id)
        # Try to obtain run_id via describe
        desc = await handle.describe()
        run_id = desc.run_id

        # Use the underlying workflow service to fetch history events
        from temporalio.api.workflowservice.v1 import GetWorkflowExecutionHistoryRequest
        from temporalio.api.common.v1 import WorkflowExecution

        svc = temporalio_client.client.workflow_service
        req = GetWorkflowExecutionHistoryRequest(
            namespace=temporalio_client.client.namespace,
            execution=WorkflowExecution(workflow_id=workflow_id, run_id=run_id),
            history_event_filter_type=1,  # HISTORY_EVENT_FILTER_TYPE_ALL_EVENT
            skip_archival=True,
        )
        resp = await svc.get_workflow_execution_history(req)

        events_simplified: List[Dict[str, Any]] = []
        for ev in resp.history.events:
            ev_type = ev.event_type.name if hasattr(ev.event_type, 'name') else str(ev.event_type)
            ts = ev.event_time.ToDatetime().isoformat() if hasattr(ev, 'event_time') and ev.event_time is not None else None
            events_simplified.append({
                "event_id": getattr(ev, 'event_id', None),
                "type": ev_type,
                "time": ts,
                # Store which attributes field is set for quick inspection
                "attributes": (ev.WhichOneof("attributes") if hasattr(ev, 'WhichOneof') else None),
            })

        return {
            "workflow_id": workflow_id,
            "run_id": run_id,
            "count": len(events_simplified),
            "events": events_simplified,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow history for {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow history: {str(e)}")
