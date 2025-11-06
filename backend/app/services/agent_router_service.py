"""
Agent Router Service - Intelligent document routing and agent assignment
"""
import logging
import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text

from app.core.config import settings
from app.db.models import Document
from app.schemas.enums import IndexingStatus

logger = logging.getLogger(__name__)


class AgentRouterService:
    """Service for intelligent document routing and agent assignment"""
    
    # Document type to agents mapping
    AGENT_MAPPING = {
        "contract": {
            "agents": ["legal_compliance", "digital_signature", "contract_analyzer"],
            "strategy": "sequential",
            "priority": "high"
        },
        "invoice": {
            "agents": ["financial_analysis", "document_analyzer"],
            "strategy": "parallel",
            "priority": "normal"
        },
        "report": {
            "agents": ["document_analyzer", "rag_assistant"],
            "strategy": "parallel",
            "priority": "normal"
        },
        "legal": {
            "agents": ["legal_compliance", "contract_analyzer", "digital_signature"],
            "strategy": "sequential",
            "priority": "high"
        },
        "financial": {
            "agents": ["financial_analysis", "document_analyzer"],
            "strategy": "parallel",
            "priority": "high"
        },
        "correspondence": {
            "agents": ["document_analyzer", "rag_assistant"],
            "strategy": "parallel",
            "priority": "low"
        },
        "compliance": {
            "agents": ["legal_compliance", "document_analyzer"],
            "strategy": "sequential",
            "priority": "high"
        },
        "technical": {
            "agents": ["document_analyzer", "rag_assistant"],
            "strategy": "parallel",
            "priority": "normal"
        },
        "hr": {
            "agents": ["document_analyzer", "legal_compliance"],
            "strategy": "parallel",
            "priority": "normal"
        },
        "general": {
            "agents": ["document_analyzer", "rag_assistant"],
            "strategy": "parallel",
            "priority": "low"
        }
    }
    
    def __init__(self, tenant_id: str, user_id: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    async def analyze_and_route_document(
        self,
        db: AsyncSession,
        document_id: str,
        content: str,
        filename: str,
        file_type: str
    ) -> Dict[str, Any]:
        """
        Analyze document and determine routing strategy
        """
        try:
            logger.info(f"Starting document routing analysis for {document_id}")
            
            # Step 1: Analyze document with CAG
            analysis_result = await self._analyze_with_cag(content, filename, document_id)
            
            # Step 2: Determine document type and characteristics
            doc_type = analysis_result.get("document_type", "general")
            confidence = analysis_result.get("confidence", 0.7)
            
            # Step 3: Get routing configuration
            routing_config = self.AGENT_MAPPING.get(doc_type, self.AGENT_MAPPING["general"])
            
            # Step 4: Detect special characteristics
            characteristics = await self._detect_characteristics(content, analysis_result)
            
            # Step 5: Determine assigned agents
            assigned_agents = self._determine_agents(
                doc_type,
                characteristics,
                routing_config["agents"]
            )
            
            # Step 6: Save routing analysis to database
            routing_analysis = await self._save_routing_analysis(
                db,
                document_id,
                doc_type,
                confidence,
                characteristics,
                assigned_agents,
                routing_config
            )
            
            # Step 7: Create agent assignments
            await self._create_agent_assignments(
                db,
                routing_analysis["id"],
                document_id,
                assigned_agents,
                routing_config["strategy"]
            )
            
            logger.info(f"Document routing completed for {document_id}")
            
            return {
                "success": True,
                "document_id": document_id,
                "document_type": doc_type,
                "confidence": confidence,
                "characteristics": characteristics,
                "assigned_agents": assigned_agents,
                "routing_strategy": routing_config["strategy"],
                "priority": routing_config["priority"],
                "routing_id": routing_analysis["id"]
            }
            
        except Exception as e:
            logger.error(f"Error in document routing: {e}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }
    
    async def _analyze_with_cag(self, content: str, filename: str, document_id: str = None) -> Dict[str, Any]:
        """Analyze document using CAG service"""
        try:
            # Prepare content for analysis (limit size)
            analysis_content = content[:10000] if len(content) > 10000 else content
            
            # Generate document_id if not provided
            if not document_id:
                document_id = str(uuid.uuid4())
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.CAG_SERVICE_URL}/api/v1/cag/analyze",
                    json={
                        "document_content": analysis_content,
                        "document_id": document_id,
                        "tenant_id": self.tenant_id,
                        "user_id": self.user_id,
                        "analysis_type": "comprehensive"
                    },
                    headers={"X-API-Key": settings.MICROSERVICES_API_KEY}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Extract document type from CAG analysis
                    # CAG now returns document_type and confidence directly
                    doc_type = result.get("document_type")
                    confidence = result.get("confidence")
                    
                    # Fallback to extraction if not provided
                    if not doc_type:
                        doc_type = self._extract_document_type(result, filename, analysis_content)
                        confidence = result.get("quality_score", 0.7)
                    
                    return {
                        "document_type": doc_type,
                        "confidence": confidence,
                        "summary": result.get("summary", ""),
                        "entities": result.get("entities", []),
                        "key_terms": result.get("key_terms", []),
                        "language": result.get("language", "en")
                    }
                else:
                    logger.warning(f"CAG analysis failed with status {response.status_code}")
                    return self._fallback_analysis(filename, analysis_content)
                    
        except Exception as e:
            logger.error(f"Error calling CAG service: {e}")
            return self._fallback_analysis(filename, content[:1000])
    
    def _extract_document_type(self, cag_result: Dict, filename: str, content: str) -> str:
        """Extract document type from CAG analysis"""
        # Check CAG suggested type
        if "document_type" in cag_result:
            return cag_result["document_type"]
        
        # Use DocumentTypeDetector for accurate detection
        try:
            from app.services.document_type_detector import get_document_type_detector
            detector = get_document_type_detector()
            doc_type, confidence = detector.detect_type(content, filename)
            
            # Log detection result
            logger.info(f"Document type detected: {doc_type} (confidence: {confidence:.2f})")
            return doc_type
        except Exception as e:
            logger.warning(f"Could not use DocumentTypeDetector: {e}")
            
            # Basic fallback
            filename_lower = filename.lower()
            content_lower = content.lower()[:2000]
            
            if "contract" in filename_lower or "agreement" in content_lower:
                return "contract"
            elif "invoice" in filename_lower or "bill" in content_lower:
                return "invoice"
            elif "report" in filename_lower or "analysis" in content_lower:
                return "report"
            else:
                return "general"
    
    def _fallback_analysis(self, filename: str, content: str) -> Dict[str, Any]:
        """Fallback analysis when CAG is not available"""
        doc_type = self._simple_type_detection(filename, content)
        return {
            "document_type": doc_type,
            "confidence": 0.5,
            "summary": "",
            "entities": [],
            "key_terms": [],
            "language": "en"
        }
    
    def _simple_type_detection(self, filename: str, content: str) -> str:
        """Simple rule-based document type detection"""
        try:
            from app.services.document_type_detector import get_document_type_detector
            detector = get_document_type_detector()
            doc_type, _ = detector.detect_type(content, filename)
            return doc_type
        except Exception as e:
            logger.warning(f"Could not use DocumentTypeDetector in fallback: {e}")
            # Very basic fallback
            filename_lower = filename.lower()
            if "contract" in filename_lower or "agreement" in filename_lower:
                return "contract"
            elif "invoice" in filename_lower or "bill" in filename_lower:
                return "invoice"
            elif "report" in filename_lower:
                return "report"
            else:
                return "general"
    
    async def _detect_characteristics(self, content: str, analysis: Dict) -> Dict[str, bool]:
        """Detect special document characteristics"""
        content_lower = content.lower()[:5000]
        
        return {
            "is_signable": self._detect_signable(content_lower),
            "requires_approval": self._detect_approval_needed(content_lower),
            "is_confidential": self._detect_confidential(content_lower),
            "has_financial_data": self._detect_financial_data(content_lower),
            "has_personal_data": self._detect_personal_data(content_lower),
            "has_legal_clauses": self._detect_legal_clauses(content_lower)
        }
    
    def _detect_signable(self, content: str) -> bool:
        """Detect if document requires signatures"""
        signature_indicators = [
            "signature", "sign here", "signed by", "authorized signature",
            "witness", "notary", "_____________", "sign:", "signature:"
        ]
        return any(ind in content for ind in signature_indicators)
    
    def _detect_approval_needed(self, content: str) -> bool:
        """Detect if document needs approval"""
        approval_indicators = [
            "approval", "approve", "authorized by", "reviewed by",
            "for approval", "pending approval", "requires approval"
        ]
        return any(ind in content for ind in approval_indicators)
    
    def _detect_confidential(self, content: str) -> bool:
        """Detect if document is confidential"""
        confidential_indicators = [
            "confidential", "proprietary", "restricted", "internal use only",
            "not for distribution", "classified", "sensitive"
        ]
        return any(ind in content for ind in confidential_indicators)
    
    def _detect_financial_data(self, content: str) -> bool:
        """Detect financial data presence"""
        financial_indicators = [
            "$", "€", "£", "¥", "usd", "eur", "revenue", "expense",
            "balance", "payment", "invoice", "total amount"
        ]
        return any(ind in content for ind in financial_indicators)
    
    def _detect_personal_data(self, content: str) -> bool:
        """Detect personal data presence"""
        import re
        
        # Check for common PII patterns
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        
        has_email = bool(re.search(email_pattern, content))
        has_phone = bool(re.search(phone_pattern, content))
        has_ssn = bool(re.search(ssn_pattern, content))
        
        pii_keywords = ["date of birth", "social security", "passport", "driver license"]
        has_pii_keywords = any(keyword in content for keyword in pii_keywords)
        
        return has_email or has_phone or has_ssn or has_pii_keywords
    
    def _detect_legal_clauses(self, content: str) -> bool:
        """Detect legal clauses presence"""
        legal_indicators = [
            "whereas", "hereby", "pursuant to", "in witness whereof",
            "terms and conditions", "governing law", "jurisdiction",
            "indemnification", "liability", "warranty"
        ]
        count = sum(1 for ind in legal_indicators if ind in content)
        return count >= 3
    
    def _determine_agents(
        self,
        doc_type: str,
        characteristics: Dict[str, bool],
        base_agents: List[str]
    ) -> List[Dict[str, Any]]:
        """Determine which agents should process the document"""
        agents = []
        
        # Add base agents for document type
        for agent_type in base_agents:
            agents.append({
                "type": agent_type,
                "name": self._get_agent_name(agent_type),
                "reason": f"Standard agent for {doc_type} documents",
                "priority": 1
            })
        
        # Add additional agents based on characteristics
        if characteristics.get("is_signable") and "digital_signature" not in base_agents:
            agents.append({
                "type": "digital_signature",
                "name": "Digital Signature Agent",
                "reason": "Document contains signature fields",
                "priority": 2
            })
        
        if characteristics.get("has_legal_clauses") and "legal_compliance" not in base_agents:
            agents.append({
                "type": "legal_compliance",
                "name": "Legal Compliance Agent",
                "reason": "Document contains legal clauses",
                "priority": 2
            })
        
        if characteristics.get("has_financial_data") and "financial_analysis" not in base_agents:
            agents.append({
                "type": "financial_analysis",
                "name": "Financial Analysis Agent",
                "reason": "Document contains financial data",
                "priority": 2
            })
        
        if characteristics.get("is_confidential"):
            # Add security/compliance check
            for agent in agents:
                if agent["type"] == "legal_compliance":
                    agent["reason"] += " (Confidential document)"
                    agent["priority"] = 0  # Higher priority
        
        # Sort by priority
        agents.sort(key=lambda x: x["priority"])
        
        return agents
    
    def _get_agent_name(self, agent_type: str) -> str:
        """Get human-readable agent name"""
        names = {
            "document_analyzer": "Document Analyzer",
            "rag_assistant": "RAG Assistant",
            "digital_signature": "Digital Signature Agent",
            "legal_compliance": "Legal Compliance Agent",
            "financial_analysis": "Financial Analysis Agent",
            "contract_analyzer": "Contract Analyzer"
        }
        return names.get(agent_type, agent_type.replace("_", " ").title())
    
    async def _save_routing_analysis(
        self,
        db: AsyncSession,
        document_id: str,
        doc_type: str,
        confidence: float,
        characteristics: Dict[str, bool],
        assigned_agents: List[Dict],
        routing_config: Dict
    ) -> Dict[str, Any]:
        """Save routing analysis to database"""
        try:
            # Create SQL insert
            routing_id = str(uuid.uuid4())
            
            query = """
                INSERT INTO document_routing_analysis (
                    id, document_id, tenant_id, document_type, confidence_score,
                    is_signable, requires_approval, is_confidential,
                    has_financial_data, has_personal_data, has_legal_clauses,
                    assigned_agents, routing_strategy, priority_level,
                    routing_status, analyzed_at
                ) VALUES (
                    :id, :document_id, :tenant_id, :document_type, :confidence,
                    :is_signable, :requires_approval, :is_confidential,
                    :has_financial_data, :has_personal_data, :has_legal_clauses,
                    :assigned_agents, :strategy, :priority,
                    'routed', NOW()
                )
            """
            
            await db.execute(
                text(query),
                {
                    "id": routing_id,
                    "document_id": document_id,
                    "tenant_id": self.tenant_id,
                    "document_type": doc_type,
                    "confidence": confidence,
                    "is_signable": characteristics.get("is_signable", False),
                    "requires_approval": characteristics.get("requires_approval", False),
                    "is_confidential": characteristics.get("is_confidential", False),
                    "has_financial_data": characteristics.get("has_financial_data", False),
                    "has_personal_data": characteristics.get("has_personal_data", False),
                    "has_legal_clauses": characteristics.get("has_legal_clauses", False),
                    "assigned_agents": json.dumps(assigned_agents),
                    "strategy": routing_config["strategy"],
                    "priority": routing_config["priority"]
                }
            )
            
            await db.commit()
            
            return {"id": routing_id}
            
        except Exception as e:
            logger.error(f"Error saving routing analysis: {e}")
            await db.rollback()
            raise
    
    async def _create_agent_assignments(
        self,
        db: AsyncSession,
        routing_id: str,
        document_id: str,
        assigned_agents: List[Dict],
        strategy: str
    ):
        """Create agent assignment records"""
        try:
            for idx, agent in enumerate(assigned_agents):
                query = """
                    INSERT INTO document_agent_assignments (
                        id, routing_analysis_id, document_id, agent_type,
                        agent_name, assignment_reason, execution_order,
                        status, created_at
                    ) VALUES (
                        :id, :routing_id, :document_id, :agent_type,
                        :agent_name, :reason, :order,
                        'pending', NOW()
                    )
                """
                
                await db.execute(
                    text(query),
                    {
                        "id": str(uuid.uuid4()),
                        "routing_id": routing_id,
                        "document_id": document_id,
                        "agent_type": agent["type"],
                        "agent_name": agent["name"],
                        "reason": agent["reason"],
                        "order": idx if strategy == "sequential" else 0
                    }
                )
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error creating agent assignments: {e}")
            await db.rollback()
            raise