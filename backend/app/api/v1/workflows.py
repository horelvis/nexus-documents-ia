"""
Workflow API Endpoints

Provides REST API for managing BPMN workflows and approval processes.
Proxies requests to camunda-service microservice.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from typing import Optional, List
import logging

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.models import User
from app.services.workflow_service import get_workflow_service, WorkflowServiceError
from app.schemas.workflow import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentListResponse,
    ProcessDefinitionListResponse,
    StartProcessRequest,
    ProcessInstanceResponse,
    ProcessInstanceDetailResponse,
    ProcessInstanceListResponse,
    TaskResponse,
    TaskDetailResponse,
    TaskListResponse,
    CompleteTaskRequest,
    ClaimTaskRequest,
    StartDocumentApprovalRequest,
    ApprovalDecisionRequest,
    CorrelateMessageRequest,
    CorrelateMessageResponse,
    CamundaHealthResponse
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflows"])


# ============ Health & Info ============

@router.get("/health", response_model=CamundaHealthResponse)
async def workflow_health():
    """Check workflow service health."""
    service = get_workflow_service()
    result = await service.health_check()
    return result


# ============ Deployments ============

@router.post("/deployments", response_model=DeploymentResponse)
async def deploy_process(
    deployment: DeploymentCreate,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Deploy a BPMN process definition.

    Requires admin or team_member role.
    """
    if not current_user.is_admin and not current_user.is_team_member:
        raise HTTPException(status_code=403, detail="Only admins can deploy processes")

    service = get_workflow_service()
    try:
        result = await service.deploy_process(
            tenant_id=tenant_id,
            name=deployment.name,
            bpmn_xml=deployment.bpmn_xml,
            source=deployment.source
        )
        return result
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    name: Optional[str] = Query(None, description="Filter by name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """List BPMN deployments for the tenant."""
    service = get_workflow_service()
    try:
        result = await service.get_deployments(
            tenant_id=tenant_id,
            name=name,
            first_result=skip,
            max_results=limit
        )
        return {"deployments": result.get("deployments", []), "total": result.get("total", 0)}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/deployments/{deployment_id}")
async def delete_deployment(
    deployment_id: str,
    cascade: bool = Query(True, description="Cascade delete instances"),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Delete a deployment. Requires admin role."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can delete deployments")

    service = get_workflow_service()
    try:
        await service.delete_deployment(
            tenant_id=tenant_id,
            deployment_id=deployment_id,
            cascade=cascade
        )
        return {"status": "deleted", "deployment_id": deployment_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ============ Process Definitions ============

@router.get("/definitions", response_model=ProcessDefinitionListResponse)
async def list_process_definitions(
    key: Optional[str] = Query(None, description="Filter by process key"),
    latest_only: bool = Query(True, description="Only return latest versions"),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """List available process definitions."""
    service = get_workflow_service()
    try:
        result = await service.get_process_definitions(
            tenant_id=tenant_id,
            key=key,
            latest_version=latest_only
        )
        return {"definitions": result.get("definitions", []), "total": len(result.get("definitions", []))}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/definitions/{key}/xml")
async def get_process_definition_xml(
    key: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get BPMN XML for a process definition."""
    service = get_workflow_service()
    try:
        result = await service.get_process_definition_xml(
            tenant_id=tenant_id,
            key=key
        )
        return result
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ============ Process Instances ============

@router.post("/instances", response_model=ProcessInstanceResponse)
async def start_process(
    request: StartProcessRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Start a new process instance.

    The process key must correspond to a deployed process definition.
    Variables are passed as initial process variables.
    """
    service = get_workflow_service()

    # Add user and tenant info to variables
    variables = request.variables or {}
    variables["tenant_id"] = tenant_id
    variables["requester_id"] = str(current_user.id)
    variables["requester_email"] = current_user.email

    try:
        result = await service.start_process(
            tenant_id=tenant_id,
            process_key=request.process_key,
            variables=variables,
            business_key=request.business_key
        )
        return result
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/instances", response_model=ProcessInstanceListResponse)
async def list_process_instances(
    process_key: Optional[str] = Query(None, description="Filter by process key"),
    business_key: Optional[str] = Query(None, description="Filter by business key"),
    active_only: bool = Query(True, description="Only return active instances"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """List process instances for the tenant."""
    service = get_workflow_service()
    try:
        result = await service.get_process_instances(
            tenant_id=tenant_id,
            process_key=process_key,
            business_key=business_key,
            active=active_only if active_only else None,
            first_result=skip,
            max_results=limit
        )
        return {"instances": result.get("instances", []), "total": result.get("total", 0)}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/instances/{instance_id}", response_model=ProcessInstanceDetailResponse)
async def get_process_instance(
    instance_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get a specific process instance with its variables."""
    service = get_workflow_service()
    try:
        instance = await service.get_process_instance(
            tenant_id=tenant_id,
            instance_id=instance_id
        )
        variables = await service.get_process_instance_variables(
            tenant_id=tenant_id,
            instance_id=instance_id
        )
        instance["variables"] = variables.get("variables", {})
        return instance
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/instances/{instance_id}")
async def cancel_process_instance(
    instance_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Cancel a running process instance."""
    service = get_workflow_service()
    try:
        await service.cancel_process_instance(
            tenant_id=tenant_id,
            instance_id=instance_id
        )
        return {"status": "cancelled", "instance_id": instance_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ============ Tasks ============

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    assigned_to_me: bool = Query(True, description="Only show tasks assigned to current user"),
    process_key: Optional[str] = Query(None, description="Filter by process definition key"),
    process_instance_id: Optional[str] = Query(None, description="Filter by process instance"),
    include_unassigned: bool = Query(False, description="Include unassigned tasks"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    List user tasks.

    By default returns tasks assigned to the current user.
    Use assigned_to_me=false and include_unassigned=true to see all available tasks.
    """
    service = get_workflow_service()

    assignee = str(current_user.id) if assigned_to_me else None
    candidate = str(current_user.id) if include_unassigned and not assigned_to_me else None

    try:
        result = await service.get_tasks(
            tenant_id=tenant_id,
            assignee=assignee,
            candidate_user=candidate,
            process_instance_id=process_instance_id,
            process_definition_key=process_key,
            unassigned=include_unassigned if not assigned_to_me else None,
            first_result=skip,
            max_results=limit
        )
        return {"tasks": result.get("tasks", []), "total": result.get("total", 0)}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get a specific task with its variables."""
    service = get_workflow_service()
    try:
        task = await service.get_task(
            tenant_id=tenant_id,
            task_id=task_id
        )
        variables = await service.get_task_variables(
            tenant_id=tenant_id,
            task_id=task_id
        )
        task["variables"] = variables.get("variables", {})
        return task
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    request: CompleteTaskRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Complete a user task.

    Variables provided will be set as process variables.
    """
    service = get_workflow_service()

    # Add completion metadata
    variables = request.variables or {}
    variables["completed_by"] = str(current_user.id)
    variables["completed_by_email"] = current_user.email

    try:
        await service.complete_task(
            tenant_id=tenant_id,
            task_id=task_id,
            variables=variables
        )
        return {"status": "completed", "task_id": task_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/tasks/{task_id}/claim")
async def claim_task(
    task_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Claim a task for the current user."""
    service = get_workflow_service()
    try:
        await service.claim_task(
            tenant_id=tenant_id,
            task_id=task_id,
            user_id=str(current_user.id)
        )
        return {"status": "claimed", "task_id": task_id, "assignee": str(current_user.id)}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/tasks/{task_id}/unclaim")
async def unclaim_task(
    task_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Release a claimed task."""
    service = get_workflow_service()
    try:
        await service.unclaim_task(
            tenant_id=tenant_id,
            task_id=task_id
        )
        return {"status": "unclaimed", "task_id": task_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: str,
    request: ClaimTaskRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Assign a task to another user.

    Requires admin or team_member role.
    """
    if not current_user.is_admin and not current_user.is_team_member:
        raise HTTPException(status_code=403, detail="Only admins can assign tasks to others")

    service = get_workflow_service()
    try:
        await service.assign_task(
            tenant_id=tenant_id,
            task_id=task_id,
            user_id=request.user_id
        )
        return {"status": "assigned", "task_id": task_id, "assignee": request.user_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ============ Document Approval Workflow ============

@router.post("/document-approval", response_model=ProcessInstanceResponse)
async def start_document_approval(
    request: StartDocumentApprovalRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Start a document approval workflow.

    This is a convenience endpoint that starts the 'document-approval' process
    with the appropriate variables for document approval/signature workflows.
    """
    service = get_workflow_service()

    # Build process variables
    variables = {
        "document_id": request.document_id,
        "tenant_id": tenant_id,
        "requester_id": str(current_user.id),
        "requester_email": current_user.email,
        "approver_id": request.approver_id,
        "require_signature": request.require_signature,
        "message": request.message or ""
    }

    if request.signers:
        import json
        variables["signers"] = json.dumps([s.model_dump() for s in request.signers])

    try:
        result = await service.start_process(
            tenant_id=tenant_id,
            process_key="document-approval",
            variables=variables,
            business_key=f"doc-{request.document_id}"
        )
        logger.info(f"Started document approval workflow for document {request.document_id}")
        return result
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/tasks/{task_id}/approve")
async def submit_approval_decision(
    task_id: str,
    request: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Submit approval decision for a document review task.

    This completes the user task with the approval decision.
    """
    service = get_workflow_service()

    variables = {
        "approved": request.approved,
        "approval_decision": "approved" if request.approved else "rejected",
        "decision_by": str(current_user.id),
        "decision_by_email": current_user.email
    }

    if not request.approved and request.reason:
        variables["rejection_reason"] = request.reason

    if request.approved and request.signers:
        import json
        variables["signers"] = json.dumps([s.model_dump() for s in request.signers])

    try:
        await service.complete_task(
            tenant_id=tenant_id,
            task_id=task_id,
            variables=variables
        )
        decision = "approved" if request.approved else "rejected"
        return {"status": decision, "task_id": task_id}
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ============ Message Correlation ============

@router.post("/messages", response_model=CorrelateMessageResponse)
async def correlate_message(
    request: CorrelateMessageRequest,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Correlate a message to running process instances.

    Used to signal events to waiting processes (e.g., signature completed).
    """
    service = get_workflow_service()
    try:
        result = await service.correlate_message(
            tenant_id=tenant_id,
            message_name=request.message_name,
            business_key=request.business_key,
            process_variables=request.process_variables,
            correlation_keys=request.correlation_keys
        )
        return result
    except WorkflowServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
