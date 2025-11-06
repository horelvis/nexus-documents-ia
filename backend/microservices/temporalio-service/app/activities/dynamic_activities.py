"""
Dynamic Activities - Configurable activities for template-based workflows
"""
from typing import Dict, Any, List
import logging
from datetime import datetime
import httpx

from temporalio import activity
from app.core.config import settings

logger = logging.getLogger(__name__)


@activity.defn
async def execute_generic_activity(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a generic activity based on configuration
    
    Args:
        activity_data: Activity configuration and context
        
    Returns:
        Activity execution result
    """
    activity_type = activity_data.get("activity_type", "generic")
    
    activity.logger.info(f"Executing generic activity: {activity_type}")
    
    try:
        # Route to specific activity handlers
        if activity_type == "data_collection":
            return await _handle_data_collection(activity_data)
        elif activity_type == "validation":
            return await _handle_validation(activity_data)
        elif activity_type == "calculation":
            return await _handle_calculation(activity_data)
        elif activity_type == "integration":
            return await _handle_external_integration(activity_data)
        else:
            # Default generic handling
            return {
                "success": True,
                "activity_type": activity_type,
                "result": f"Generic activity {activity_type} executed",
                "execution_time": datetime.utcnow().isoformat(),
                "context_updates": {
                    f"{activity_type}_completed": True,
                    f"{activity_type}_timestamp": datetime.utcnow().isoformat()
                }
            }
            
    except Exception as e:
        activity.logger.error(f"Error in generic activity {activity_type}: {e}")
        return {
            "success": False,
            "error": str(e),
            "activity_type": activity_type
        }


@activity.defn
async def create_manual_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a manual task for human intervention
    
    Args:
        task_data: Task configuration and assignment information
        
    Returns:
        Task creation result
    """
    step_id = task_data.get("step_id")
    assignee_role = task_data.get("assignee_role")
    instructions = task_data.get("instructions", "")
    
    activity.logger.info(f"Creating manual task for step {step_id}, assignee: {assignee_role}")
    
    try:
        # Generate task ID
        task_id = f"task_{step_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # In a real implementation, this would:
        # 1. Create task record in database
        # 2. Assign to appropriate user/role
        # 3. Send notifications
        # 4. Set up task tracking
        
        # Simulate task creation
        task_info = {
            "task_id": task_id,
            "step_id": step_id,
            "assignee_role": assignee_role,
            "instructions": instructions,
            "status": "assigned",
            "created_at": datetime.utcnow().isoformat(),
            "priority": task_data.get("priority", "normal"),
            "estimated_duration": task_data.get("estimated_duration", "Unknown")
        }
        
        # Send notification to assignee
        await _notify_task_assignee(task_info, task_data)
        
        return {
            "success": True,
            "task_id": task_id,
            "task_info": task_info,
            "message": f"Manual task created and assigned to {assignee_role}"
        }
        
    except Exception as e:
        activity.logger.error(f"Error creating manual task: {e}")
        return {
            "success": False,
            "error": str(e),
            "step_id": step_id
        }


@activity.defn
async def evaluate_decision_conditions(decision_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate decision conditions to determine workflow path
    
    Args:
        decision_data: Decision conditions and context
        
    Returns:
        Decision evaluation result
    """
    conditions = decision_data.get("conditions", {})
    context = decision_data.get("user_input", {})
    
    activity.logger.info("Evaluating decision conditions")
    
    try:
        decision_result = "continue"  # Default
        evaluation_details = {}
        
        # Evaluate each condition
        for condition_name, condition_def in conditions.items():
            condition_type = condition_def.get("type", "simple")
            
            if condition_type == "field_value":
                field_name = condition_def.get("field")
                expected_value = condition_def.get("value")
                actual_value = context.get(field_name)
                
                evaluation_details[condition_name] = {
                    "expected": expected_value,
                    "actual": actual_value,
                    "matches": actual_value == expected_value
                }
                
            elif condition_type == "field_range":
                field_name = condition_def.get("field")
                min_value = condition_def.get("min")
                max_value = condition_def.get("max")
                actual_value = context.get(field_name)
                
                try:
                    actual_num = float(actual_value) if actual_value else 0
                    in_range = min_value <= actual_num <= max_value
                    
                    evaluation_details[condition_name] = {
                        "range": f"{min_value}-{max_value}",
                        "actual": actual_value,
                        "in_range": in_range
                    }
                except (ValueError, TypeError):
                    evaluation_details[condition_name] = {
                        "error": "Invalid numeric value",
                        "actual": actual_value
                    }
                    
            elif condition_type == "urgency_based":
                urgency = context.get("urgency_level", "media")
                high_priority = urgency == "alta"
                
                evaluation_details[condition_name] = {
                    "urgency": urgency,
                    "high_priority": high_priority
                }
                
                if high_priority:
                    decision_result = "escalate_to_senior"
        
        # Simple decision logic - can be made more sophisticated
        if context.get("consultation_type") == "discrimination":
            decision_result = "escalate_to_senior"
        elif context.get("urgency_level") == "alta":
            decision_result = "priority_handling"
        elif context.get("budget_range") in [">15000"]:
            decision_result = "approval_required"
        
        return {
            "success": True,
            "decision": decision_result,
            "evaluation_details": evaluation_details,
            "context_updates": {
                "decision_made": decision_result,
                "decision_timestamp": datetime.utcnow().isoformat()
            }
        }
        
    except Exception as e:
        activity.logger.error(f"Error evaluating decision conditions: {e}")
        return {
            "success": False,
            "error": str(e),
            "decision": "error"
        }


@activity.defn
async def create_approval_request(approval_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an approval request
    
    Args:
        approval_data: Approval request configuration
        
    Returns:
        Approval request creation result
    """
    step_config = approval_data.get("step_config", {})
    approver_role = step_config.get("assignee_role", "manager")
    
    activity.logger.info(f"Creating approval request for {approver_role}")
    
    try:
        approval_id = f"approval_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        # Create approval request
        approval_info = {
            "approval_id": approval_id,
            "approver_role": approver_role,
            "request_type": step_config.get("step_name", "General Approval"),
            "context": approval_data.get("user_input", {}),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "urgency": approval_data.get("user_input", {}).get("urgency_level", "media")
        }
        
        # Send notification to approver
        await _notify_approver(approval_info, approval_data)
        
        return {
            "success": True,
            "approval_id": approval_id,
            "approval_info": approval_info,
            "message": f"Approval request sent to {approver_role}"
        }
        
    except Exception as e:
        activity.logger.error(f"Error creating approval request: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@activity.defn
async def create_case_documentation(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create case documentation and archive
    
    Args:
        doc_data: Documentation configuration and case data
        
    Returns:
        Documentation creation result
    """
    case_info = doc_data.get("user_input", {})
    execution_context = doc_data.get("execution_context", {})
    
    activity.logger.info("Creating case documentation")
    
    try:
        # Generate case summary
        case_summary = {
            "case_id": execution_context.get("workflow_id"),
            "client_name": case_info.get("client_name"),
            "consultation_type": case_info.get("consultation_type"),
            "case_description": case_info.get("case_description"),
            "urgency_level": case_info.get("urgency_level"),
            "created_at": datetime.utcnow().isoformat(),
            "status": "documented"
        }
        
        # Generate documentation package
        documentation = {
            "case_summary": case_summary,
            "client_information": {
                "name": case_info.get("client_name"),
                "email": case_info.get("client_email"),
                "phone": case_info.get("client_phone"),
                "company": case_info.get("company_name")
            },
            "case_details": {
                "type": case_info.get("consultation_type"),
                "description": case_info.get("case_description"),
                "affected_employees": case_info.get("affected_employees"),
                "contract_type": case_info.get("contract_type"),
                "preferred_resolution": case_info.get("preferred_resolution"),
                "budget_range": case_info.get("budget_range"),
                "deadline": case_info.get("deadline")
            },
            "processing_info": {
                "workflow_id": execution_context.get("workflow_id"),
                "template_id": execution_context.get("template_id"),
                "processed_by": execution_context.get("user_id"),
                "processing_date": datetime.utcnow().isoformat()
            }
        }
        
        # Generate document ID
        doc_id = f"case_doc_{execution_context.get('workflow_id', 'unknown')}_{datetime.utcnow().strftime('%Y%m%d')}"
        
        # In a real implementation, this would store the documentation
        # in the document management system
        
        return {
            "success": True,
            "document_id": doc_id,
            "documentation": documentation,
            "case_summary": case_summary,
            "archived_at": datetime.utcnow().isoformat(),
            "context_updates": {
                "documentation_created": True,
                "document_id": doc_id,
                "case_archived": True
            }
        }
        
    except Exception as e:
        activity.logger.error(f"Error creating case documentation: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Helper functions
async def _handle_data_collection(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle data collection activity"""
    collection_config = activity_data.get("collection_config", {})
    
    # Simulate data collection
    collected_data = {
        "collection_type": collection_config.get("type", "form_data"),
        "data_sources": collection_config.get("sources", ["user_input"]),
        "collected_at": datetime.utcnow().isoformat(),
        "data_quality": "verified"
    }
    
    return {
        "success": True,
        "activity_type": "data_collection",
        "collected_data": collected_data,
        "context_updates": {
            "data_collection_completed": True,
            "collected_data": collected_data
        }
    }


async def _handle_validation(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle validation activity"""
    validation_rules = activity_data.get("validation_rules", {})
    
    # Simulate validation
    validation_result = {
        "validation_type": "business_rules",
        "rules_checked": len(validation_rules),
        "validation_passed": True,
        "validated_at": datetime.utcnow().isoformat()
    }
    
    return {
        "success": True,
        "activity_type": "validation",
        "validation_result": validation_result,
        "context_updates": {
            "validation_completed": True,
            "validation_passed": True
        }
    }


async def _handle_calculation(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle calculation activity"""
    calculation_config = activity_data.get("calculation_config", {})
    
    # Simulate calculation
    calculation_result = {
        "calculation_type": calculation_config.get("type", "generic"),
        "result_value": 100.0,  # Simulated result
        "calculated_at": datetime.utcnow().isoformat()
    }
    
    return {
        "success": True,
        "activity_type": "calculation",
        "calculation_result": calculation_result,
        "context_updates": {
            "calculation_completed": True,
            "calculated_value": calculation_result["result_value"]
        }
    }


async def _handle_external_integration(activity_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle external integration activity"""
    integration_config = activity_data.get("integration_config", {})
    
    # Simulate external API call
    integration_result = {
        "integration_type": integration_config.get("type", "api_call"),
        "endpoint": integration_config.get("endpoint", "unknown"),
        "response_status": "success",
        "integrated_at": datetime.utcnow().isoformat()
    }
    
    return {
        "success": True,
        "activity_type": "integration",
        "integration_result": integration_result,
        "context_updates": {
            "integration_completed": True,
            "external_data_received": True
        }
    }


async def _notify_task_assignee(task_info: Dict[str, Any], task_data: Dict[str, Any]) -> None:
    """Send notification to task assignee"""
    # In a real implementation, this would send actual notifications
    logger.info(f"Notification sent to {task_info['assignee_role']} for task {task_info['task_id']}")


async def _notify_approver(approval_info: Dict[str, Any], approval_data: Dict[str, Any]) -> None:
    """Send notification to approver"""
    # In a real implementation, this would send actual notifications  
    logger.info(f"Approval request sent to {approval_info['approver_role']} for approval {approval_info['approval_id']}")