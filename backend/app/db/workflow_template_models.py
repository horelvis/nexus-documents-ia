"""
Workflow Template Models
Multi-tenant workflow template system for configurable business processes
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid

from app.db.base_class import Base


class WorkflowTemplate(Base):
    """
    Workflow Template - Configurable workflow definitions by tenant admins
    """
    __tablename__ = "engine_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Multi-tenant
    tenant_id = Column(String, nullable=False, index=True)
    
    # Template Basic Info
    name = Column(String, nullable=False)  # "Employee Onboarding", "Contract Renewal", etc.
    description = Column(Text)
    category = Column(String, nullable=False)  # "hr", "legal", "finance", "operations"
    
    # Template Configuration
    version = Column(String, default="1.0.0")
    status = Column(String, default="draft")  # "draft", "active", "deprecated"
    
    # Workflow Definition (JSON Schema)
    workflow_definition = Column(JSONB, nullable=False)  # Steps, activities, decision points
    input_schema = Column(JSONB, nullable=False)         # Required/optional fields for execution
    validation_rules = Column(JSONB, default={})        # Business rules and constraints
    notification_config = Column(JSONB, default={})     # Who gets notified and when
    
    # Template file info (stored in tenant storage)
    template_file_path = Column(String, nullable=True)
    template_file_name = Column(String, nullable=True)
    template_file_mime = Column(String, nullable=True)
    template_file_size = Column(Integer, nullable=True)
    template_file_updated_at = Column(DateTime)
    template_source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
    # Template file info (ODT stored in tenant storage)
    template_file_path = Column(String, nullable=True)
    template_file_name = Column(String, nullable=True)
    template_file_mime = Column(String, nullable=True)
    template_file_size = Column(Integer, nullable=True)
    template_file_updated_at = Column(DateTime)
    template_source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    
    # Template Metadata
    estimated_duration = Column(String)  # "2 days", "1 week", etc.
    complexity_level = Column(String, default="intermediate")  # "simple", "intermediate", "advanced"
    tags = Column(JSONB, default=[])     # Searchable tags
    
    # Usage Statistics
    usage_count = Column(Integer, default=0)
    success_rate = Column(Integer, default=100)  # Percentage
    
    # Permissions
    is_public = Column(Boolean, default=False)   # Available to all tenants
    allowed_roles = Column(JSONB, default=[])    # Roles that can execute this template
    
    # Audit
    created_by = Column(String, nullable=False)  # User who created the template
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    executions = relationship("WorkflowExecution", back_populates="template")


class WorkflowExecution(Base):
    """
    Workflow Execution - Instances of workflow templates being executed
    """
    __tablename__ = "workflow_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Multi-tenant
    tenant_id = Column(String, nullable=False, index=True)
    
    # Template Reference
    template_id = Column(UUID(as_uuid=True), ForeignKey("engine_templates.id"), nullable=False)
    template_version = Column(String, nullable=False)
    
    # Temporalio Integration
    temporalio_workflow_id = Column(String, unique=True, nullable=False, index=True)
    temporalio_run_id = Column(String)
    task_queue = Column(String, default="nexus-workflow-tasks")
    
    # Execution Data
    input_data = Column(JSONB, nullable=False)   # User-provided input
    current_step = Column(String)                # Current workflow step
    execution_context = Column(JSONB, default={})  # Runtime context and variables
    
    # Status
    status = Column(String, default="running")   # "running", "completed", "failed", "cancelled", "paused"
    progress_percentage = Column(Integer, default=0)
    
    # Results
    output_data = Column(JSONB)                  # Final workflow output
    generated_documents = Column(JSONB, default=[])  # Generated document IDs
    error_message = Column(Text)                 # Error details if failed
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    estimated_completion = Column(DateTime)
    
    # User Context
    initiated_by = Column(String, nullable=False)  # User who started the execution
    assigned_to = Column(String)                    # Current assignee (for manual steps)
    
    # Relationships
    template = relationship("WorkflowTemplate", back_populates="executions")
    steps = relationship("WorkflowExecutionStep", back_populates="execution")


class WorkflowExecutionStep(Base):
    """
    Individual steps within a workflow execution
    """
    __tablename__ = "workflow_execution_steps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Execution Reference
    execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id"), nullable=False)
    
    # Step Definition
    step_id = Column(String, nullable=False)     # ID from template definition
    step_name = Column(String, nullable=False)   # Human-readable name
    step_type = Column(String, nullable=False)   # "activity", "decision", "manual", "approval"
    
    # Step Data
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    step_context = Column(JSONB, default={})
    
    # Status
    status = Column(String, default="pending")   # "pending", "running", "completed", "failed", "skipped"
    retry_count = Column(Integer, default=0)
    
    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)
    
    # Assignment (for manual steps)
    assigned_to = Column(String)
    completed_by = Column(String)
    
    # Error Handling
    error_message = Column(Text)
    
    # Relationships
    execution = relationship("WorkflowExecution", back_populates="steps")


class WorkflowTemplateField(Base):
    """
    Configurable input fields for workflow templates
    """
    __tablename__ = "engine_template_fields"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Template Reference
    template_id = Column(UUID(as_uuid=True), ForeignKey("engine_templates.id"), nullable=False)
    
    # Field Definition
    field_name = Column(String, nullable=False)      # "employee_name", "contract_type", etc.
    field_label = Column(String, nullable=False)     # "Employee Name", "Contract Type"
    field_type = Column(String, nullable=False)      # "text", "select", "date", "file", "number"
    
    # Validation
    is_required = Column(Boolean, default=False)
    validation_rules = Column(JSONB, default={})     # min_length, max_length, regex, etc.
    
    # UI Configuration
    field_order = Column(Integer, default=0)
    field_group = Column(String)                     # Group fields in sections
    placeholder_text = Column(String)
    help_text = Column(String)
    
    # Options (for select fields)
    field_options = Column(JSONB, default=[])       # [{"value": "full_time", "label": "Full Time"}]
    
    # Default Values
    default_value = Column(String)
    
    # Conditional Logic
    show_conditions = Column(JSONB, default={})     # When to show this field
    
    # Relationships
    template = relationship("WorkflowTemplate", backref="fields")
