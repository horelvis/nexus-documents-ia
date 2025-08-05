"""
Compliance Checker API endpoints - Main API
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Dict, Any, List, Optional
import logging
from enum import Enum

from app.api.v1.deps import get_current_user, get_current_active_user, get_client_manager
from app.db.models import User
from app.services.compliance_checker_client import ComplianceCheckerClient
from app.services.client_manager import ClientManager
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class ComplianceFramework(str, Enum):
    """Supported compliance frameworks"""
    GDPR = "gdpr"
    CCPA = "ccpa"
    HIPAA = "hipaa"
    SOX = "sox"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"
    SOC2 = "soc2"
    FERPA = "ferpa"
    GLBA = "glba"
    FCRA = "fcra"
    ADA = "ada"
    COPPA = "coppa"
    CUSTOM = "custom"


class ComplianceCheckType(str, Enum):
    """Types of compliance checks"""
    FULL_AUDIT = "full_audit"
    DATA_PRIVACY = "data_privacy"
    SECURITY_CONTROLS = "security_controls"
    ACCESS_CONTROLS = "access_controls"
    RETENTION_POLICIES = "retention_policies"
    CONSENT_MANAGEMENT = "consent_management"
    BREACH_NOTIFICATION = "breach_notification"
    THIRD_PARTY_SHARING = "third_party_sharing"
    SENSITIVE_DATA = "sensitive_data"
    REGULATORY_SPECIFIC = "regulatory_specific"


class ComplianceCheckRequest(BaseModel):
    """Request for compliance check"""
    document_id: Optional[str] = Field(None, description="ID of stored document")
    content: Optional[str] = Field(None, description="Document content to check")
    frameworks: List[ComplianceFramework] = Field(
        [ComplianceFramework.GDPR],
        description="Compliance frameworks to check against"
    )
    check_type: ComplianceCheckType = Field(
        ComplianceCheckType.FULL_AUDIT,
        description="Type of compliance check"
    )
    industry: Optional[str] = Field(None, description="Industry context")
    jurisdiction: Optional[str] = Field(None, description="Legal jurisdiction")
    custom_policies: Optional[List[str]] = Field(None, description="Custom compliance policies")


class ComplianceCheckResponse(BaseModel):
    """Response from compliance check"""
    document_id: Optional[str]
    check_type: ComplianceCheckType
    frameworks_checked: List[ComplianceFramework]
    compliance_score: float
    is_compliant: bool
    violations: List[Dict[str, Any]]
    sensitive_data: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    summary: str
    risk_assessment: Dict[str, Any]
    metadata: Dict[str, Any]
    processing_time: float


@router.post("/check", response_model=ComplianceCheckResponse)
async def check_compliance(
    request: ComplianceCheckRequest,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Check document compliance against specified frameworks
    
    This comprehensive compliance checker helps ensure your documents meet regulatory requirements:
    
    **Frameworks Supported:**
    - GDPR (General Data Protection Regulation)
    - CCPA (California Consumer Privacy Act)
    - HIPAA (Health Insurance Portability and Accountability Act)
    - SOX (Sarbanes-Oxley Act)
    - PCI DSS (Payment Card Industry Data Security Standard)
    - ISO 27001 (Information Security Management)
    - SOC2 (Service Organization Control 2)
    - And more...
    
    **Check Types:**
    - **full_audit**: Comprehensive compliance review
    - **data_privacy**: Focus on privacy regulations
    - **security_controls**: Verify security measures
    - **sensitive_data**: Scan for PII, PHI, PCI data
    - **consent_management**: Review consent practices
    - And more specialized checks...
    
    **What It Detects:**
    - Regulatory violations and gaps
    - Sensitive data exposure (SSN, credit cards, medical records)
    - Missing security controls
    - Inadequate consent mechanisms
    - Data retention issues
    - Third-party sharing risks
    """
    
    try:
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await client.check_compliance(
            document_id=request.document_id,
            content=request.content,
            frameworks=[f.value for f in request.frameworks],
            check_type=request.check_type.value,
            industry=request.industry,
            jurisdiction=request.jurisdiction,
            custom_policies=request.custom_policies
        )
        
        return ComplianceCheckResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Compliance check failed: {e}")
        raise HTTPException(status_code=500, detail="Compliance check failed")


@router.post("/check-file", response_model=ComplianceCheckResponse)
async def check_file_compliance(
    file: UploadFile = File(...),
    frameworks: str = Form("gdpr"),
    check_type: ComplianceCheckType = Form(ComplianceCheckType.FULL_AUDIT),
    industry: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Check uploaded file for compliance violations
    
    Supported formats:
    - PDF documents
    - Word documents (DOC, DOCX)
    - Excel spreadsheets (XLS, XLSX)
    - CSV files
    - Text files (TXT)
    - JSON/XML data files
    """
    
    try:
        # Read file content
        content = await file.read()
        
        # Parse frameworks
        framework_list = [ComplianceFramework(f.strip()) for f in frameworks.split(",")]
        
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await client.check_file(
            file_content=content,
            filename=file.filename,
            content_type=file.content_type,
            frameworks=[f.value for f in framework_list],
            check_type=check_type.value,
            industry=industry,
            jurisdiction=jurisdiction
        )
        
        return ComplianceCheckResponse(**result)
        
    except Exception as e:
        logger.error(f"File compliance check failed: {e}")
        raise HTTPException(status_code=500, detail="File compliance check failed")


@router.post("/scan-sensitive-data")
async def scan_for_sensitive_data(
    document_ids: List[str],
    deep_scan: bool = False,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Scan multiple documents for sensitive data
    
    Identifies:
    - Personal Identifiable Information (PII)
    - Protected Health Information (PHI)
    - Payment Card Information (PCI)
    - Financial account data
    - Government identifiers
    - Biometric data
    - Credentials and secrets
    """
    
    try:
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.scan_sensitive_data(
            document_ids=document_ids,
            deep_scan=deep_scan
        )
        
    except Exception as e:
        logger.error(f"Sensitive data scan failed: {e}")
        raise HTTPException(status_code=500, detail="Sensitive data scan failed")


@router.post("/data-mapping")
async def create_data_mapping(
    document_ids: List[str],
    deep_scan: bool = False,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Create comprehensive data mapping and classification
    
    Generates:
    - Complete data inventory
    - Data flow mapping
    - Classification by sensitivity
    - Compliance coverage analysis
    - Gap identification
    """
    
    try:
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.create_data_mapping(
            document_ids=document_ids,
            deep_scan=deep_scan
        )
        
    except Exception as e:
        logger.error(f"Data mapping failed: {e}")
        raise HTTPException(status_code=500, detail="Data mapping failed")


@router.post("/generate-report")
async def generate_compliance_report(
    document_ids: List[str],
    frameworks: List[ComplianceFramework],
    include_remediation: bool = True,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Generate comprehensive compliance report
    
    Includes:
    - Executive summary
    - Detailed findings by framework
    - Risk heat map
    - Remediation roadmap
    - Compliance metrics
    """
    
    try:
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.generate_report(
            document_ids=document_ids,
            frameworks=[f.value for f in frameworks],
            include_remediation=include_remediation
        )
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail="Report generation failed")


@router.post("/policies")
async def create_custom_policy(
    name: str,
    description: str,
    rules: List[str],
    frameworks: List[ComplianceFramework],
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Create custom compliance policy
    
    Allows organizations to define their own compliance rules
    beyond standard frameworks.
    """
    
    try:
        client = ComplianceCheckerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.create_custom_policy(
            name=name,
            description=description,
            rules=rules,
            frameworks=[f.value for f in frameworks]
        )
        
    except Exception as e:
        logger.error(f"Policy creation failed: {e}")
        raise HTTPException(status_code=500, detail="Policy creation failed")


@router.get("/frameworks")
async def get_compliance_frameworks():
    """Get available compliance frameworks with descriptions"""
    
    return {
        "frameworks": [
            {
                "code": ComplianceFramework.GDPR.value,
                "name": "General Data Protection Regulation",
                "description": "EU data protection and privacy regulation",
                "categories": ["data_privacy", "consent", "data_rights"],
                "fines": "Up to €20M or 4% of global revenue"
            },
            {
                "code": ComplianceFramework.CCPA.value,
                "name": "California Consumer Privacy Act",
                "description": "California state privacy law",
                "categories": ["data_privacy", "consumer_rights", "data_sale"],
                "fines": "Up to $7,500 per violation"
            },
            {
                "code": ComplianceFramework.HIPAA.value,
                "name": "Health Insurance Portability and Accountability Act",
                "description": "US healthcare data privacy and security",
                "categories": ["healthcare", "phi", "security"],
                "fines": "Up to $50,000 per violation"
            },
            {
                "code": ComplianceFramework.SOX.value,
                "name": "Sarbanes-Oxley Act",
                "description": "US financial reporting and internal controls",
                "categories": ["financial", "internal_controls", "audit"],
                "fines": "Up to $5M and 20 years imprisonment"
            },
            {
                "code": ComplianceFramework.PCI_DSS.value,
                "name": "Payment Card Industry Data Security Standard",
                "description": "Credit card data security requirements",
                "categories": ["payment", "security", "encryption"],
                "fines": "Up to $100,000 per month"
            },
            {
                "code": ComplianceFramework.ISO_27001.value,
                "name": "ISO/IEC 27001",
                "description": "Information security management standard",
                "categories": ["security", "risk_management", "controls"],
                "fines": "Loss of certification"
            },
            {
                "code": ComplianceFramework.SOC2.value,
                "name": "Service Organization Control 2",
                "description": "Security, availability, and confidentiality controls",
                "categories": ["security", "availability", "confidentiality"],
                "fines": "Loss of business trust"
            },
            {
                "code": ComplianceFramework.FERPA.value,
                "name": "Family Educational Rights and Privacy Act",
                "description": "US education records privacy",
                "categories": ["education", "student_privacy", "records"],
                "fines": "Loss of federal funding"
            },
            {
                "code": ComplianceFramework.GLBA.value,
                "name": "Gramm-Leach-Bliley Act",
                "description": "US financial services privacy",
                "categories": ["financial", "privacy", "disclosure"],
                "fines": "Up to $100,000 per violation"
            },
            {
                "code": ComplianceFramework.FCRA.value,
                "name": "Fair Credit Reporting Act",
                "description": "US consumer credit information regulation",
                "categories": ["credit", "consumer_rights", "accuracy"],
                "fines": "Up to $3,937 per violation"
            },
            {
                "code": ComplianceFramework.ADA.value,
                "name": "Americans with Disabilities Act",
                "description": "US disability rights and accessibility",
                "categories": ["accessibility", "discrimination", "accommodation"],
                "fines": "Up to $75,000 first violation"
            },
            {
                "code": ComplianceFramework.COPPA.value,
                "name": "Children's Online Privacy Protection Act",
                "description": "US children's online privacy protection",
                "categories": ["children", "online_privacy", "parental_consent"],
                "fines": "Up to $43,792 per violation"
            }
        ]
    }


@router.get("/check-types")
async def get_check_types():
    """Get available compliance check types with descriptions"""
    
    return {
        "check_types": [
            {
                "type": ComplianceCheckType.FULL_AUDIT.value,
                "name": "Full Compliance Audit",
                "description": "Comprehensive check across all compliance areas",
                "duration": "3-5 minutes",
                "coverage": ["All frameworks", "All data types", "All controls"]
            },
            {
                "type": ComplianceCheckType.DATA_PRIVACY.value,
                "name": "Data Privacy Check",
                "description": "Focus on privacy regulations and data protection",
                "duration": "2 minutes",
                "coverage": ["GDPR", "CCPA", "Privacy policies"]
            },
            {
                "type": ComplianceCheckType.SECURITY_CONTROLS.value,
                "name": "Security Controls Audit",
                "description": "Verify security measures and controls",
                "duration": "2 minutes",
                "coverage": ["Encryption", "Access controls", "Security policies"]
            },
            {
                "type": ComplianceCheckType.SENSITIVE_DATA.value,
                "name": "Sensitive Data Scan",
                "description": "Identify and classify sensitive information",
                "duration": "1-2 minutes",
                "coverage": ["PII", "PHI", "PCI", "Credentials"]
            }
        ]
    }


@router.get("/industries")
async def get_supported_industries():
    """Get list of supported industries for compliance analysis"""
    
    return {
        "industries": [
            {
                "code": "healthcare",
                "name": "Healthcare",
                "primary_frameworks": ["hipaa", "gdpr"],
                "key_concerns": ["PHI protection", "Patient privacy", "Medical records"]
            },
            {
                "code": "finance",
                "name": "Financial Services",
                "primary_frameworks": ["sox", "glba", "pci_dss"],
                "key_concerns": ["Financial data", "Transaction security", "Audit trails"]
            },
            {
                "code": "retail",
                "name": "Retail & E-commerce",
                "primary_frameworks": ["pci_dss", "ccpa", "gdpr"],
                "key_concerns": ["Payment data", "Customer privacy", "Data breaches"]
            },
            {
                "code": "education",
                "name": "Education",
                "primary_frameworks": ["ferpa", "coppa", "ada"],
                "key_concerns": ["Student records", "Minor privacy", "Accessibility"]
            },
            {
                "code": "technology",
                "name": "Technology",
                "primary_frameworks": ["soc2", "iso_27001", "gdpr"],
                "key_concerns": ["Data security", "API keys", "User privacy"]
            }
        ]
    }


@router.get("/jurisdictions")
async def get_supported_jurisdictions():
    """Get list of supported jurisdictions for compliance analysis"""
    
    return {
        "jurisdictions": [
            {
                "code": "us_federal",
                "name": "United States - Federal",
                "frameworks": ["hipaa", "sox", "glba", "ferpa", "ada"]
            },
            {
                "code": "us_ca",
                "name": "United States - California",
                "frameworks": ["ccpa", "hipaa", "sox"]
            },
            {
                "code": "eu",
                "name": "European Union",
                "frameworks": ["gdpr"]
            },
            {
                "code": "uk",
                "name": "United Kingdom",
                "frameworks": ["gdpr", "iso_27001"]
            },
            {
                "code": "canada",
                "name": "Canada",
                "frameworks": ["pipeda"]
            }
        ]
    }