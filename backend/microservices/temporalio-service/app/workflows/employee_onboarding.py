"""Employee Onboarding Workflow Definition"""
from datetime import timedelta
from typing import Dict, Any, List
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

from app.activities import (
    document_activities,
    notification_activities,
    validation_activities
)


@dataclass
class EmployeeOnboardingInput:
    """Input data for employee onboarding workflow"""
    employee_id: str
    tenant_id: str
    hr_user_id: str
    employee_name: str
    position: str
    department: str
    start_date: str
    manager_id: str
    contract_type: str
    salary: str
    work_location: str
    equipment_needs: List[str] = None


@dataclass
class EmployeeOnboardingResult:
    """Result of employee onboarding workflow"""
    workflow_id: str
    employee_id: str
    onboarding_status: str  # "COMPLETED", "FAILED", "PENDING"
    completed_tasks: List[str]
    pending_tasks: List[str]
    generated_documents: List[str]
    assigned_equipment: List[str]
    access_permissions: Dict[str, str]
    completion_percentage: int
    completed_at: str


@workflow.defn
class EmployeeOnboardingWorkflow:
    """
    Comprehensive employee onboarding workflow
    
    Handles the complete employee onboarding process:
    1. Generate employment contract and welcome documents
    2. Setup system accounts and permissions
    3. Order and assign equipment
    4. Schedule orientation sessions
    5. Create training plan
    6. Setup workspace and tools
    7. Send welcome notifications
    8. Track onboarding progress
    """
    
    def __init__(self) -> None:
        self._execution_log: List[Dict[str, Any]] = []
        self._workflow_state = "INITIALIZING"
        self._completed_tasks: List[str] = []
        self._pending_tasks: List[str] = []
        self._equipment_assigned: List[str] = []
        self._documents_generated: List[str] = []
    
    @workflow.run
    async def run(self, input_data: EmployeeOnboardingInput) -> EmployeeOnboardingResult:
        """Main onboarding workflow execution"""
        
        workflow_id = workflow.info().workflow_id
        # Upsert search attributes for tenant isolation and type
        try:
            workflow.upsert_search_attributes({
                "TenantId": input_data.tenant_id,
                "WorkflowType": "employee_onboarding",
                "EmployeeId": input_data.employee_id,
            })
        except Exception:
            pass
        self._log_step("onboarding_started", {"workflow_id": workflow_id})
        
        try:
            # Step 1: Generate Employment Contract
            self._workflow_state = "GENERATING_CONTRACT"
            contract_result = await workflow.execute_activity(
                document_activities.generate_contract_document,
                args=[{
                    "contract_id": f"contract_{input_data.employee_id}",
                    "tenant_id": input_data.tenant_id,
                    "document_type": "employment_contract",
                    "contract_data": {
                        "employee_name": input_data.employee_name,
                        "position": input_data.position,
                        "department": input_data.department,
                        "start_date": input_data.start_date,
                        "contract_type": input_data.contract_type,
                        "salary": input_data.salary,
                        "work_location": input_data.work_location,
                        "manager_id": input_data.manager_id
                    }
                }],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3)
            )
            self._documents_generated.append(contract_result.get("document_id"))
            self._completed_tasks.append("employment_contract_generated")
            self._log_step("contract_generated", contract_result)
            
            # Step 2: Generate Welcome Package
            self._workflow_state = "GENERATING_WELCOME_PACKAGE"
            welcome_package = await workflow.execute_activity(
                document_activities.generate_contract_document,
                args=[{
                    "contract_id": f"welcome_{input_data.employee_id}",
                    "tenant_id": input_data.tenant_id,
                    "document_type": "welcome_package",
                    "contract_data": {
                        "employee_name": input_data.employee_name,
                        "position": input_data.position,
                        "department": input_data.department,
                        "start_date": input_data.start_date,
                        "manager_id": input_data.manager_id
                    }
                }],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            self._documents_generated.append(welcome_package.get("document_id"))
            self._completed_tasks.append("welcome_package_generated")
            self._log_step("welcome_package_generated", welcome_package)
            
            # Step 3: Validate Compliance Requirements
            self._workflow_state = "VALIDATING_COMPLIANCE"
            compliance_check = await workflow.execute_activity(
                validation_activities.validate_legal_compliance,
                args=[{
                    "contract_id": f"contract_{input_data.employee_id}",
                    "tenant_id": input_data.tenant_id,
                    "recommendation": {
                        "decision": "HIRE",
                        "contract_type": input_data.contract_type,
                        "position": input_data.position
                    },
                    "contract_type": input_data.contract_type,
                    "jurisdiction": "ES"
                }],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            if compliance_check.get("compliant", False):
                self._completed_tasks.append("compliance_validated")
            else:
                self._pending_tasks.append("compliance_issues_to_resolve")
                
            self._log_step("compliance_validated", compliance_check)
            
            # Step 4: Setup System Access (parallel activities)
            self._workflow_state = "SETTING_UP_ACCESS"
            
            # Simulate multiple parallel setup activities
            setup_activities = []
            
            # Email account setup
            setup_activities.append(
                workflow.execute_activity(
                    self._setup_email_account,
                    args=[input_data.employee_id, input_data.employee_name, input_data.tenant_id],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=2)
                )
            )
            
            # System permissions setup  
            setup_activities.append(
                workflow.execute_activity(
                    self._setup_system_permissions,
                    args=[input_data.employee_id, input_data.position, input_data.department, input_data.tenant_id],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=RetryPolicy(maximum_attempts=2)
                )
            )
            
            # Equipment ordering (if needed)
            if input_data.equipment_needs:
                setup_activities.append(
                    workflow.execute_activity(
                        self._order_equipment,
                        args=[input_data.employee_id, input_data.equipment_needs, input_data.tenant_id],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=RetryPolicy(maximum_attempts=2)
                    )
                )
            
            # Wait for all setup activities to complete
            setup_results = await workflow.gather(*setup_activities)
            
            access_permissions = {}
            for result in setup_results:
                if result.get("type") == "email":
                    access_permissions["email"] = result.get("email_address")
                    self._completed_tasks.append("email_account_created")
                elif result.get("type") == "permissions":
                    access_permissions["systems"] = result.get("granted_permissions", [])
                    self._completed_tasks.append("system_permissions_granted")
                elif result.get("type") == "equipment":
                    self._equipment_assigned.extend(result.get("equipment_list", []))
                    self._completed_tasks.append("equipment_ordered")
            
            self._log_step("access_setup_completed", {"permissions": access_permissions})
            
            # Step 5: Schedule Orientation
            self._workflow_state = "SCHEDULING_ORIENTATION"
            orientation_result = await workflow.execute_activity(
                self._schedule_orientation,
                args=[input_data.employee_id, input_data.start_date, input_data.manager_id, input_data.tenant_id],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            if orientation_result.get("scheduled"):
                self._completed_tasks.append("orientation_scheduled")
            else:
                self._pending_tasks.append("orientation_scheduling_failed")
                
            self._log_step("orientation_scheduled", orientation_result)
            
            # Step 6: Send Welcome Notifications
            self._workflow_state = "SENDING_NOTIFICATIONS"
            
            # Notify HR
            hr_notification = await workflow.execute_activity(
                notification_activities.send_system_notification,
                args=[{
                    "tenant_id": input_data.tenant_id,
                    "user_id": input_data.hr_user_id,
                    "notification_type": "onboarding_progress",
                    "message": f"Onboarding initiated for {input_data.employee_name}. Contract generated and access setup in progress.",
                    "employee_id": input_data.employee_id
                }],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            # Notify Manager
            manager_notification = await workflow.execute_activity(
                notification_activities.send_system_notification,
                args=[{
                    "tenant_id": input_data.tenant_id,
                    "user_id": input_data.manager_id,
                    "notification_type": "new_team_member",
                    "message": f"New team member {input_data.employee_name} starts on {input_data.start_date}. Please prepare for orientation.",
                    "employee_id": input_data.employee_id
                }],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=2)
            )
            
            self._completed_tasks.append("notifications_sent")
            self._log_step("notifications_sent", {
                "hr_notified": hr_notification.get("success", False),
                "manager_notified": manager_notification.get("success", False)
            })
            
            # Step 7: Final Status Calculation
            self._workflow_state = "COMPLETED"
            total_tasks = len(self._completed_tasks) + len(self._pending_tasks)
            completion_percentage = int((len(self._completed_tasks) / max(total_tasks, 1)) * 100)
            
            onboarding_status = "COMPLETED" if completion_percentage >= 90 else "PENDING"
            completion_time = workflow.now().isoformat()
            
            self._log_step("onboarding_completed", {
                "status": onboarding_status,
                "completion_percentage": completion_percentage,
                "completed_tasks": len(self._completed_tasks),
                "pending_tasks": len(self._pending_tasks)
            })
            
            return EmployeeOnboardingResult(
                workflow_id=workflow_id,
                employee_id=input_data.employee_id,
                onboarding_status=onboarding_status,
                completed_tasks=self._completed_tasks,
                pending_tasks=self._pending_tasks,
                generated_documents=self._documents_generated,
                assigned_equipment=self._equipment_assigned,
                access_permissions=access_permissions,
                completion_percentage=completion_percentage,
                completed_at=completion_time
            )
            
        except Exception as e:
            self._workflow_state = "FAILED"
            self._log_step("onboarding_failed", {"error": str(e)})
            
            # Send failure notification
            try:
                await workflow.execute_activity(
                    notification_activities.send_system_notification,
                    args=[{
                        "tenant_id": input_data.tenant_id,
                        "user_id": input_data.hr_user_id,
                        "notification_type": "onboarding_failed",
                        "message": f"Onboarding workflow failed for {input_data.employee_name}: {str(e)}",
                        "employee_id": input_data.employee_id
                    }],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=1)
                )
            except:
                pass
            
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
    def get_onboarding_progress(self) -> Dict[str, Any]:
        """Query current onboarding progress"""
        total_tasks = len(self._completed_tasks) + len(self._pending_tasks)
        completion_percentage = int((len(self._completed_tasks) / max(total_tasks, 1)) * 100)
        
        return {
            "state": self._workflow_state,
            "completion_percentage": completion_percentage,
            "completed_tasks": self._completed_tasks,
            "pending_tasks": self._pending_tasks,
            "documents_generated": self._documents_generated,
            "equipment_assigned": self._equipment_assigned
        }
    
    # Activity stubs (these would be implemented as actual activities)
    async def _setup_email_account(self, employee_id: str, employee_name: str, tenant_id: str) -> Dict[str, Any]:
        """Activity stub for email account setup"""
        return {
            "type": "email",
            "employee_id": employee_id,
            "email_address": f"{employee_name.lower().replace(' ', '.')}@company.com",
            "success": True
        }
    
    async def _setup_system_permissions(self, employee_id: str, position: str, department: str, tenant_id: str) -> Dict[str, Any]:
        """Activity stub for system permissions setup"""
        return {
            "type": "permissions",
            "employee_id": employee_id,
            "granted_permissions": ["nexus_docs_access", "department_files", "email_system"],
            "success": True
        }
    
    async def _order_equipment(self, employee_id: str, equipment_needs: List[str], tenant_id: str) -> Dict[str, Any]:
        """Activity stub for equipment ordering"""
        return {
            "type": "equipment",
            "employee_id": employee_id,
            "equipment_list": equipment_needs,
            "order_id": f"ORDER_{employee_id}",
            "success": True
        }
    
    async def _schedule_orientation(self, employee_id: str, start_date: str, manager_id: str, tenant_id: str) -> Dict[str, Any]:
        """Activity stub for orientation scheduling"""
        return {
            "employee_id": employee_id,
            "orientation_date": start_date,
            "manager_id": manager_id,
            "scheduled": True,
            "session_id": f"ORIENTATION_{employee_id}"
        }
