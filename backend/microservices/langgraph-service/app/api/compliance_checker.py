"""
Compliance Checker API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Dict, Any, List, Optional, Set
import logging
from datetime import datetime
from enum import Enum

from app.core.dependencies import validate_service_access
from app.services.compliance_processor import ComplianceProcessor
from app.core.cag_engine import CAGEngine
from app.core.embeddings import EmbeddingsService
from app.core.llm import LLMService
from app.core.vector_service import VectorService
from app.core.config import get_settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


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


class SensitivityLevel(str, Enum):
    """Data sensitivity levels"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    CRITICAL = "critical"


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
    
    
class ComplianceViolation(BaseModel):
    """Represents a compliance violation"""
    framework: str
    regulation: str
    description: str
    severity: str  # low, medium, high, critical
    location: Optional[str] = None
    evidence: Optional[str] = None
    remediation: str
    legal_risk: str
    

class SensitiveDataItem(BaseModel):
    """Represents sensitive data found"""
    data_type: str  # PII, PHI, PCI, etc.
    category: str  # name, ssn, credit_card, medical, etc.
    value_pattern: str  # Masked value
    count: int
    locations: List[str]
    sensitivity_level: SensitivityLevel
    compliance_impact: List[str]  # Which regulations are affected
    

class ComplianceRecommendation(BaseModel):
    """Compliance improvement recommendation"""
    priority: str  # low, medium, high, critical
    category: str
    action: str
    rationale: str
    frameworks_addressed: List[str]
    implementation_effort: str  # low, medium, high
    

class ComplianceCheckResponse(BaseModel):
    """Response from compliance check"""
    document_id: Optional[str]
    check_type: ComplianceCheckType
    frameworks_checked: List[ComplianceFramework]
    compliance_score: float  # 0-100
    is_compliant: bool
    violations: List[ComplianceViolation]
    sensitive_data: List[SensitiveDataItem]
    recommendations: List[ComplianceRecommendation]
    summary: str
    risk_assessment: Dict[str, Any]
    metadata: Dict[str, Any]
    processing_time: float


class CompliancePolicyRequest(BaseModel):
    """Request to create/update compliance policy"""
    name: str
    description: str
    rules: List[str]
    frameworks: List[ComplianceFramework]
    active: bool = True


class DataMappingRequest(BaseModel):
    """Request for data mapping and classification"""
    document_ids: List[str]
    deep_scan: bool = False
    

class DataMappingResponse(BaseModel):
    """Response from data mapping"""
    total_documents: int
    data_categories: Dict[str, int]  # Category -> count
    sensitivity_distribution: Dict[str, int]  # Level -> count
    compliance_coverage: Dict[str, float]  # Framework -> coverage %
    gaps_identified: List[str]
    recommendations: List[str]


@router.post("/check", response_model=ComplianceCheckResponse)
async def check_compliance(
    request: ComplianceCheckRequest,
    context: dict = Depends(validate_service_access)
):
    """
    Check document compliance against specified frameworks
    
    This endpoint performs comprehensive compliance analysis:
    - Regulatory requirement checking
    - Sensitive data detection
    - Policy violation identification
    - Risk assessment
    - Remediation recommendations
    """
    
    start_time = datetime.now()
    
    try:
        if not request.document_id and not request.content:
            raise HTTPException(status_code=400, detail="Either document_id or content must be provided")
        
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Get document content
        if request.content:
            document_content = request.content
        else:
            # TODO: Fetch from storage service by document_id
            document_content = f"Document content for ID: {request.document_id}"
        
        # Perform compliance check based on type
        if request.check_type == ComplianceCheckType.FULL_AUDIT:
            result = await processor.full_compliance_audit(
                document_content,
                frameworks=[f.value for f in request.frameworks],
                industry=request.industry,
                jurisdiction=request.jurisdiction,
                custom_policies=request.custom_policies
            )
        elif request.check_type == ComplianceCheckType.DATA_PRIVACY:
            result = await processor.check_data_privacy(
                document_content,
                frameworks=[f.value for f in request.frameworks]
            )
        elif request.check_type == ComplianceCheckType.SECURITY_CONTROLS:
            result = await processor.check_security_controls(document_content)
        elif request.check_type == ComplianceCheckType.ACCESS_CONTROLS:
            result = await processor.check_access_controls(document_content)
        elif request.check_type == ComplianceCheckType.RETENTION_POLICIES:
            result = await processor.check_retention_policies(document_content)
        elif request.check_type == ComplianceCheckType.CONSENT_MANAGEMENT:
            result = await processor.check_consent_management(document_content)
        elif request.check_type == ComplianceCheckType.BREACH_NOTIFICATION:
            result = await processor.check_breach_notification(document_content)
        elif request.check_type == ComplianceCheckType.THIRD_PARTY_SHARING:
            result = await processor.check_third_party_sharing(document_content)
        elif request.check_type == ComplianceCheckType.SENSITIVE_DATA:
            result = await processor.scan_sensitive_data(document_content)
        elif request.check_type == ComplianceCheckType.REGULATORY_SPECIFIC:
            result = await processor.check_regulatory_specific(
                document_content,
                frameworks=[f.value for f in request.frameworks],
                jurisdiction=request.jurisdiction
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown check type: {request.check_type}")
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Prepare response
        return ComplianceCheckResponse(
            document_id=request.document_id,
            check_type=request.check_type,
            frameworks_checked=request.frameworks,
            compliance_score=result.get("compliance_score", 0.0),
            is_compliant=result.get("is_compliant", False),
            violations=[ComplianceViolation(**v) for v in result.get("violations", [])],
            sensitive_data=[SensitiveDataItem(**s) for s in result.get("sensitive_data", [])],
            recommendations=[ComplianceRecommendation(**r) for r in result.get("recommendations", [])],
            summary=result.get("summary", ""),
            risk_assessment=result.get("risk_assessment", {}),
            metadata={
                "industry": request.industry,
                "jurisdiction": request.jurisdiction,
                "total_rules_checked": result.get("total_rules_checked", 0),
                "scan_depth": result.get("scan_depth", "standard")
            },
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"Compliance check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {str(e)}")


@router.post("/check-file", response_model=ComplianceCheckResponse)
async def check_file_compliance(
    file: UploadFile = File(...),
    frameworks: str = Form("gdpr"),  # Comma-separated list
    check_type: ComplianceCheckType = Form(ComplianceCheckType.FULL_AUDIT),
    industry: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    context: dict = Depends(validate_service_access)
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
        
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Extract text from file
        from app.services.document_processor import DocumentProcessor
        doc_processor = DocumentProcessor()
        
        extracted_text = await doc_processor.process_file(
            content=content,
            filename=file.filename,
            content_type=file.content_type
        )
        
        if not extracted_text.get("text"):
            raise HTTPException(status_code=400, detail="Could not extract text from file")
        
        # Create compliance request
        request = ComplianceCheckRequest(
            content=extracted_text["text"],
            frameworks=framework_list,
            check_type=check_type,
            industry=industry,
            jurisdiction=jurisdiction
        )
        
        # Perform check
        return await check_compliance(request, context)
        
    except Exception as e:
        logger.error(f"File compliance check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File compliance check failed: {str(e)}")


@router.post("/scan-sensitive-data")
async def scan_for_sensitive_data(
    document_ids: List[str],
    deep_scan: bool = False,
    context: dict = Depends(validate_service_access)
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
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Scan each document
        results = []
        for doc_id in document_ids:
            # TODO: Fetch document content
            document_content = f"Document content for ID: {doc_id}"
            
            scan_result = await processor.scan_sensitive_data(
                document_content,
                deep_scan=deep_scan
            )
            
            results.append({
                "document_id": doc_id,
                "sensitive_data": scan_result.get("sensitive_data", []),
                "risk_score": scan_result.get("risk_score", 0)
            })
        
        # Aggregate results
        all_sensitive_data = []
        total_risk = 0
        
        for result in results:
            all_sensitive_data.extend(result["sensitive_data"])
            total_risk += result["risk_score"]
        
        return {
            "documents_scanned": len(document_ids),
            "total_sensitive_items": len(all_sensitive_data),
            "average_risk_score": total_risk / len(results) if results else 0,
            "sensitive_data_summary": processor._summarize_sensitive_data(all_sensitive_data),
            "detailed_results": results if deep_scan else None
        }
        
    except Exception as e:
        logger.error(f"Sensitive data scan failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sensitive data scan failed: {str(e)}")


@router.post("/data-mapping", response_model=DataMappingResponse)
async def create_data_mapping(
    request: DataMappingRequest,
    context: dict = Depends(validate_service_access)
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
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Process documents
        mapping_result = await processor.create_data_mapping(
            document_ids=request.document_ids,
            deep_scan=request.deep_scan
        )
        
        return DataMappingResponse(
            total_documents=len(request.document_ids),
            data_categories=mapping_result.get("data_categories", {}),
            sensitivity_distribution=mapping_result.get("sensitivity_distribution", {}),
            compliance_coverage=mapping_result.get("compliance_coverage", {}),
            gaps_identified=mapping_result.get("gaps", []),
            recommendations=mapping_result.get("recommendations", [])
        )
        
    except Exception as e:
        logger.error(f"Data mapping failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Data mapping failed: {str(e)}")


@router.post("/generate-report")
async def generate_compliance_report(
    document_ids: List[str],
    frameworks: List[ComplianceFramework],
    include_remediation: bool = True,
    context: dict = Depends(validate_service_access)
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
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Generate report
        report = await processor.generate_compliance_report(
            document_ids=document_ids,
            frameworks=[f.value for f in frameworks],
            include_remediation=include_remediation
        )
        
        return report
        
    except Exception as e:
        logger.error(f"Report generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.post("/policies")
async def create_custom_policy(
    policy: CompliancePolicyRequest,
    context: dict = Depends(validate_service_access)
):
    """
    Create custom compliance policy
    
    Allows organizations to define their own compliance rules
    beyond standard frameworks.
    """
    
    try:
        # Initialize services
        embeddings_service = EmbeddingsService()
        llm_service = LLMService()
        vector_service = VectorService(
            embeddings_service=embeddings_service,
            tenant_id=context.get("tenant_id", settings.DEFAULT_TENANT)
        )
        
        # Initialize CAG engine
        cag_engine = CAGEngine(
            llm=llm_service.llm,
            embeddings=embeddings_service.embeddings,
            vector_service=vector_service
        )
        
        # Initialize compliance processor
        processor = ComplianceProcessor(cag_engine)
        
        # Create policy
        policy_id = await processor.create_custom_policy(
            name=policy.name,
            description=policy.description,
            rules=policy.rules,
            frameworks=[f.value for f in policy.frameworks]
        )
        
        return {
            "policy_id": policy_id,
            "status": "created",
            "message": f"Custom policy '{policy.name}' created successfully"
        }
        
    except Exception as e:
        logger.error(f"Policy creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Policy creation failed: {str(e)}")


@router.get("/frameworks")
async def get_compliance_frameworks():
    """Get available compliance frameworks with descriptions"""
    
    return {
        "frameworks": [
            {
                "code": ComplianceFramework.GDPR.value,
                "name": "General Data Protection Regulation",
                "description": "EU data protection and privacy regulation",
                "categories": ["data_privacy", "consent", "data_rights"]
            },
            {
                "code": ComplianceFramework.CCPA.value,
                "name": "California Consumer Privacy Act",
                "description": "California state privacy law",
                "categories": ["data_privacy", "consumer_rights", "data_sale"]
            },
            {
                "code": ComplianceFramework.HIPAA.value,
                "name": "Health Insurance Portability and Accountability Act",
                "description": "US healthcare data privacy and security",
                "categories": ["healthcare", "phi", "security"]
            },
            {
                "code": ComplianceFramework.SOX.value,
                "name": "Sarbanes-Oxley Act",
                "description": "US financial reporting and internal controls",
                "categories": ["financial", "internal_controls", "audit"]
            },
            {
                "code": ComplianceFramework.PCI_DSS.value,
                "name": "Payment Card Industry Data Security Standard",
                "description": "Credit card data security requirements",
                "categories": ["payment", "security", "encryption"]
            },
            {
                "code": ComplianceFramework.ISO_27001.value,
                "name": "ISO/IEC 27001",
                "description": "Information security management standard",
                "categories": ["security", "risk_management", "controls"]
            },
            {
                "code": ComplianceFramework.SOC2.value,
                "name": "Service Organization Control 2",
                "description": "Security, availability, and confidentiality controls",
                "categories": ["security", "availability", "confidentiality"]
            },
            {
                "code": ComplianceFramework.FERPA.value,
                "name": "Family Educational Rights and Privacy Act",
                "description": "US education records privacy",
                "categories": ["education", "student_privacy", "records"]
            },
            {
                "code": ComplianceFramework.GLBA.value,
                "name": "Gramm-Leach-Bliley Act",
                "description": "US financial services privacy",
                "categories": ["financial", "privacy", "disclosure"]
            },
            {
                "code": ComplianceFramework.FCRA.value,
                "name": "Fair Credit Reporting Act",
                "description": "US consumer credit information regulation",
                "categories": ["credit", "consumer_rights", "accuracy"]
            },
            {
                "code": ComplianceFramework.ADA.value,
                "name": "Americans with Disabilities Act",
                "description": "US disability rights and accessibility",
                "categories": ["accessibility", "discrimination", "accommodation"]
            },
            {
                "code": ComplianceFramework.COPPA.value,
                "name": "Children's Online Privacy Protection Act",
                "description": "US children's online privacy protection",
                "categories": ["children", "online_privacy", "parental_consent"]
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
                "duration": "3-5 minutes"
            },
            {
                "type": ComplianceCheckType.DATA_PRIVACY.value,
                "name": "Data Privacy Check",
                "description": "Focus on privacy regulations and data protection",
                "duration": "2 minutes"
            },
            {
                "type": ComplianceCheckType.SECURITY_CONTROLS.value,
                "name": "Security Controls Audit",
                "description": "Verify security measures and controls",
                "duration": "2 minutes"
            },
            {
                "type": ComplianceCheckType.ACCESS_CONTROLS.value,
                "name": "Access Control Review",
                "description": "Check user access and permission controls",
                "duration": "1 minute"
            },
            {
                "type": ComplianceCheckType.RETENTION_POLICIES.value,
                "name": "Retention Policy Check",
                "description": "Verify data retention and deletion policies",
                "duration": "1 minute"
            },
            {
                "type": ComplianceCheckType.CONSENT_MANAGEMENT.value,
                "name": "Consent Management Audit",
                "description": "Review consent collection and management",
                "duration": "2 minutes"
            },
            {
                "type": ComplianceCheckType.BREACH_NOTIFICATION.value,
                "name": "Breach Notification Review",
                "description": "Check breach notification procedures",
                "duration": "1 minute"
            },
            {
                "type": ComplianceCheckType.THIRD_PARTY_SHARING.value,
                "name": "Third-Party Sharing Audit",
                "description": "Review data sharing with third parties",
                "duration": "2 minutes"
            },
            {
                "type": ComplianceCheckType.SENSITIVE_DATA.value,
                "name": "Sensitive Data Scan",
                "description": "Identify and classify sensitive information",
                "duration": "1-2 minutes"
            },
            {
                "type": ComplianceCheckType.REGULATORY_SPECIFIC.value,
                "name": "Regulatory-Specific Check",
                "description": "Focus on specific regulatory requirements",
                "duration": "2-3 minutes"
            }
        ]
    }