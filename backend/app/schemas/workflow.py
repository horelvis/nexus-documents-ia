"""
Pydantic schemas for Workflow/Camunda integration.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ProcessInstanceState(str, Enum):
    """Process instance states."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"
    EXTERNALLY_TERMINATED = "EXTERNALLY_TERMINATED"
    INTERNALLY_TERMINATED = "INTERNALLY_TERMINATED"


class TaskState(str, Enum):
    """User task states."""
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# ============ Deployment Schemas ============

class DeploymentCreate(BaseModel):
    """Schema for deploying a BPMN process."""
    name: str = Field(..., description="Deployment name")
    bpmn_xml: str = Field(..., description="BPMN 2.0 XML content")
    source: Optional[str] = Field(None, description="Source identifier")


class DeploymentResponse(BaseModel):
    """Schema for deployment response."""
    id: str
    name: str
    deployment_time: Optional[datetime] = None
    source: Optional[str] = None
    deployed_process_definitions: List[Dict[str, Any]] = []


class DeploymentListResponse(BaseModel):
    """Schema for list of deployments."""
    deployments: List[DeploymentResponse]
    total: int


# ============ Process Definition Schemas ============

class ProcessDefinitionResponse(BaseModel):
    """Schema for process definition."""
    id: str
    key: str
    name: Optional[str] = None
    description: Optional[str] = None
    version: int
    version_tag: Optional[str] = None
    category: Optional[str] = None
    deployment_id: str
    resource: Optional[str] = None
    suspended: bool = False


class ProcessDefinitionListResponse(BaseModel):
    """Schema for list of process definitions."""
    definitions: List[ProcessDefinitionResponse]
    total: int


# ============ Process Instance Schemas ============

class ProcessVariable(BaseModel):
    """Schema for process variable."""
    name: str
    value: Any
    type: Optional[str] = None


class StartProcessRequest(BaseModel):
    """Schema for starting a process instance."""
    process_key: str = Field(..., description="Process definition key")
    business_key: Optional[str] = Field(None, description="Business key for correlation")
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Initial process variables")


class ProcessInstanceResponse(BaseModel):
    """Schema for process instance."""
    id: str
    definition_id: str
    definition_key: Optional[str] = None
    business_key: Optional[str] = None
    ended: bool = False
    suspended: bool = False
    links: Optional[List[Dict[str, Any]]] = None


class ProcessInstanceDetailResponse(ProcessInstanceResponse):
    """Schema for detailed process instance with variables."""
    variables: Dict[str, Any] = {}


class ProcessInstanceListResponse(BaseModel):
    """Schema for list of process instances."""
    instances: List[ProcessInstanceResponse]
    total: int


# ============ Task Schemas ============

class TaskResponse(BaseModel):
    """Schema for user task."""
    id: str
    name: str
    assignee: Optional[str] = None
    created: Optional[datetime] = None
    due: Optional[datetime] = None
    follow_up: Optional[datetime] = None
    description: Optional[str] = None
    execution_id: str
    owner: Optional[str] = None
    parent_task_id: Optional[str] = None
    priority: int = 0
    process_definition_id: str
    process_instance_id: str
    task_definition_key: str
    form_key: Optional[str] = None
    suspended: bool = False


class TaskDetailResponse(TaskResponse):
    """Schema for detailed task with variables."""
    variables: Dict[str, Any] = {}


class TaskListResponse(BaseModel):
    """Schema for list of tasks."""
    tasks: List[TaskResponse]
    total: int


class CompleteTaskRequest(BaseModel):
    """Schema for completing a task."""
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Task completion variables")


class ClaimTaskRequest(BaseModel):
    """Schema for claiming a task."""
    user_id: str = Field(..., description="User ID to assign the task to")


# ============ Document Approval Workflow Schemas ============

class SignerInfo(BaseModel):
    """Schema for signer information."""
    name: str
    email: str
    role: str = "signer"
    order: int = 1


class StartDocumentApprovalRequest(BaseModel):
    """Schema for starting document approval workflow."""
    document_id: str = Field(..., description="Document ID to approve")
    approver_id: str = Field(..., description="User ID of the approver")
    signers: Optional[List[SignerInfo]] = Field(None, description="List of signers (for signature workflows)")
    message: Optional[str] = Field(None, description="Message for approver/signers")
    require_signature: bool = Field(False, description="Whether digital signature is required")


class ApprovalDecisionRequest(BaseModel):
    """Schema for approval decision."""
    approved: bool = Field(..., description="Whether the document is approved")
    reason: Optional[str] = Field(None, description="Reason for decision (required if rejected)")
    signers: Optional[List[SignerInfo]] = Field(None, description="Signers to add (if approved with signature)")


# ============ Message Correlation Schemas ============

class CorrelateMessageRequest(BaseModel):
    """Schema for correlating a message to running processes."""
    message_name: str = Field(..., description="Name of the message to correlate")
    business_key: Optional[str] = Field(None, description="Business key for correlation")
    process_variables: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Variables to set")
    correlation_keys: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional correlation keys")


class CorrelateMessageResponse(BaseModel):
    """Schema for message correlation response."""
    result_type: str
    process_instance: Optional[ProcessInstanceResponse] = None
    execution: Optional[Dict[str, Any]] = None


# ============ Workflow Status Schemas ============

class WorkflowStatusResponse(BaseModel):
    """Schema for workflow status overview."""
    process_instance_id: str
    definition_key: str
    business_key: Optional[str] = None
    state: ProcessInstanceState
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    current_tasks: List[TaskResponse] = []
    variables: Dict[str, Any] = {}


# ============ Health Check Schema ============

class CamundaHealthResponse(BaseModel):
    """Schema for Camunda health status."""
    status: str
    camunda_url: Optional[str] = None
    service: Optional[str] = None
    camunda_status: Optional[str] = None
    engine_name: Optional[str] = None
    version: Optional[str] = None
    workers_running: int = 0
    active_topics: List[str] = []
    error: Optional[str] = None
