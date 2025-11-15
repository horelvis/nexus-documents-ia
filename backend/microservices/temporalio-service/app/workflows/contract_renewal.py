"""Contract Renewal Workflow Definition"""
from datetime import timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activities
from app.activities import (
    emma_ai_activities,
    document_activities,
    notification_activities,
    validation_activities
)


@dataclass
class ContractRenewalInput:
    """Input data for contract renewal workflow"""
    contract_id: str
    tenant_id: str
    user_id: str
    employee_name: str
    contract_type: str
    expiration_date: str
    position: str
    performance_rating: Optional[str] = None
    current_salary: Optional[str] = None
    force_regenerate: bool = False


@dataclass
class ContractRenewalResult:
    """Result of contract renewal workflow"""
    workflow_id: str
    contract_id: str
    final_decision: str  # "RENEW" or "TERMINATE"
    recommendation_confidence: float
    generated_documents: list[str]
    notifications_sent: list[str]
    execution_summary: Dict[str, Any]
    completed_at: str


@workflow.defn
class ContractRenewalWorkflow:
    """
    Durable workflow for contract renewal process
    
    This workflow handles the complete contract renewal decision process:
    1. Analyze employee performance with Emma AI
    2. Evaluate operational need  
    3. Make renewal recommendation
    4. Generate appropriate documents
    5. Send notifications to stakeholders
    6. Handle legal compliance validation
    """
    
    def __init__(self) -> None:
        self._execution_log: list[Dict[str, Any]] = []
        self._workflow_state = "INITIALIZING"
    
    @workflow.run
    async def run(self, input_data: ContractRenewalInput) -> ContractRenewalResult:
        """Main workflow execution"""
        
        workflow_id = workflow.info().workflow_id
        # Upsert search attributes for tenant and type
        try:
            workflow.upsert_search_attributes({
                "TenantId": input_data.tenant_id,
                "WorkflowType": "contract_renewal",
                "ContractId": input_data.contract_id,
            })
        except Exception:
            pass
        self._log_step("workflow_started", {"workflow_id": workflow_id})
        
        try:
            # Step 1: Analyze Employee Performance
            self._workflow_state = "ANALYZING_PERFORMANCE"
            performance_analysis = await workflow.execute_activity(
                emma_ai_activities.analyze_employee_performance,
                args=[{
                    "contract_id": input_data.contract_id,
                    "tenant_id": input_data.tenant_id,
                    "employee_name": input_data.employee_name,
                    "performance_rating": input_data.performance_rating,
                    "position": input_data.position
                }],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=60),
                    maximum_attempts=3
                )
            )
            self._log_step("performance_analyzed", performance_analysis)
            
            # Step 2: Evaluate Operational Need
            self._workflow_state = "EVALUATING_OPERATIONAL_NEED"
            operational_evaluation = await workflow.execute_activity(
                emma_ai_activities.evaluate_operational_need,
                args=[{
                    "contract_id": input_data.contract_id,
                    "tenant_id": input_data.tenant_id,
                    "position": input_data.position,
                    "contract_type": input_data.contract_type,
                    "expiration_date": input_data.expiration_date
                }],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            self._log_step("operational_need_evaluated", operational_evaluation)
            
            # Step 3: Generate Renewal Recommendation 
            self._workflow_state = "GENERATING_RECOMMENDATION"
            recommendation = await workflow.execute_activity(
                emma_ai_activities.generate_contract_recommendation,
                args=[{
                    "contract_id": input_data.contract_id,
                    "tenant_id": input_data.tenant_id,
                    "performance_analysis": performance_analysis,
                    "operational_evaluation": operational_evaluation,
                    "contract_data": {
                        "employee_name": input_data.employee_name,
                        "contract_type": input_data.contract_type,
                        "position": input_data.position,
                        "current_salary": input_data.current_salary
                    }
                }],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            self._log_step("recommendation_generated", recommendation)
            
            # Step 4: Validate Legal Compliance
            self._workflow_state = "VALIDATING_COMPLIANCE"
            compliance_validation = await workflow.execute_activity(
                validation_activities.validate_legal_compliance,
                args=[{
                    "contract_id": input_data.contract_id,
                    "tenant_id": input_data.tenant_id,
                    "recommendation": recommendation,
                    "contract_type": input_data.contract_type,
                    "jurisdiction": "ES"  # Spain
                }],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            self._log_step("compliance_validated", compliance_validation)
            
            # Step 5: Generate Documents Based on Decision
            self._workflow_state = "GENERATING_DOCUMENTS"
            generated_documents = []
            
            final_decision = recommendation.get("decision", "TERMINATE")
            
            if final_decision == "RENEW":
                # Generate renewal contract
                renewal_doc = await workflow.execute_activity(
                    document_activities.generate_contract_document,
                    args=[{
                        "contract_id": input_data.contract_id,
                        "tenant_id": input_data.tenant_id,
                        "document_type": "renewal_contract",
                        "contract_data": {
                            "employee_name": input_data.employee_name,
                            "position": input_data.position,
                            "contract_type": input_data.contract_type,
                            "recommended_salary": recommendation.get("recommended_salary"),
                            "recommended_duration": recommendation.get("recommended_duration")
                        }
                    }],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=RetryPolicy(maximum_attempts=2)
                )
                generated_documents.append(renewal_doc.get("document_id"))
                
            else:
                # Generate termination documents  
                termination_docs = await workflow.execute_activity(
                    document_activities.prepare_termination_documents,
                    args=[{
                        "contract_id": input_data.contract_id,
                        "tenant_id": input_data.tenant_id,
                        "employee_name": input_data.employee_name,
                        "position": input_data.position,
                        "reason": recommendation.get("termination_reason")
                    }],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=RetryPolicy(maximum_attempts=2)
                )
                generated_documents.extend(termination_docs.get("document_ids", []))
                
            self._log_step("documents_generated", {"documents": generated_documents})
            
            # Step 6: Send Notifications
            self._workflow_state = "SENDING_NOTIFICATIONS"
            notifications_sent = await workflow.execute_activity(
                notification_activities.notify_stakeholders,
                args=[{
                    "contract_id": input_data.contract_id,
                    "tenant_id": input_data.tenant_id,
                    "user_id": input_data.user_id,
                    "decision": final_decision,
                    "employee_name": input_data.employee_name,
                    "documents": generated_documents,
                    "recommendation": recommendation
                }],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            self._log_step("notifications_sent", notifications_sent)
            
            # Step 7: Final Workflow Completion
            self._workflow_state = "COMPLETED"
            completion_time = workflow.now().isoformat()
            
            self._log_step("workflow_completed", {
                "final_decision": final_decision,
                "completion_time": completion_time
            })
            
            return ContractRenewalResult(
                workflow_id=workflow_id,
                contract_id=input_data.contract_id,
                final_decision=final_decision,
                recommendation_confidence=recommendation.get("confidence", 0.0),
                generated_documents=generated_documents,
                notifications_sent=notifications_sent.get("sent_to", []),
                execution_summary={
                    "performance_analysis": performance_analysis,
                    "operational_evaluation": operational_evaluation,
                    "recommendation": recommendation,
                    "compliance_validation": compliance_validation,
                    "execution_log": self._execution_log
                },
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
                        "message": f"Contract renewal workflow failed for {input_data.employee_name}: {str(e)}",
                        "contract_id": input_data.contract_id
                    }],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=1)
                )
            except:
                pass  # Best effort notification
            
            raise
    
    def _log_step(self, step_name: str, data: Any) -> None:
        """Log workflow execution step"""
        self._execution_log.append({
            "step": step_name,
            "timestamp": workflow.now().isoformat(),
            "state": self._workflow_state,
            "data": data
        })
    
    @workflow.query
    def get_workflow_state(self) -> str:
        """Query current workflow state"""
        return self._workflow_state
    
    @workflow.query
    def get_execution_log(self) -> list[Dict[str, Any]]:
        """Query workflow execution log"""
        return self._execution_log
    
    @workflow.signal
    def cancel_workflow(self) -> None:
        """Signal to cancel workflow"""
        self._workflow_state = "CANCELLED"
        workflow.logger.info("Workflow cancellation requested")
        # Note: Actual cancellation logic would be implemented here
