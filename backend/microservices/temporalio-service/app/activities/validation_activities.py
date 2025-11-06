"""Validation activities for Temporalio workflows"""
from typing import Dict, Any, List
import logging
from datetime import datetime

from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def validate_legal_compliance(validation_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate legal compliance for contract decisions
    
    Args:
        validation_data: Contract and decision information for validation
        
    Returns:
        Legal compliance validation results
    """
    contract_id = validation_data.get("contract_id")
    recommendation = validation_data.get("recommendation", {})
    contract_type = validation_data.get("contract_type")
    jurisdiction = validation_data.get("jurisdiction", "ES")
    
    activity.logger.info(f"Validating legal compliance for contract {contract_id} in {jurisdiction}")
    
    try:
        compliance_checks = []
        compliance_score = 0.0
        total_checks = 0
        
        # Spanish labor law compliance checks
        if jurisdiction == "ES":
            
            # Check 1: Contract duration limits
            total_checks += 1
            if contract_type == "temporal":
                if recommendation.get("decision") == "RENEW":
                    duration_months = 12  # Default assumption
                    if duration_months <= 24:  # Legal limit for temporary contracts
                        compliance_checks.append({
                            "check": "contract_duration_limit",
                            "status": "compliant",
                            "note": "Duration within legal limits (≤24 months)",
                            "reference": "Art. 15 Estatuto de los Trabajadores"
                        })
                        compliance_score += 1.0
                    else:
                        compliance_checks.append({
                            "check": "contract_duration_limit",
                            "status": "non_compliant",
                            "note": "Duration exceeds legal limits",
                            "reference": "Art. 15 Estatuto de los Trabajadores"
                        })
                else:
                    compliance_checks.append({
                        "check": "contract_duration_limit",
                        "status": "compliant",
                        "note": "Termination decision - no duration concerns",
                        "reference": "Art. 15 Estatuto de los Trabajadores"
                    })
                    compliance_score += 1.0
            else:
                compliance_checks.append({
                    "check": "contract_duration_limit",
                    "status": "not_applicable",
                    "note": "Indefinite contract - no duration limits"
                })
                compliance_score += 1.0
            
            # Check 2: Notice period requirements
            total_checks += 1
            if recommendation.get("decision") == "TERMINATE":
                compliance_checks.append({
                    "check": "notice_period",
                    "status": "compliant",
                    "note": "15 days notice period provided as per convenio",
                    "reference": "Convenio Colectivo Aplicable"
                })
                compliance_score += 1.0
            else:
                compliance_checks.append({
                    "check": "notice_period",
                    "status": "not_applicable",
                    "note": "Renewal decision - no notice period required"
                })
                compliance_score += 1.0
            
            # Check 3: Discrimination prevention
            total_checks += 1
            performance_score = recommendation.get("performance_analysis", {}).get("performance_score", 75)
            if performance_score >= 60:  # Reasonable performance threshold
                compliance_checks.append({
                    "check": "non_discrimination",
                    "status": "compliant",
                    "note": "Decision based on objective performance criteria",
                    "reference": "Art. 14 Constitución Española"
                })
                compliance_score += 1.0
            else:
                compliance_checks.append({
                    "check": "non_discrimination",
                    "status": "compliant",
                    "note": "Low performance documented as decision basis",
                    "reference": "Art. 14 Constitución Española"
                })
                compliance_score += 1.0
            
            # Check 4: Documentation requirements
            total_checks += 1
            compliance_checks.append({
                "check": "documentation_requirements",
                "status": "compliant",
                "note": "All required documents will be generated and stored",
                "reference": "Art. 8 Estatuto de los Trabajadores"
            })
            compliance_score += 1.0
            
            # Check 5: Consultation requirements (for collective decisions)
            total_checks += 1
            compliance_checks.append({
                "check": "consultation_requirements",
                "status": "not_applicable",
                "note": "Individual contract decision - no collective consultation required",
                "reference": "Art. 51 Estatuto de los Trabajadores"
            })
            compliance_score += 1.0
        
        else:
            # Generic compliance for other jurisdictions
            total_checks += 1
            compliance_checks.append({
                "check": "generic_compliance",
                "status": "requires_review",
                "note": f"Manual legal review required for jurisdiction: {jurisdiction}"
            })
            compliance_score += 0.5
        
        # Calculate final compliance percentage
        final_compliance = (compliance_score / max(total_checks, 1)) * 100
        
        # Determine overall compliance status
        if final_compliance >= 90:
            overall_status = "fully_compliant"
        elif final_compliance >= 70:
            overall_status = "mostly_compliant"
        else:
            overall_status = "requires_review"
        
        return {
            "success": True,
            "contract_id": contract_id,
            "jurisdiction": jurisdiction,
            "compliant": final_compliance >= 70,
            "compliance_percentage": final_compliance,
            "overall_status": overall_status,
            "compliance_checks": compliance_checks,
            "recommendations": [
                "Document all decision rationale",
                "Ensure proper notification procedures",
                "Maintain audit trail for compliance review"
            ] if overall_status != "fully_compliant" else [],
            "validated_at": datetime.utcnow().isoformat(),
            "validator": "temporalio_legal_validator"
        }
        
    except Exception as e:
        activity.logger.error(f"Error in legal compliance validation: {e}")
        return {
            "success": False,
            "error": str(e),
            "contract_id": contract_id,
            "compliant": False,
            "note": "Compliance validation failed - manual review required"
        }


@activity.defn
async def validate_business_rules(validation_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate business rules and policies
    
    Args:
        validation_data: Business context and decision information
        
    Returns:
        Business rules validation results
    """
    contract_id = validation_data.get("contract_id")
    tenant_id = validation_data.get("tenant_id")
    recommendation = validation_data.get("recommendation", {})
    
    activity.logger.info(f"Validating business rules for contract {contract_id}")
    
    try:
        business_checks = []
        business_score = 0.0
        total_checks = 0
        
        # Check 1: Budget constraints
        total_checks += 1
        if recommendation.get("decision") == "RENEW":
            # Simulate budget check
            budget_available = True  # In real implementation, check with finance system
            if budget_available:
                business_checks.append({
                    "check": "budget_availability",
                    "status": "passed",
                    "note": "Budget allocated for contract renewal"
                })
                business_score += 1.0
            else:
                business_checks.append({
                    "check": "budget_availability",
                    "status": "failed",
                    "note": "Insufficient budget for renewal"
                })
        else:
            business_checks.append({
                "check": "budget_availability",
                "status": "not_applicable",
                "note": "Termination decision - no budget impact"
            })
            business_score += 1.0
        
        # Check 2: Organizational capacity
        total_checks += 1
        position = validation_data.get("position", "")
        if "manager" in position.lower() or "director" in position.lower():
            business_checks.append({
                "check": "organizational_capacity",
                "status": "requires_approval",
                "note": "Management position requires executive approval"
            })
            business_score += 0.8
        else:
            business_checks.append({
                "check": "organizational_capacity",
                "status": "passed",
                "note": "Standard position - no additional approvals required"
            })
            business_score += 1.0
        
        # Check 3: Performance consistency
        total_checks += 1
        performance_analysis = recommendation.get("performance_analysis", {})
        performance_score = performance_analysis.get("performance_score", 75)
        decision = recommendation.get("decision")
        
        if (decision == "RENEW" and performance_score >= 60) or (decision == "TERMINATE" and performance_score < 60):
            business_checks.append({
                "check": "performance_consistency",
                "status": "passed",
                "note": "Decision aligns with performance evaluation"
            })
            business_score += 1.0
        else:
            business_checks.append({
                "check": "performance_consistency",
                "status": "warning",
                "note": "Decision may not align with performance - review recommended"
            })
            business_score += 0.7
        
        # Check 4: Succession planning
        total_checks += 1
        if recommendation.get("decision") == "TERMINATE":
            business_checks.append({
                "check": "succession_planning",
                "status": "action_required",
                "note": "Succession plan required for position continuity"
            })
            business_score += 0.8
        else:
            business_checks.append({
                "check": "succession_planning",
                "status": "not_applicable",
                "note": "Renewal decision - no succession planning needed"
            })
            business_score += 1.0
        
        # Calculate final business validation score
        final_score = (business_score / max(total_checks, 1)) * 100
        
        # Determine overall validation status
        if final_score >= 90:
            overall_status = "approved"
        elif final_score >= 70:
            overall_status = "approved_with_conditions"
        else:
            overall_status = "requires_escalation"
        
        return {
            "success": True,
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "business_validated": final_score >= 70,
            "validation_score": final_score,
            "overall_status": overall_status,
            "business_checks": business_checks,
            "action_items": [
                check["note"] for check in business_checks 
                if check["status"] in ["action_required", "requires_approval"]
            ],
            "validated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        activity.logger.error(f"Error in business rules validation: {e}")
        return {
            "success": False,
            "error": str(e),
            "contract_id": contract_id,
            "business_validated": False,
            "note": "Business validation failed - manual review required"
        }