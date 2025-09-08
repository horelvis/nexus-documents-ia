"""
Activity Loader - Dynamic loading of activities for Temporalio workers
"""
import logging
from typing import List, Any

logger = logging.getLogger(__name__)


def get_advanced_emma_activities() -> List[Any]:
    """Load advanced Emma AI activities"""
    
    try:
        from app.activities.emma_ai_advanced_activities import (
            analyze_legal_case,
            generate_legal_document,
            emma_case_recommendation
        )
        
        activities = [
            analyze_legal_case,
            generate_legal_document,
            emma_case_recommendation
        ]
        
        logger.info(f"✅ Loaded {len(activities)} advanced Emma AI activities")
        return activities
        
    except ImportError as e:
        logger.error(f"❌ Failed to load advanced Emma AI activities: {e}")
        return []


def get_dynamic_activities() -> List[Any]:
    """Load dynamic workflow activities"""
    
    try:
        from app.activities.dynamic_activities import (
            execute_generic_activity,
            create_manual_task,
            evaluate_decision_conditions,
            create_approval_request,
            create_case_documentation
        )
        
        activities = [
            execute_generic_activity,
            create_manual_task,
            evaluate_decision_conditions,
            create_approval_request,
            create_case_documentation
        ]
        
        logger.info(f"✅ Loaded {len(activities)} dynamic activities")
        return activities
        
    except ImportError as e:
        logger.error(f"❌ Failed to load dynamic activities: {e}")
        return []


def get_ai_agent_activities() -> List[Any]:
    """Load AI agent activities"""
    
    try:
        from app.activities.ai_agent_activities import get_ai_agent_activities
        
        activities = get_ai_agent_activities()
        logger.info(f"✅ Loaded {len(activities)} AI agent activities")
        return activities
        
    except ImportError as e:
        logger.error(f"❌ Failed to load AI agent activities: {e}")
        return []


def get_all_workflow_activities() -> List[Any]:
    """Get all available workflow activities"""
    
    activities = []
    
    # AI Agent Activities (Priority - new intelligent agents)
    activities.extend(get_ai_agent_activities())
    
    # Original Emma AI Activities
    try:
        from app.activities import emma_ai_activities
        activities.extend([
            emma_ai_activities.analyze_employee_performance,
            emma_ai_activities.evaluate_operational_need,
            emma_ai_activities.generate_contract_recommendation,
        ])
        logger.info("✅ Loaded original Emma AI activities")
    except ImportError as e:
        logger.error(f"❌ Failed to load original Emma AI activities: {e}")
    
    # Advanced Emma AI Activities
    activities.extend(get_advanced_emma_activities())
    
    # Document Activities
    try:
        from app.activities import document_activities
        activities.extend([
            document_activities.generate_contract_document,
            document_activities.prepare_termination_documents,
            document_activities.store_document,
        ])
        logger.info("✅ Loaded document activities")
    except ImportError as e:
        logger.error(f"❌ Failed to load document activities: {e}")
    
    # Dynamic Activities
    activities.extend(get_dynamic_activities())
    
    # Validation Activities
    try:
        from app.activities import validation_activities
        activities.extend([
            validation_activities.validate_legal_compliance,
            validation_activities.validate_business_rules,
        ])
        logger.info("✅ Loaded validation activities")
    except ImportError as e:
        logger.error(f"❌ Failed to load validation activities: {e}")
    
    # Notification Activities
    try:
        from app.activities import notification_activities
        activities.extend([
            notification_activities.send_email_notification,
            notification_activities.send_system_notification,
            notification_activities.notify_stakeholders,
        ])
        logger.info("✅ Loaded notification activities")
    except ImportError as e:
        logger.error(f"❌ Failed to load notification activities: {e}")
    
    logger.info(f"🎯 Total activities loaded: {len(activities)}")
    return activities