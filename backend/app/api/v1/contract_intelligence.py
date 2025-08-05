"""
Contract Intelligence API endpoints - Main API
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Dict, Any, List, Optional
import logging
from enum import Enum

from app.api.v1.deps import get_current_user, get_current_active_user, get_client_manager
from app.db.models import User
from app.services.contract_intelligence_client import ContractIntelligenceClient
from app.services.client_manager import ClientManager
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class ContractAnalysisType(str, Enum):
    """Types of contract analysis available"""
    FULL_ANALYSIS = "full_analysis"
    KEY_TERMS = "key_terms"
    OBLIGATIONS = "obligations"
    RISKS = "risks"
    DEADLINES = "deadlines"
    FINANCIAL_TERMS = "financial_terms"
    TERMINATION = "termination"
    LIABILITY = "liability"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    COMPLIANCE = "compliance"


class ContractComparisonType(str, Enum):
    """Types of contract comparisons"""
    CLAUSE_COMPARISON = "clause_comparison"
    TERM_DIFFERENCES = "term_differences"
    RISK_COMPARISON = "risk_comparison"
    OBLIGATION_CHANGES = "obligation_changes"
    FINANCIAL_IMPACT = "financial_impact"


class ContractAnalysisRequest(BaseModel):
    """Request for contract analysis"""
    contract_id: Optional[str] = Field(None, description="ID of stored contract")
    content: Optional[str] = Field(None, description="Contract text content")
    analysis_type: ContractAnalysisType = Field(
        ContractAnalysisType.FULL_ANALYSIS,
        description="Type of analysis to perform"
    )
    industry: Optional[str] = Field(None, description="Industry context for analysis")
    jurisdiction: Optional[str] = Field(None, description="Legal jurisdiction")
    party_perspective: Optional[str] = Field(None, description="Which party's perspective to analyze from")
    custom_concerns: Optional[List[str]] = Field(None, description="Specific concerns to check")


class ContractAnalysisResponse(BaseModel):
    """Response from contract analysis"""
    contract_id: Optional[str]
    analysis_type: ContractAnalysisType
    summary: str
    key_clauses: List[Dict[str, Any]]
    obligations: List[Dict[str, Any]]
    risks: List[Dict[str, Any]]
    deadlines: List[Dict[str, Any]]
    financial_terms: Dict[str, Any]
    recommendations: List[str]
    metadata: Dict[str, Any]
    confidence_score: float
    processing_time: float


@router.post("/analyze", response_model=ContractAnalysisResponse)
async def analyze_contract(
    request: ContractAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Analyze a contract using advanced CAG-based intelligence
    
    This endpoint performs deep contract analysis including:
    - Key terms and conditions extraction
    - Obligation and commitment identification
    - Risk assessment and flagging
    - Deadline and milestone tracking
    - Financial terms analysis
    - Compliance checking
    
    Analysis types:
    - **full_analysis**: Comprehensive contract review
    - **key_terms**: Extract and analyze important clauses
    - **obligations**: Identify all party obligations
    - **risks**: Assess potential risks and unfavorable terms
    - **deadlines**: Extract time-sensitive obligations
    - **financial_terms**: Analyze monetary aspects
    - **termination**: Review exit conditions
    - **liability**: Assess liability and indemnification
    - **intellectual_property**: Review IP provisions
    - **compliance**: Check regulatory compliance
    """
    
    try:
        client = ContractIntelligenceClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await client.analyze_contract(
            contract_id=request.contract_id,
            content=request.content,
            analysis_type=request.analysis_type.value,
            industry=request.industry,
            jurisdiction=request.jurisdiction,
            party_perspective=request.party_perspective,
            custom_concerns=request.custom_concerns
        )
        
        return ContractAnalysisResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Contract analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Contract analysis failed")


@router.post("/analyze-file", response_model=ContractAnalysisResponse)
async def analyze_contract_file(
    file: UploadFile = File(...),
    analysis_type: ContractAnalysisType = Form(ContractAnalysisType.FULL_ANALYSIS),
    industry: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    party_perspective: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Analyze an uploaded contract file
    
    Supported formats:
    - PDF documents
    - Word documents (DOC, DOCX)
    - Text files (TXT)
    - RTF documents
    """
    
    try:
        # Read file content
        content = await file.read()
        
        client = ContractIntelligenceClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await client.analyze_file(
            file_content=content,
            filename=file.filename,
            content_type=file.content_type,
            analysis_type=analysis_type.value,
            industry=industry,
            jurisdiction=jurisdiction,
            party_perspective=party_perspective
        )
        
        return ContractAnalysisResponse(**result)
        
    except Exception as e:
        logger.error(f"Contract file analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Contract file analysis failed")


@router.post("/compare")
async def compare_contracts(
    contract_ids: List[str],
    comparison_type: ContractComparisonType = ContractComparisonType.CLAUSE_COMPARISON,
    focus_areas: Optional[List[str]] = None,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Compare multiple contracts
    
    Comparison types:
    - **clause_comparison**: Compare clauses across contracts
    - **term_differences**: Identify term variations
    - **risk_comparison**: Compare risk profiles
    - **obligation_changes**: Track obligation modifications
    - **financial_impact**: Analyze financial differences
    """
    
    if len(contract_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 contracts required for comparison")
    
    if len(contract_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 contracts can be compared at once")
    
    try:
        client = ContractIntelligenceClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await client.compare_contracts(
            contract_ids=contract_ids,
            comparison_type=comparison_type.value,
            focus_areas=focus_areas
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Contract comparison failed: {e}")
        raise HTTPException(status_code=500, detail="Contract comparison failed")


@router.get("/templates/{industry}")
async def get_contract_templates(
    industry: str,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Get standard contract templates and clauses for an industry
    
    Returns:
    - Essential clauses for the industry
    - Common negotiation points
    - Red flags to watch for
    - Best practices and recommendations
    """
    
    try:
        client = ContractIntelligenceClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.get_industry_templates(industry)
        
    except Exception as e:
        logger.error(f"Failed to get contract templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get contract templates")


@router.post("/validate/{contract_id}")
async def validate_contract(
    contract_id: str,
    validation_rules: Optional[List[str]] = None,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Validate a contract against best practices and custom rules
    
    Default validation includes:
    - Required clause presence
    - Risk balance assessment
    - Clear obligation definitions
    - Proper legal language
    - Completeness check
    """
    
    try:
        client = ContractIntelligenceClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        return await client.validate_contract(
            contract_id=contract_id,
            validation_rules=validation_rules
        )
        
    except Exception as e:
        logger.error(f"Contract validation failed: {e}")
        raise HTTPException(status_code=500, detail="Contract validation failed")


@router.get("/analysis-types")
async def get_analysis_types():
    """Get available contract analysis types with descriptions"""
    
    return {
        "analysis_types": [
            {
                "type": ContractAnalysisType.FULL_ANALYSIS.value,
                "name": "Full Analysis",
                "description": "Comprehensive contract analysis covering all aspects",
                "typical_duration": "2-3 minutes"
            },
            {
                "type": ContractAnalysisType.KEY_TERMS.value,
                "name": "Key Terms",
                "description": "Extract and analyze key contractual terms and conditions",
                "typical_duration": "1 minute"
            },
            {
                "type": ContractAnalysisType.OBLIGATIONS.value,
                "name": "Obligations",
                "description": "Identify all party obligations and commitments",
                "typical_duration": "1 minute"
            },
            {
                "type": ContractAnalysisType.RISKS.value,
                "name": "Risk Assessment",
                "description": "Analyze potential risks and unfavorable terms",
                "typical_duration": "1-2 minutes"
            },
            {
                "type": ContractAnalysisType.DEADLINES.value,
                "name": "Deadlines & Milestones",
                "description": "Extract all time-bound obligations and key dates",
                "typical_duration": "30 seconds"
            },
            {
                "type": ContractAnalysisType.FINANCIAL_TERMS.value,
                "name": "Financial Terms",
                "description": "Analyze pricing, payment terms, and financial obligations",
                "typical_duration": "1 minute"
            },
            {
                "type": ContractAnalysisType.TERMINATION.value,
                "name": "Termination Clauses",
                "description": "Review termination conditions and exit strategies",
                "typical_duration": "30 seconds"
            },
            {
                "type": ContractAnalysisType.LIABILITY.value,
                "name": "Liability Analysis",
                "description": "Assess liability allocation and limitation clauses",
                "typical_duration": "1 minute"
            },
            {
                "type": ContractAnalysisType.INTELLECTUAL_PROPERTY.value,
                "name": "IP Rights",
                "description": "Analyze intellectual property ownership and usage rights",
                "typical_duration": "1 minute"
            },
            {
                "type": ContractAnalysisType.COMPLIANCE.value,
                "name": "Compliance Check",
                "description": "Verify compliance with regulations and standards",
                "typical_duration": "1-2 minutes"
            }
        ]
    }


@router.get("/industries")
async def get_supported_industries():
    """Get list of supported industries for contract analysis"""
    
    return {
        "industries": [
            {"code": "technology", "name": "Technology & Software"},
            {"code": "healthcare", "name": "Healthcare & Medical"},
            {"code": "finance", "name": "Finance & Banking"},
            {"code": "real_estate", "name": "Real Estate"},
            {"code": "manufacturing", "name": "Manufacturing"},
            {"code": "retail", "name": "Retail & E-commerce"},
            {"code": "construction", "name": "Construction"},
            {"code": "consulting", "name": "Consulting & Professional Services"},
            {"code": "transportation", "name": "Transportation & Logistics"},
            {"code": "energy", "name": "Energy & Utilities"},
            {"code": "media", "name": "Media & Entertainment"},
            {"code": "education", "name": "Education"},
            {"code": "government", "name": "Government & Public Sector"},
            {"code": "nonprofit", "name": "Non-profit Organizations"},
            {"code": "general", "name": "General Business"}
        ]
    }


@router.get("/jurisdictions")
async def get_supported_jurisdictions():
    """Get list of supported jurisdictions for contract analysis"""
    
    return {
        "jurisdictions": [
            {"code": "us_federal", "name": "United States - Federal"},
            {"code": "us_ca", "name": "United States - California"},
            {"code": "us_ny", "name": "United States - New York"},
            {"code": "us_tx", "name": "United States - Texas"},
            {"code": "us_fl", "name": "United States - Florida"},
            {"code": "uk", "name": "United Kingdom"},
            {"code": "eu", "name": "European Union"},
            {"code": "canada", "name": "Canada"},
            {"code": "australia", "name": "Australia"},
            {"code": "singapore", "name": "Singapore"},
            {"code": "india", "name": "India"},
            {"code": "general", "name": "General International"}
        ]
    }