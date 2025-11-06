"""
Dynamic Workflow Engine - Executes workflow templates configured by admins
"""
from datetime import timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

# Activities will be imported by the worker, not here
# This keeps the workflow definition clean


@dataclass
class DynamicWorkflowInput:
    """Input for dynamic workflow execution"""
    template_id: str
    template_name: str
    template_version: str
    tenant_id: str
    user_id: str
    execution_id: str
    workflow_definition: Dict[str, Any]
    user_input_data: Dict[str, Any]
    context: Dict[str, Any] = None


@dataclass
class DynamicWorkflowResult:
    """Result of dynamic workflow execution"""
    execution_id: str
    template_id: str
    template_name: str
    final_status: str  # "completed", "failed", "cancelled"
    execution_context: Dict[str, Any]
    generated_outputs: Dict[str, Any]
    execution_log: List[Dict[str, Any]]
    completed_at: str


@workflow.defn
class DynamicWorkflow:
    """
    Generic workflow that executes any workflow template configuration
    
    This workflow reads the template definition and executes steps dynamically:
    - Manual steps: Wait for user input/approval
    - Activity steps: Execute configured activities 
    - Decision steps: Evaluate conditions and branch
    - Parallel steps: Execute multiple activities concurrently
    """
    
    def __init__(self) -> None:
        self._execution_log: List[Dict[str, Any]] = []
        self._workflow_state = "INITIALIZING"
        self._execution_context: Dict[str, Any] = {}
        self._current_step: Optional[str] = None
    
    @workflow.run
    async def run(self, input_data: DynamicWorkflowInput) -> DynamicWorkflowResult:
        """Execute dynamic workflow based on template definition"""
        
        workflow_id = workflow.info().workflow_id
        self._execution_context = input_data.context or {}
        self._execution_context.update({
            "workflow_id": workflow_id,
            "template_id": input_data.template_id,
            "tenant_id": input_data.tenant_id,
            "user_id": input_data.user_id,
            "user_input": input_data.user_input_data
        })
        
        self._log_step("workflow_started", {"workflow_id": workflow_id})
        
        try:
            workflow_def = input_data.workflow_definition
            
            # Debug: Log workflow definition structure
            workflow.logger.info(f"Workflow definition keys: {list(workflow_def.keys()) if workflow_def else 'None'}")
            if workflow_def:
                workflow.logger.info(f"Start step in definition: {'start_step' in workflow_def}")
                if 'start_step' in workflow_def:
                    workflow.logger.info(f"Start step value: {workflow_def['start_step']}")
            
            start_step_id = workflow_def.get("start_step")
            
            if not start_step_id:
                workflow.logger.error(f"No start step found. Workflow def: {workflow_def}")
                raise ValueError(f"No start step defined in workflow. Available keys: {list(workflow_def.keys()) if workflow_def else 'None'}")
            
            # Execute workflow steps
            final_result = await self._execute_step_sequence(workflow_def, start_step_id)
            
            self._workflow_state = "COMPLETED"
            completion_time = workflow.now().isoformat()
            
            self._log_step("workflow_completed", {
                "final_status": "completed",
                "completion_time": completion_time
            })
            
            return DynamicWorkflowResult(
                execution_id=input_data.execution_id,
                template_id=input_data.template_id,
                template_name=input_data.template_name,
                final_status="completed",
                execution_context=self._execution_context,
                generated_outputs=final_result,
                execution_log=self._execution_log,
                completed_at=completion_time
            )
            
        except Exception as e:
            self._workflow_state = "FAILED"
            self._log_step("workflow_failed", {"error": str(e)})
            
            # Send failure notification
            try:
                await workflow.execute_activity(
                    notification_activities.send_system_notification,
                    args=[{
                        "tenant_id": input_data.tenant_id,
                        "user_id": input_data.user_id,
                        "notification_type": "workflow_failed",
                        "message": f"Workflow '{input_data.template_name}' failed: {str(e)}",
                        "execution_id": input_data.execution_id
                    }],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=1)
                )
            except:
                pass
            
            raise
    
    async def _execute_step_sequence(self, workflow_def: Dict[str, Any], start_step_id: str) -> Dict[str, Any]:
        """Execute sequence of workflow steps"""
        
        steps_map = {step["step_id"]: step for step in workflow_def["steps"]}
        current_step_id = start_step_id
        step_results = {}
        
        while current_step_id and current_step_id != "end":
            if current_step_id not in steps_map:
                raise ValueError(f"Step '{current_step_id}' not found in workflow definition")
            
            step_def = steps_map[current_step_id]
            self._current_step = current_step_id
            self._workflow_state = f"EXECUTING_{current_step_id.upper()}"
            
            # Execute the step
            step_result = await self._execute_single_step(step_def)
            step_results[current_step_id] = step_result
            
            # Determine next step
            current_step_id = self._determine_next_step(step_def, step_result)
            
        return step_results
    
    async def _execute_single_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single workflow step"""
        
        step_id = step_def["step_id"]
        step_type = step_def["step_type"]
        
        self._log_step(f"step_started", {
            "step_id": step_id,
            "step_name": step_def["step_name"],
            "step_type": step_type
        })
        
        try:
            if step_type == "activity":
                result = await self._execute_activity_step(step_def)
            elif step_type == "manual":
                result = await self._execute_manual_step(step_def)
            elif step_type == "decision":
                result = await self._execute_decision_step(step_def)
            elif step_type == "approval":
                result = await self._execute_approval_step(step_def)
            elif step_type == "parallel":
                result = await self._execute_parallel_step(step_def)
            else:
                raise ValueError(f"Unknown step type: {step_type}")
            
            self._log_step(f"step_completed", {
                "step_id": step_id,
                "result": result
            })
            
            return result
            
        except Exception as e:
            self._log_step(f"step_failed", {
                "step_id": step_id,
                "error": str(e)
            })
            raise
    
    async def _execute_activity_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an activity step"""
        
        activity_type = step_def.get("activity_type")
        activity_config = step_def.get("activity_config", {})
        
        # Prepare activity input
        activity_input = {
            **self._execution_context,
            **activity_config,
            "step_config": step_def
        }
        
        # Map activity types to actual activities - AI Agents Integration
        if activity_type == "emma_legal_advisor_agent":
            from app.activities.ai_agent_activities import emma_legal_advisor_agent
            result = await workflow.execute_activity(
                emma_legal_advisor_agent,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "emma_document_analyzer_agent":
            from app.activities.ai_agent_activities import emma_document_analyzer_agent
            result = await workflow.execute_activity(
                emma_document_analyzer_agent,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=8),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "multi_agent_coordinator":
            from app.activities.ai_agent_activities import multi_agent_coordinator
            result = await workflow.execute_activity(
                multi_agent_coordinator,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "agent_state_persistence":
            from app.activities.ai_agent_activities import agent_state_persistence
            result = await workflow.execute_activity(
                agent_state_persistence,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
        # Legacy activity types for backward compatibility
        elif activity_type == "emma_ai_legal_analysis":
            # Map to new agent system
            from app.activities.ai_agent_activities import emma_legal_advisor_agent
            result = await workflow.execute_activity(
                emma_legal_advisor_agent,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "legal_document_generation":
            from app.activities.ai_agent_activities import emma_document_analyzer_agent
            result = await workflow.execute_activity(
                emma_document_analyzer_agent,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "emma_case_recommendation":
            from app.activities.ai_agent_activities import emma_legal_advisor_agent
            result = await workflow.execute_activity(
                emma_legal_advisor_agent,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "case_documentation":
            result = await workflow.execute_activity(
                dynamic_activities.create_case_documentation,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        elif activity_type == "send_notification":
            result = await workflow.execute_activity(
                notification_activities.send_configured_notification,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
        else:
            # Generic activity execution
            result = await workflow.execute_activity(
                dynamic_activities.execute_generic_activity,
                args=[activity_input],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
        
        # Update execution context with result
        if result.get("context_updates"):
            self._execution_context.update(result["context_updates"])
        
        return result
    
    async def _execute_manual_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a manual step - wait for human input"""
        
        # In a real implementation, this would create a task assignment
        # and wait for completion via signal
        
        assignee_role = step_def.get("assignee_role")
        instructions = step_def.get("instructions", "")
        
        # Create manual task
        task_result = await workflow.execute_activity(
            dynamic_activities.create_manual_task,
            args=[{
                **self._execution_context,
                "step_id": step_def["step_id"],
                "assignee_role": assignee_role,
                "instructions": instructions,
                "step_config": step_def
            }],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        # For demo purposes, simulate task completion
        # In production, this would wait for a signal with the actual result
        simulated_result = {
            "task_id": task_result.get("task_id"),
            "assignee_role": assignee_role,
            "status": "completed",
            "manual_input": {
                "decision": "approved",
                "notes": "Task completed successfully",
                "completion_time": workflow.now().isoformat()
            }
        }
        
        return simulated_result
    
    async def _execute_decision_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a decision step - evaluate conditions"""
        
        decision_conditions = step_def.get("decision_conditions", {})
        
        # Execute decision logic
        decision_result = await workflow.execute_activity(
            dynamic_activities.evaluate_decision_conditions,
            args=[{
                **self._execution_context,
                "conditions": decision_conditions,
                "step_config": step_def
            }],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        return decision_result
    
    async def _execute_approval_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an approval step"""
        
        # Similar to manual step but with approval-specific logic
        approval_result = await workflow.execute_activity(
            dynamic_activities.create_approval_request,
            args=[{
                **self._execution_context,
                "step_config": step_def
            }],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2)
        )
        
        # Simulate approval
        return {
            **approval_result,
            "approval_status": "approved",
            "approved_by": "system_demo",
            "approved_at": workflow.now().isoformat()
        }
    
    async def _execute_parallel_step(self, step_def: Dict[str, Any]) -> Dict[str, Any]:
        """Execute parallel activities"""
        
        parallel_activities = step_def.get("parallel_activities", [])
        
        # Execute all activities in parallel
        activity_tasks = []
        for activity_def in parallel_activities:
            task = workflow.execute_activity(
                dynamic_activities.execute_generic_activity,
                args=[{
                    **self._execution_context,
                    **activity_def,
                    "step_config": step_def
                }],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            activity_tasks.append(task)
        
        # Wait for all activities to complete
        results = await workflow.gather(*activity_tasks)
        
        return {
            "parallel_results": results,
            "completed_activities": len(results)
        }
    
    def _determine_next_step(self, step_def: Dict[str, Any], step_result: Dict[str, Any]) -> Optional[str]:
        """Determine next step based on current step result"""
        
        next_steps = step_def.get("next_steps", {})
        
        if not next_steps:
            return "end"
        
        # Simple next step logic - can be made more complex
        if step_result.get("status") == "failed":
            return next_steps.get("failure", "end")
        elif step_result.get("decision") == "approved":
            return next_steps.get("approved", next_steps.get("success", "end"))
        elif step_result.get("decision") == "rejected":
            return next_steps.get("rejected", next_steps.get("failure", "end"))
        else:
            return next_steps.get("continue", next_steps.get("success", "end"))
    
    def _log_step(self, step_name: str, data: Any) -> None:
        """Log workflow execution step"""
        self._execution_log.append({
            "step": step_name,
            "timestamp": workflow.now().isoformat(),
            "current_step": self._current_step,
            "state": self._workflow_state,
            "data": data
        })
    
    @workflow.query
    def get_workflow_state(self) -> str:
        """Query current workflow state"""
        return self._workflow_state
    
    @workflow.query
    def get_current_step(self) -> Optional[str]:
        """Query current step"""
        return self._current_step
    
    @workflow.query
    def get_execution_log(self) -> List[Dict[str, Any]]:
        """Query workflow execution log"""
        return self._execution_log
    
    @workflow.query
    def get_execution_context(self) -> Dict[str, Any]:
        """Query current execution context"""
        return self._execution_context
    
    @workflow.signal
    def manual_task_completed(self, task_id: str, result: Dict[str, Any]) -> None:
        """Signal that a manual task has been completed"""
        # Update execution context with manual task result
        self._execution_context[f"manual_task_{task_id}"] = result
        workflow.logger.info(f"Manual task {task_id} completed")
    
    @workflow.signal
    def cancel_workflow(self) -> None:
        """Signal to cancel workflow"""
        self._workflow_state = "CANCELLED"
        workflow.logger.info("Workflow cancellation requested")