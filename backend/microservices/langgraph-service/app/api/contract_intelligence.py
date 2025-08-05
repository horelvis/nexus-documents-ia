"""
Contract Intelligence API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from enum import Enum

from app.core.dependencies import validate_service_access
from app.services.contract_processor import ContractProcessor
from app.core.cag_engine import CAGEngine
from app.core.embeddings import EmbeddingsService
from app.core.llm import LLMService
from app.core.vector_service import VectorService
from app.core.config import get_settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


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


class ContractClause(BaseModel):
    """Represents a contract clause"""
    clause_type: str
    text: str
    section: Optional[str] = None
    risk_level: str = "low"  # low, medium, high, critical
    explanation: Optional[str] = None
    recommendations: Optional[List[str]] = None


class ContractObligation(BaseModel):
    """Represents a contractual obligation"""
    party: str
    obligation: str
    deadline: Optional[datetime] = None
    conditions: Optional[List[str]] = None
    penalties: Optional[str] = None
    priority: str = "medium"  # low, medium, high, critical


class ContractRisk(BaseModel):
    """Represents a contract risk"""
    risk_type: str
    description: str
    severity: str  # low, medium, high, critical
    affected_clauses: List[str]
    mitigation_suggestions: List[str]
    likelihood: str = "medium"  # low, medium, high


class ContractAnalysisResponse(BaseModel):
    """Response from contract analysis"""
    contract_id: Optional[str]
    analysis_type: ContractAnalysisType
    summary: str
    key_clauses: List[ContractClause]
    obligations: List[ContractObligation]
    risks: List[ContractRisk]
    deadlines: List[Dict[str, Any]]
    financial_terms: Dict[str, Any]
    recommendations: List[str]
    metadata: Dict[str, Any]
    confidence_score: float
    processing_time: float


class ContractComparisonRequest(BaseModel):
    """Request for contract comparison"""
    contract_ids: List[str] = Field(..., min_items=2, max_items=5)
    comparison_type: ContractComparisonType
    focus_areas: Optional[List[str]] = None


class ContractComparisonResponse(BaseModel):
    """Response from contract comparison"""
    comparison_type: ContractComparisonType
    contracts_analyzed: List[str]
    differences: List[Dict[str, Any]]
    similarities: List[Dict[str, Any]]
    risk_delta: Dict[str, Any]
    recommendations: List[str]
    summary: str


@router.post("/analyze", response_model=ContractAnalysisResponse)
async def analyze_contract(
    request: ContractAnalysisRequest,
    context: dict = Depends(validate_service_access)
):
    """
    Analyze a contract using CAG-based intelligence
    
    This endpoint performs deep contract analysis including:
    - Key terms and conditions extraction
    - Obligation and commitment identification
    - Risk assessment and flagging
    - Deadline and milestone tracking
    - Financial terms analysis
    - Compliance checking
    """
    
    start_time = datetime.now()
    
    try:
        if not request.contract_id and not request.content:
            raise HTTPException(status_code=400, detail="Either contract_id or content must be provided")
        
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
        
        # Initialize contract processor
        processor = ContractProcessor(cag_engine)
        
        # Get contract content
        if request.content:
            contract_content = request.content
        else:
            # TODO: Fetch from storage service by contract_id
            contract_content = f"Contract content for ID: {request.contract_id}"
        
        # Perform analysis based on type
        if request.analysis_type == ContractAnalysisType.FULL_ANALYSIS:
            result = await processor.full_analysis(
                contract_content,
                industry=request.industry,
                jurisdiction=request.jurisdiction,
                party_perspective=request.party_perspective,
                custom_concerns=request.custom_concerns
            )
        elif request.analysis_type == ContractAnalysisType.KEY_TERMS:
            result = await processor.extract_key_terms(contract_content)
        elif request.analysis_type == ContractAnalysisType.OBLIGATIONS:
            result = await processor.extract_obligations(
                contract_content,
                party_perspective=request.party_perspective
            )
        elif request.analysis_type == ContractAnalysisType.RISKS:
            result = await processor.assess_risks(
                contract_content,
                industry=request.industry,
                custom_concerns=request.custom_concerns
            )
        elif request.analysis_type == ContractAnalysisType.DEADLINES:
            result = await processor.extract_deadlines(contract_content)
        elif request.analysis_type == ContractAnalysisType.FINANCIAL_TERMS:
            result = await processor.analyze_financial_terms(contract_content)
        elif request.analysis_type == ContractAnalysisType.TERMINATION:
            result = await processor.analyze_termination_clauses(contract_content)
        elif request.analysis_type == ContractAnalysisType.LIABILITY:
            result = await processor.analyze_liability(contract_content)
        elif request.analysis_type == ContractAnalysisType.INTELLECTUAL_PROPERTY:
            result = await processor.analyze_ip_clauses(contract_content)
        elif request.analysis_type == ContractAnalysisType.COMPLIANCE:
            result = await processor.check_compliance(
                contract_content,
                jurisdiction=request.jurisdiction,
                industry=request.industry
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown analysis type: {request.analysis_type}")
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Prepare response
        return ContractAnalysisResponse(
            contract_id=request.contract_id,
            analysis_type=request.analysis_type,
            summary=result.get("summary", ""),
            key_clauses=result.get("key_clauses", []),
            obligations=result.get("obligations", []),
            risks=result.get("risks", []),
            deadlines=result.get("deadlines", []),
            financial_terms=result.get("financial_terms", {}),
            recommendations=result.get("recommendations", []),
            metadata={
                "industry": request.industry,
                "jurisdiction": request.jurisdiction,
                "party_perspective": request.party_perspective,
                "custom_concerns": request.custom_concerns,
                "total_clauses_analyzed": result.get("total_clauses", 0),
                "analysis_depth": result.get("analysis_depth", "standard")
            },
            confidence_score=result.get("confidence_score", 0.85),
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"Contract analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Contract analysis failed: {str(e)}")


@router.post("/analyze-file", response_model=ContractAnalysisResponse)
async def analyze_contract_file(
    file: UploadFile = File(...),
    analysis_type: ContractAnalysisType = Form(ContractAnalysisType.FULL_ANALYSIS),
    industry: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    party_perspective: Optional[str] = Form(None),
    context: dict = Depends(validate_service_access)
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
        
        # Initialize contract processor
        processor = ContractProcessor(cag_engine)
        
        # Extract text from file
        from app.services.document_processor import DocumentProcessor
        doc_processor = DocumentProcessor()
        
        extracted_text = await doc_processor.process_file(
            content=content,
            filename=file.filename,
            content_type=file.content_type
        )
        
        if not extracted_text.get("text"):
            raise HTTPException(status_code=400, detail="Could not extract text from contract file")
        
        # Create analysis request
        request = ContractAnalysisRequest(
            content=extracted_text["text"],
            analysis_type=analysis_type,
            industry=industry,
            jurisdiction=jurisdiction,
            party_perspective=party_perspective
        )
        
        # Perform analysis
        return await analyze_contract(request, context)
        
    except Exception as e:
        logger.error(f"Contract file analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Contract file analysis failed: {str(e)}")


@router.post("/compare", response_model=ContractComparisonResponse)
async def compare_contracts(
    request: ContractComparisonRequest,
    context: dict = Depends(validate_service_access)
):
    """
    Compare multiple contracts
    
    This endpoint compares contracts to identify:
    - Clause differences and variations
    - Risk level changes
    - Obligation modifications
    - Financial impact analysis
    - Term improvements or degradations
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
        
        # Initialize contract processor
        processor = ContractProcessor(cag_engine)
        
        # TODO: Fetch contract contents from storage
        contracts = {}
        for contract_id in request.contract_ids:
            contracts[contract_id] = f"Contract content for ID: {contract_id}"
        
        # Perform comparison
        result = await processor.compare_contracts(
            contracts=contracts,
            comparison_type=request.comparison_type,
            focus_areas=request.focus_areas
        )
        
        return ContractComparisonResponse(
            comparison_type=request.comparison_type,
            contracts_analyzed=request.contract_ids,
            differences=result.get("differences", []),
            similarities=result.get("similarities", []),
            risk_delta=result.get("risk_delta", {}),
            recommendations=result.get("recommendations", []),
            summary=result.get("summary", "")
        )
        
    except Exception as e:
        logger.error(f"Contract comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Contract comparison failed: {str(e)}")


@router.get("/templates/{industry}")
async def get_contract_templates(
    industry: str,
    context: dict = Depends(validate_service_access)
):
    """
    Get standard contract templates and clauses for an industry
    
    Returns common contract structures and recommended clauses
    based on industry best practices.
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
        
        # Initialize contract processor
        processor = ContractProcessor(cag_engine)
        
        # Get templates
        templates = await processor.get_industry_templates(industry)
        
        return templates
        
    except Exception as e:
        logger.error(f"Failed to get contract templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get contract templates: {str(e)}")


@router.post("/validate")
async def validate_contract(
    contract_id: str,
    validation_rules: Optional[List[str]] = None,
    context: dict = Depends(validate_service_access)
):
    """
    Validate a contract against predefined rules and best practices
    
    Checks for:
    - Required clauses presence
    - Prohibited terms
    - Balanced risk allocation
    - Clear obligations and deadlines
    - Proper legal language
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
        
        # Initialize contract processor
        processor = ContractProcessor(cag_engine)
        
        # TODO: Fetch contract content from storage
        contract_content = f"Contract content for ID: {contract_id}"
        
        # Validate contract
        validation_result = await processor.validate_contract(
            contract_content,
            custom_rules=validation_rules
        )
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Contract validation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Contract validation failed: {str(e)}")


@router.get("/analysis-types")
async def get_analysis_types():
    """Get available contract analysis types with descriptions"""
    
    return {
        "analysis_types": [
            {
                "type": ContractAnalysisType.FULL_ANALYSIS,
                "name": "Full Analysis",
                "description": "Comprehensive contract analysis covering all aspects"
            },
            {
                "type": ContractAnalysisType.KEY_TERMS,
                "name": "Key Terms",
                "description": "Extract and analyze key contractual terms and conditions"
            },
            {
                "type": ContractAnalysisType.OBLIGATIONS,
                "name": "Obligations",
                "description": "Identify all party obligations and commitments"
            },
            {
                "type": ContractAnalysisType.RISKS,
                "name": "Risk Assessment",
                "description": "Analyze potential risks and unfavorable terms"
            },
            {
                "type": ContractAnalysisType.DEADLINES,
                "name": "Deadlines & Milestones",
                "description": "Extract all time-bound obligations and key dates"
            },
            {
                "type": ContractAnalysisType.FINANCIAL_TERMS,
                "name": "Financial Terms",
                "description": "Analyze pricing, payment terms, and financial obligations"
            },
            {
                "type": ContractAnalysisType.TERMINATION,
                "name": "Termination Clauses",
                "description": "Review termination conditions and exit strategies"
            },
            {
                "type": ContractAnalysisType.LIABILITY,
                "name": "Liability Analysis",
                "description": "Assess liability allocation and limitation clauses"
            },
            {
                "type": ContractAnalysisType.INTELLECTUAL_PROPERTY,
                "name": "IP Rights",
                "description": "Analyze intellectual property ownership and usage rights"
            },
            {
                "type": ContractAnalysisType.COMPLIANCE,
                "name": "Compliance Check",
                "description": "Verify compliance with regulations and standards"
            }
        ]
    }