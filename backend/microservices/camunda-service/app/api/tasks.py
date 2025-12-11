"""User task management endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from app.core.camunda_client import get_camunda_client

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    id: str
    name: Optional[str] = None
    assignee: Optional[str] = None
    created: Optional[str] = None
    due: Optional[str] = None
    process_instance_id: Optional[str] = None
    process_definition_key: Optional[str] = None
    task_definition_key: Optional[str] = None
    tenant_id: Optional[str] = None


class TaskListResponse(BaseModel):
    tasks: list[dict]
    total: int


class CompleteTaskRequest(BaseModel):
    variables: Optional[dict[str, Any]] = None


class ClaimTaskRequest(BaseModel):
    user_id: str


class AssignTaskRequest(BaseModel):
    user_id: str


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    tenant_id: Optional[str] = None,
    assignee: Optional[str] = None,
    candidate_user: Optional[str] = None,
    process_instance_id: Optional[str] = None,
    process_definition_key: Optional[str] = None,
    unassigned: Optional[bool] = None,
    first_result: int = 0,
    max_results: int = 100
):
    """
    List user tasks.

    Filter by:
    - tenant_id: Tasks for a specific tenant
    - assignee: Tasks assigned to a specific user
    - candidate_user: Tasks where user is a candidate
    - process_instance_id: Tasks for a specific process instance
    - process_definition_key: Tasks for a specific process type
    - unassigned: Only unassigned tasks
    """
    client = get_camunda_client()

    try:
        tasks = await client.get_tasks(
            tenant_id=tenant_id,
            assignee=assignee,
            candidate_user=candidate_user,
            process_instance_id=process_instance_id,
            process_definition_key=process_definition_key,
            unassigned=unassigned,
            first_result=first_result,
            max_results=max_results
        )

        return TaskListResponse(
            tasks=tasks,
            total=len(tasks)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get a specific task."""
    client = get_camunda_client()

    try:
        task = await client.get_task(task_id)
        return TaskResponse(
            id=task.get("id"),
            name=task.get("name"),
            assignee=task.get("assignee"),
            created=task.get("created"),
            due=task.get("due"),
            process_instance_id=task.get("processInstanceId"),
            process_definition_key=task.get("processDefinitionKey"),
            task_definition_key=task.get("taskDefinitionKey"),
            tenant_id=task.get("tenantId")
        )

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Task not found: {str(e)}")


@router.get("/{task_id}/variables")
async def get_task_variables(task_id: str):
    """Get all variables available in a task's scope."""
    client = get_camunda_client()

    try:
        return await client.get_task_variables(task_id)

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to get task variables: {str(e)}")


@router.post("/{task_id}/complete")
async def complete_task(task_id: str, request: CompleteTaskRequest = None):
    """
    Complete a user task.

    Optionally set variables when completing the task.
    Common variables for approval workflows:
    - approved: boolean
    - comment: string
    - next_assignee: string
    """
    client = get_camunda_client()

    try:
        variables = request.variables if request else None
        await client.complete_task(task_id, variables=variables)
        return {"message": f"Task {task_id} completed successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to complete task: {str(e)}")


@router.post("/{task_id}/claim")
async def claim_task(task_id: str, request: ClaimTaskRequest):
    """
    Claim a task for a user.

    The user becomes the assignee of the task.
    Only unassigned tasks or tasks in the user's candidate groups can be claimed.
    """
    client = get_camunda_client()

    try:
        await client.claim_task(task_id, request.user_id)
        return {"message": f"Task {task_id} claimed by {request.user_id}"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to claim task: {str(e)}")


@router.post("/{task_id}/unclaim")
async def unclaim_task(task_id: str):
    """
    Unclaim a task.

    Removes the current assignee, making the task available for others.
    """
    client = get_camunda_client()

    try:
        await client.unclaim_task(task_id)
        return {"message": f"Task {task_id} unclaimed"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to unclaim task: {str(e)}")


@router.post("/{task_id}/assign")
async def assign_task(task_id: str, request: AssignTaskRequest):
    """
    Assign a task to a user.

    Different from claim: can be done by any user with permission,
    not just the user being assigned.
    """
    client = get_camunda_client()

    try:
        await client.assign_task(task_id, request.user_id)
        return {"message": f"Task {task_id} assigned to {request.user_id}"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to assign task: {str(e)}")
