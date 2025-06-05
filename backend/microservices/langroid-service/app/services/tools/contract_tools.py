"""
Contract Analysis Tools - Specialized tools for contract processing
"""
import re
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import langroid as lr
from langroid.agent.tools.orchestration import AgentDoneTool
from langroid.pydantic_v1 import BaseModel, Field

logger = logging.getLogger(__name__)


# =====================================
# DATA MODELS
# =====================================

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClauseType(Enum):
    PAYMENT = "payment"
    DELIVERY = "delivery"
    TERMINATION = "termination"
    LIABILITY = "liability"
    CONFIDENTIALITY = "confidentiality"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DISPUTE_RESOLUTION = "dispute_resolution"
    FORCE_MAJEURE = "force_majeure"
    GOVERNING_LAW = "governing_law"
    RENEWAL = "renewal"


@dataclass
class ContractClause:
    type: ClauseType
    content: str
    location: str  # Section/paragraph reference
    risk_level: RiskLevel
    key_terms: List[str]
    confidence: float


@dataclass
class ContractEntity:
    name: str
    role: str  # "client", "contractor", "guarantor", etc.
    contact_info: Dict[str, str]
    obligations: List[str]


@dataclass
class ContractDate:
    type: str  # "start", "end", "renewal", "termination_notice"
    date: datetime
    description: str
    criticality: RiskLevel


@dataclass
class ContractRisk:
    type: str
    description: str
    level: RiskLevel
    mitigation: str
    clause_reference: str


# =====================================
# CONTRACT ANALYSIS TOOLS
# =====================================

class ExtractClausesTool(lr.agent.ToolMessage):
    """Tool for extracting specific clauses from contracts"""
    request: str = "extract_clauses"
    document_content: str = Field(..., description="Full contract text content")
    clause_types: List[str] = Field(
        default=["payment", "termination", "liability", "confidentiality"],
        description="Types of clauses to extract"
    )
    
    def handle(self) -> str:
        """Extract and analyze contract clauses"""
        try:
            clauses = self._extract_clauses_from_content(
                self.document_content, 
                self.clause_types
            )
            
            result = {
                "extracted_clauses": len(clauses),
                "clauses": [
                    {
                        "type": clause.type.value,
                        "content": clause.content[:200] + "..." if len(clause.content) > 200 else clause.content,
                        "location": clause.location,
                        "risk_level": clause.risk_level.value,
                        "key_terms": clause.key_terms,
                        "confidence": clause.confidence
                    }
                    for clause in clauses
                ],
                "high_risk_clauses": [
                    clause.type.value for clause in clauses 
                    if clause.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
                ]
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error extracting clauses: {str(e)}")
            return f"Error extracting clauses: {str(e)}"
    
    def _extract_clauses_from_content(
        self, 
        content: str, 
        clause_types: List[str]
    ) -> List[ContractClause]:
        """Extract clauses using pattern matching and NLP"""
        
        clauses = []
        
        # Define clause patterns
        clause_patterns = {
            ClauseType.PAYMENT: [
                r"payment.*?(?:due|shall be paid|payable)",
                r"invoice.*?(?:within|days|payment)",
                r"compensation.*?(?:amount|sum|fee)",
                r"(?:net|gross).*?(?:\d+.*?days|payment terms)"
            ],
            ClauseType.TERMINATION: [
                r"terminat.*?(?:agreement|contract|notice)",
                r"expir.*?(?:agreement|contract)",
                r"breach.*?(?:terminat|end|cancel)",
                r"notice.*?(?:terminat|cancellation)"
            ],
            ClauseType.LIABILITY: [
                r"liabilit.*?(?:limited|unlimited|exclude)",
                r"damages.*?(?:consequential|indirect|direct)",
                r"indemnif.*?(?:hold harmless|protect)",
                r"limitation.*?(?:liability|damages)"
            ],
            ClauseType.CONFIDENTIALITY: [
                r"confidential.*?(?:information|data|disclosure)",
                r"non.?disclosure.*?(?:agreement|obligation)",
                r"proprietary.*?(?:information|data)",
                r"trade.*?secret"
            ]
        }
        
        # Extract clauses for each requested type
        for clause_type_str in clause_types:
            try:
                clause_type = ClauseType(clause_type_str.lower())
                if clause_type in clause_patterns:
                    patterns = clause_patterns[clause_type]
                    
                    for pattern in patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
                        
                        for match in matches:
                            # Extract surrounding context (±200 chars)
                            start = max(0, match.start() - 200)
                            end = min(len(content), match.end() + 200)
                            clause_content = content[start:end].strip()
                            
                            # Calculate risk level based on keywords
                            risk_level = self._assess_clause_risk(clause_content, clause_type)
                            
                            # Extract key terms
                            key_terms = self._extract_key_terms(clause_content, clause_type)
                            
                            # Find location reference
                            location = self._find_location_reference(content, match.start())
                            
                            clause = ContractClause(
                                type=clause_type,
                                content=clause_content,
                                location=location,
                                risk_level=risk_level,
                                key_terms=key_terms,
                                confidence=0.85  # Base confidence
                            )
                            
                            clauses.append(clause)
                            
            except ValueError:
                logger.warning(f"Unknown clause type: {clause_type_str}")
                continue
        
        return clauses
    
    def _assess_clause_risk(self, content: str, clause_type: ClauseType) -> RiskLevel:
        """Assess risk level of a clause based on content and type"""
        
        content_lower = content.lower()
        
        # High-risk keywords
        high_risk_keywords = [
            "unlimited liability", "personal liability", "liquidated damages",
            "immediate termination", "no cure period", "sole discretion",
            "proprietary information", "trade secrets", "exclusive rights"
        ]
        
        # Medium-risk keywords
        medium_risk_keywords = [
            "limited liability", "reasonable efforts", "material breach",
            "30 days notice", "confidential", "intellectual property"
        ]
        
        # Critical risk patterns for specific clause types
        if clause_type == ClauseType.LIABILITY:
            if any(keyword in content_lower for keyword in ["unlimited", "personal", "joint and several"]):
                return RiskLevel.CRITICAL
        
        elif clause_type == ClauseType.TERMINATION:
            if any(keyword in content_lower for keyword in ["immediate", "without cause", "sole discretion"]):
                return RiskLevel.HIGH
        
        # General risk assessment
        if any(keyword in content_lower for keyword in high_risk_keywords):
            return RiskLevel.HIGH
        elif any(keyword in content_lower for keyword in medium_risk_keywords):
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _extract_key_terms(self, content: str, clause_type: ClauseType) -> List[str]:
        """Extract key terms from clause content"""
        
        key_terms = []
        
        # Date patterns
        date_pattern = r'\b(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{1,2}\s+(?:days?|months?|years?))\b'
        dates = re.findall(date_pattern, content, re.IGNORECASE)
        key_terms.extend(dates)
        
        # Money patterns
        money_pattern = r'\$[\d,]+(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:dollars?|usd|euros?|eur)\b'
        amounts = re.findall(money_pattern, content, re.IGNORECASE)
        key_terms.extend(amounts)
        
        # Percentage patterns
        percentage_pattern = r'\b\d+(?:\.\d+)?%\b'
        percentages = re.findall(percentage_pattern, content)
        key_terms.extend(percentages)
        
        # Specific terms by clause type
        if clause_type == ClauseType.PAYMENT:
            payment_terms = re.findall(r'\b(?:net|gross)\s+\d+\b', content, re.IGNORECASE)
            key_terms.extend(payment_terms)
        
        elif clause_type == ClauseType.TERMINATION:
            notice_terms = re.findall(r'\b\d+\s+days?\s+notice\b', content, re.IGNORECASE)
            key_terms.extend(notice_terms)
        
        return list(set(key_terms))  # Remove duplicates
    
    def _find_location_reference(self, full_content: str, position: int) -> str:
        """Find section/paragraph reference for the clause"""
        
        # Look backwards for section headers
        text_before = full_content[:position]
        
        # Section patterns
        section_patterns = [
            r'(?:section|article|clause|paragraph)\s+(\d+(?:\.\d+)*)',
            r'(\d+(?:\.\d+)*)\.\s*[A-Z]',
            r'([IVX]+)\.\s*[A-Z]'
        ]
        
        for pattern in section_patterns:
            matches = list(re.finditer(pattern, text_before, re.IGNORECASE))
            if matches:
                last_match = matches[-1]
                return f"Section {last_match.group(1)}"
        
        # Fallback: estimate paragraph number
        paragraphs = text_before.count('\n\n')
        return f"Paragraph ~{paragraphs + 1}"


class RiskAnalysisTool(lr.agent.ToolMessage):
    """Tool for comprehensive contract risk analysis"""
    request: str = "analyze_risks"
    document_content: str = Field(..., description="Full contract text content")
    risk_categories: List[str] = Field(
        default=["financial", "legal", "operational", "reputational"],
        description="Categories of risks to analyze"
    )
    
    def handle(self) -> str:
        """Perform comprehensive risk analysis"""
        try:
            risks = self._analyze_contract_risks(self.document_content, self.risk_categories)
            
            # Categorize risks by level
            critical_risks = [r for r in risks if r.level == RiskLevel.CRITICAL]
            high_risks = [r for r in risks if r.level == RiskLevel.HIGH]
            medium_risks = [r for r in risks if r.level == RiskLevel.MEDIUM]
            
            result = {
                "overall_risk_score": self._calculate_overall_risk_score(risks),
                "total_risks_identified": len(risks),
                "risk_distribution": {
                    "critical": len(critical_risks),
                    "high": len(high_risks),
                    "medium": len(medium_risks),
                    "low": len(risks) - len(critical_risks) - len(high_risks) - len(medium_risks)
                },
                "critical_risks": [
                    {
                        "type": risk.type,
                        "description": risk.description,
                        "mitigation": risk.mitigation,
                        "clause_reference": risk.clause_reference
                    }
                    for risk in critical_risks
                ],
                "recommendations": self._generate_risk_recommendations(risks),
                "requires_legal_review": len(critical_risks) > 0 or len(high_risks) > 2
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error analyzing risks: {str(e)}")
            return f"Error analyzing risks: {str(e)}"
    
    def _analyze_contract_risks(
        self, 
        content: str, 
        categories: List[str]
    ) -> List[ContractRisk]:
        """Analyze contract for various risk categories"""
        
        risks = []
        content_lower = content.lower()
        
        # Financial risks
        if "financial" in categories:
            risks.extend(self._analyze_financial_risks(content, content_lower))
        
        # Legal risks
        if "legal" in categories:
            risks.extend(self._analyze_legal_risks(content, content_lower))
        
        # Operational risks
        if "operational" in categories:
            risks.extend(self._analyze_operational_risks(content, content_lower))
        
        # Reputational risks
        if "reputational" in categories:
            risks.extend(self._analyze_reputational_risks(content, content_lower))
        
        return risks
    
    def _analyze_financial_risks(self, content: str, content_lower: str) -> List[ContractRisk]:
        """Analyze financial risks in the contract"""
        risks = []
        
        # Unlimited liability risk
        if "unlimited liability" in content_lower:
            risks.append(ContractRisk(
                type="unlimited_liability",
                description="Contract contains unlimited liability clauses",
                level=RiskLevel.CRITICAL,
                mitigation="Negotiate liability caps or exclusions",
                clause_reference="Liability section"
            ))
        
        # Payment terms risk
        if re.search(r"payment.*(?:immediately|upon demand|advance)", content_lower):
            risks.append(ContractRisk(
                type="aggressive_payment_terms",
                description="Aggressive payment terms may impact cash flow",
                level=RiskLevel.HIGH,
                mitigation="Negotiate standard payment terms (e.g., Net 30)",
                clause_reference="Payment section"
            ))
        
        # Currency risk
        if re.search(r"foreign.*currency|exchange.*rate", content_lower):
            risks.append(ContractRisk(
                type="currency_risk",
                description="Contract involves foreign currency exposure",
                level=RiskLevel.MEDIUM,
                mitigation="Consider currency hedging or USD denomination",
                clause_reference="Payment section"
            ))
        
        return risks
    
    def _analyze_legal_risks(self, content: str, content_lower: str) -> List[ContractRisk]:
        """Analyze legal risks in the contract"""
        risks = []
        
        # Governing law risk
        if not re.search(r"governing.*law|jurisdiction", content_lower):
            risks.append(ContractRisk(
                type="missing_governing_law",
                description="No clear governing law or jurisdiction specified",
                level=RiskLevel.HIGH,
                mitigation="Add governing law and jurisdiction clauses",
                clause_reference="General provisions"
            ))
        
        # Dispute resolution risk
        if "binding arbitration" in content_lower and "waive.*jury" in content_lower:
            risks.append(ContractRisk(
                type="limited_dispute_resolution",
                description="Limited dispute resolution options (arbitration only)",
                level=RiskLevel.MEDIUM,
                mitigation="Negotiate for court option or mediation first",
                clause_reference="Dispute resolution section"
            ))
        
        return risks
    
    def _analyze_operational_risks(self, content: str, content_lower: str) -> List[ContractRisk]:
        """Analyze operational risks in the contract"""
        risks = []
        
        # Performance standards risk
        if re.search(r"best.*efforts|commercially.*reasonable", content_lower):
            risks.append(ContractRisk(
                type="vague_performance_standards",
                description="Vague performance standards may lead to disputes",
                level=RiskLevel.MEDIUM,
                mitigation="Define specific, measurable performance criteria",
                clause_reference="Performance section"
            ))
        
        # Force majeure risk
        if not re.search(r"force.*majeure|act.*of.*god", content_lower):
            risks.append(ContractRisk(
                type="missing_force_majeure",
                description="No force majeure protection included",
                level=RiskLevel.MEDIUM,
                mitigation="Add comprehensive force majeure clause",
                clause_reference="General provisions"
            ))
        
        return risks
    
    def _analyze_reputational_risks(self, content: str, content_lower: str) -> List[ContractRisk]:
        """Analyze reputational risks in the contract"""
        risks = []
        
        # Confidentiality risk
        if not re.search(r"confidential|non.?disclosure", content_lower):
            risks.append(ContractRisk(
                type="missing_confidentiality",
                description="No confidentiality protections specified",
                level=RiskLevel.HIGH,
                mitigation="Add mutual confidentiality provisions",
                clause_reference="Confidentiality section"
            ))
        
        # Public disclosure risk
        if re.search(r"public.*disclosure|press.*release|marketing", content_lower):
            risks.append(ContractRisk(
                type="public_disclosure_risk",
                description="Contract may allow unwanted public disclosure",
                level=RiskLevel.MEDIUM,
                mitigation="Add approval requirements for public disclosures",
                clause_reference="Marketing/publicity section"
            ))
        
        return risks
    
    def _calculate_overall_risk_score(self, risks: List[ContractRisk]) -> float:
        """Calculate overall risk score (0-100, higher = more risky)"""
        if not risks:
            return 0.0
        
        risk_weights = {
            RiskLevel.CRITICAL: 25,
            RiskLevel.HIGH: 15,
            RiskLevel.MEDIUM: 8,
            RiskLevel.LOW: 3
        }
        
        total_score = sum(risk_weights.get(risk.level, 0) for risk in risks)
        # Normalize to 0-100 scale (assuming max ~10 risks)
        normalized_score = min(100, total_score * 2)
        
        return round(normalized_score, 1)
    
    def _generate_risk_recommendations(self, risks: List[ContractRisk]) -> List[str]:
        """Generate actionable recommendations based on identified risks"""
        recommendations = []
        
        critical_risks = [r for r in risks if r.level == RiskLevel.CRITICAL]
        high_risks = [r for r in risks if r.level == RiskLevel.HIGH]
        
        if critical_risks:
            recommendations.append("URGENT: Address critical risks before signing")
            recommendations.extend([f"- {risk.mitigation}" for risk in critical_risks])
        
        if high_risks:
            recommendations.append("HIGH PRIORITY: Negotiate high-risk items")
            recommendations.extend([f"- {risk.mitigation}" for risk in high_risks[:3]])
        
        if len(risks) > 10:
            recommendations.append("Consider comprehensive legal review due to high risk count")
        
        return recommendations


class ComplianceCheckTool(lr.agent.ToolMessage):
    """Tool for checking contract compliance with regulations"""
    request: str = "check_compliance"
    document_content: str = Field(..., description="Full contract text content")
    regulations: List[str] = Field(
        default=["gdpr", "sox", "ccpa"],
        description="Regulations to check compliance against"
    )
    jurisdiction: str = Field(default="US", description="Legal jurisdiction")
    
    def handle(self) -> str:
        """Check contract compliance with specified regulations"""
        try:
            compliance_results = self._check_regulatory_compliance(
                self.document_content, 
                self.regulations,
                self.jurisdiction
            )
            
            result = {
                "overall_compliance_score": self._calculate_compliance_score(compliance_results),
                "jurisdiction": self.jurisdiction,
                "regulations_checked": self.regulations,
                "compliance_details": compliance_results,
                "non_compliant_items": [
                    item for item in compliance_results 
                    if not item.get("compliant", True)
                ],
                "recommendations": self._generate_compliance_recommendations(compliance_results)
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error checking compliance: {str(e)}")
            return f"Error checking compliance: {str(e)}"
    
    def _check_regulatory_compliance(
        self, 
        content: str, 
        regulations: List[str],
        jurisdiction: str
    ) -> List[Dict[str, Any]]:
        """Check compliance with specific regulations"""
        
        results = []
        content_lower = content.lower()
        
        for regulation in regulations:
            if regulation.lower() == "gdpr":
                results.extend(self._check_gdpr_compliance(content, content_lower))
            elif regulation.lower() == "sox":
                results.extend(self._check_sox_compliance(content, content_lower))
            elif regulation.lower() == "ccpa":
                results.extend(self._check_ccpa_compliance(content, content_lower))
        
        return results
    
    def _check_gdpr_compliance(self, content: str, content_lower: str) -> List[Dict[str, Any]]:
        """Check GDPR compliance requirements"""
        results = []
        
        # Data processing purpose
        has_purpose = bool(re.search(r"purpose.*processing|lawful.*basis", content_lower))
        results.append({
            "regulation": "GDPR",
            "requirement": "Data processing purpose specified",
            "compliant": has_purpose,
            "details": "GDPR requires clear purpose for data processing" if not has_purpose else "Purpose specified",
            "severity": "high" if not has_purpose else "none"
        })
        
        # Data subject rights
        has_rights = bool(re.search(r"data.*subject.*rights|right.*access|right.*erasure", content_lower))
        results.append({
            "regulation": "GDPR",
            "requirement": "Data subject rights mentioned",
            "compliant": has_rights,
            "details": "GDPR requires data subject rights provision" if not has_rights else "Rights mentioned",
            "severity": "high" if not has_rights else "none"
        })
        
        # Data retention
        has_retention = bool(re.search(r"retention.*period|delete.*data|data.*retention", content_lower))
        results.append({
            "regulation": "GDPR",
            "requirement": "Data retention policy",
            "compliant": has_retention,
            "details": "GDPR requires data retention limits" if not has_retention else "Retention policy present",
            "severity": "medium" if not has_retention else "none"
        })
        
        return results
    
    def _check_sox_compliance(self, content: str, content_lower: str) -> List[Dict[str, Any]]:
        """Check Sarbanes-Oxley compliance requirements"""
        results = []
        
        # Internal controls
        has_controls = bool(re.search(r"internal.*controls|financial.*reporting|audit", content_lower))
        results.append({
            "regulation": "SOX",
            "requirement": "Internal controls mentioned",
            "compliant": has_controls,
            "details": "SOX requires internal controls for financial reporting" if not has_controls else "Controls mentioned",
            "severity": "high" if not has_controls else "none"
        })
        
        # Record retention
        has_record_retention = bool(re.search(r"record.*retention|document.*retention", content_lower))
        results.append({
            "regulation": "SOX",
            "requirement": "Record retention policy",
            "compliant": has_record_retention,
            "details": "SOX requires record retention policies" if not has_record_retention else "Retention policy present",
            "severity": "medium" if not has_record_retention else "none"
        })
        
        return results
    
    def _check_ccpa_compliance(self, content: str, content_lower: str) -> List[Dict[str, Any]]:
        """Check CCPA compliance requirements"""
        results = []
        
        # Consumer rights
        has_consumer_rights = bool(re.search(r"consumer.*rights|california.*privacy", content_lower))
        results.append({
            "regulation": "CCPA",
            "requirement": "Consumer privacy rights",
            "compliant": has_consumer_rights,
            "details": "CCPA requires consumer privacy rights" if not has_consumer_rights else "Rights mentioned",
            "severity": "high" if not has_consumer_rights else "none"
        })
        
        return results
    
    def _calculate_compliance_score(self, compliance_results: List[Dict[str, Any]]) -> float:
        """Calculate overall compliance score (0-100)"""
        if not compliance_results:
            return 100.0
        
        total_items = len(compliance_results)
        compliant_items = sum(1 for item in compliance_results if item.get("compliant", True))
        
        return round((compliant_items / total_items) * 100, 1)
    
    def _generate_compliance_recommendations(
        self, 
        compliance_results: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate recommendations for compliance improvements"""
        recommendations = []
        
        high_severity_items = [
            item for item in compliance_results 
            if not item.get("compliant", True) and item.get("severity") == "high"
        ]
        
        if high_severity_items:
            recommendations.append("CRITICAL: Address high-severity compliance issues immediately")
            for item in high_severity_items:
                recommendations.append(f"- {item['requirement']}: {item['details']}")
        
        medium_severity_items = [
            item for item in compliance_results 
            if not item.get("compliant", True) and item.get("severity") == "medium"
        ]
        
        if medium_severity_items:
            recommendations.append("IMPORTANT: Address medium-severity compliance issues")
            for item in medium_severity_items:
                recommendations.append(f"- {item['requirement']}: {item['details']}")
        
        return recommendations


class RenewalAlertTool(lr.agent.ToolMessage):
    """Tool for managing contract renewal alerts and dates"""
    request: str = "manage_renewals"
    document_content: str = Field(..., description="Full contract text content")
    current_date: Optional[str] = Field(default=None, description="Current date (YYYY-MM-DD)")
    
    def handle(self) -> str:
        """Extract and manage contract renewal dates"""
        try:
            current_dt = datetime.now()
            if self.current_date:
                try:
                    current_dt = datetime.strptime(self.current_date, "%Y-%m-%d")
                except ValueError:
                    pass
            
            contract_dates = self._extract_contract_dates(self.document_content)
            alerts = self._generate_renewal_alerts(contract_dates, current_dt)
            
            result = {
                "current_date": current_dt.strftime("%Y-%m-%d"),
                "total_dates_found": len(contract_dates),
                "contract_dates": [
                    {
                        "type": date.type,
                        "date": date.date.strftime("%Y-%m-%d"),
                        "description": date.description,
                        "criticality": date.criticality.value,
                        "days_until": (date.date - current_dt).days
                    }
                    for date in contract_dates
                ],
                "active_alerts": alerts,
                "upcoming_deadlines": [
                    alert for alert in alerts 
                    if alert["days_until"] <= 90 and alert["days_until"] >= 0
                ]
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error managing renewals: {str(e)}")
            return f"Error managing renewals: {str(e)}"
    
    def _extract_contract_dates(self, content: str) -> List[ContractDate]:
        """Extract important dates from contract content"""
        dates = []
        
        # Date patterns
        date_patterns = [
            # Standard formats: MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD
            r'\b(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})\b',
            # Written dates: January 1, 2024
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
            # Abbreviated: Jan 1, 2024
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b'
        ]
        
        # Context patterns to identify date types
        context_patterns = {
            "start": [r"effective.*date", r"commencement.*date", r"start.*date", r"begins?.*on"],
            "end": [r"expir.*date", r"end.*date", r"terminat.*date", r"expires?.*on"],
            "renewal": [r"renewal.*date", r"renew.*on", r"automatic.*renewal"],
            "termination_notice": [r"notice.*period", r"terminat.*notice", r"days?.*notice"]
        }
        
        # Find all dates with context
        for date_pattern in date_patterns:
            for match in re.finditer(date_pattern, content, re.IGNORECASE):
                date_str = match.group()
                
                # Get surrounding context (±100 chars)
                start = max(0, match.start() - 100)
                end = min(len(content), match.end() + 100)
                context = content[start:end].lower()
                
                # Determine date type from context
                date_type = "general"
                criticality = RiskLevel.LOW
                
                for type_name, patterns in context_patterns.items():
                    if any(re.search(pattern, context) for pattern in patterns):
                        date_type = type_name
                        if type_name in ["end", "termination_notice"]:
                            criticality = RiskLevel.HIGH
                        elif type_name == "renewal":
                            criticality = RiskLevel.MEDIUM
                        break
                
                # Parse date
                try:
                    parsed_date = self._parse_date(date_str)
                    if parsed_date:
                        contract_date = ContractDate(
                            type=date_type,
                            date=parsed_date,
                            description=f"{date_type.replace('_', ' ').title()}: {date_str}",
                            criticality=criticality
                        )
                        dates.append(contract_date)
                except Exception:
                    continue
        
        return dates
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats"""
        date_formats = [
            "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%m-%d-%Y",
            "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"
        ]
        
        date_str = date_str.strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None
    
    def _generate_renewal_alerts(
        self, 
        contract_dates: List[ContractDate], 
        current_date: datetime
    ) -> List[Dict[str, Any]]:
        """Generate alerts for upcoming dates"""
        alerts = []
        
        for date in contract_dates:
            days_until = (date.date - current_date).days
            
            # Generate alerts based on criticality and days remaining
            alert_thresholds = {
                RiskLevel.HIGH: [90, 60, 30, 14, 7, 1],
                RiskLevel.MEDIUM: [60, 30, 14],
                RiskLevel.LOW: [30]
            }
            
            thresholds = alert_thresholds.get(date.criticality, [30])
            
            for threshold in thresholds:
                if 0 <= days_until <= threshold:
                    urgency = "critical" if days_until <= 7 else "high" if days_until <= 30 else "medium"
                    
                    alerts.append({
                        "type": date.type,
                        "date": date.date.strftime("%Y-%m-%d"),
                        "description": date.description,
                        "days_until": days_until,
                        "urgency": urgency,
                        "action_required": self._get_action_required(date.type, days_until)
                    })
                    break  # Only one alert per date
        
        return sorted(alerts, key=lambda x: x["days_until"])
    
    def _get_action_required(self, date_type: str, days_until: int) -> str:
        """Get recommended action based on date type and timing"""
        if date_type == "end" or date_type == "renewal":
            if days_until <= 7:
                return "URGENT: Take immediate action"
            elif days_until <= 30:
                return "HIGH: Begin renewal negotiations"
            else:
                return "MEDIUM: Schedule renewal review"
        
        elif date_type == "termination_notice":
            if days_until <= 7:
                return "CRITICAL: Notice period ending soon"
            else:
                return "MEDIUM: Monitor notice requirements"
        
        return "LOW: Monitor date"


class ContractCompareTool(lr.agent.ToolMessage):
    """Tool for comparing contracts against templates or other contracts"""
    request: str = "compare_contracts"
    primary_document: str = Field(..., description="Primary contract content")
    comparison_document: str = Field(..., description="Template or comparison contract content")
    comparison_type: str = Field(default="template", description="Type of comparison: 'template' or 'contract'")
    
    def handle(self) -> str:
        """Compare contracts and identify differences"""
        try:
            comparison_result = self._compare_contracts(
                self.primary_document,
                self.comparison_document,
                self.comparison_type
            )
            
            result = {
                "comparison_type": self.comparison_type,
                "similarity_score": comparison_result["similarity_score"],
                "missing_clauses": comparison_result["missing_clauses"],
                "additional_clauses": comparison_result["additional_clauses"],
                "different_terms": comparison_result["different_terms"],
                "recommendations": comparison_result["recommendations"],
                "overall_assessment": self._get_overall_assessment(comparison_result)
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error comparing contracts: {str(e)}")
            return f"Error comparing contracts: {str(e)}"
    
    def _compare_contracts(
        self, 
        primary: str, 
        comparison: str, 
        comparison_type: str
    ) -> Dict[str, Any]:
        """Compare two contract documents"""
        
        # Extract key sections from both documents
        primary_sections = self._extract_sections(primary)
        comparison_sections = self._extract_sections(comparison)
        
        # Find missing and additional sections
        primary_keys = set(primary_sections.keys())
        comparison_keys = set(comparison_sections.keys())
        
        missing_clauses = list(comparison_keys - primary_keys)
        additional_clauses = list(primary_keys - comparison_keys)
        
        # Compare common sections
        common_sections = primary_keys & comparison_keys
        different_terms = []
        
        for section in common_sections:
            differences = self._compare_section_content(
                primary_sections[section],
                comparison_sections[section],
                section
            )
            different_terms.extend(differences)
        
        # Calculate similarity score
        similarity_score = self._calculate_similarity_score(
            primary_sections, comparison_sections
        )
        
        # Generate recommendations
        recommendations = self._generate_comparison_recommendations(
            missing_clauses, additional_clauses, different_terms, comparison_type
        )
        
        return {
            "similarity_score": similarity_score,
            "missing_clauses": missing_clauses,
            "additional_clauses": additional_clauses,
            "different_terms": different_terms,
            "recommendations": recommendations
        }
    
    def _extract_sections(self, content: str) -> Dict[str, str]:
        """Extract main sections from contract content"""
        sections = {}
        
        # Common contract section patterns
        section_patterns = [
            r'(?:section|article|clause)\s+\d+[:\-\.]?\s*([^:\n]+)',
            r'(\d+\.\s*[A-Z][^:\n]+)',
            r'([A-Z][A-Z\s]+):',  # ALL CAPS headers
        ]
        
        current_section = "Preamble"
        current_content = ""
        
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line is a section header
            is_header = False
            for pattern in section_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    # Save previous section
                    if current_content.strip():
                        sections[current_section] = current_content.strip()
                    
                    # Start new section
                    current_section = match.group(1).strip()
                    current_content = ""
                    is_header = True
                    break
            
            if not is_header:
                current_content += " " + line
        
        # Save final section
        if current_content.strip():
            sections[current_section] = current_content.strip()
        
        return sections
    
    def _compare_section_content(
        self, 
        primary_content: str, 
        comparison_content: str, 
        section_name: str
    ) -> List[Dict[str, Any]]:
        """Compare content of similar sections"""
        differences = []
        
        primary_lower = primary_content.lower()
        comparison_lower = comparison_content.lower()
        
        # Check for key term differences
        key_terms = [
            "liability", "termination", "payment", "confidential",
            "intellectual property", "governing law", "dispute"
        ]
        
        for term in key_terms:
            primary_has = term in primary_lower
            comparison_has = term in comparison_lower
            
            if primary_has != comparison_has:
                differences.append({
                    "section": section_name,
                    "type": "missing_term" if comparison_has and not primary_has else "additional_term",
                    "term": term,
                    "description": f"Term '{term}' {'missing from' if comparison_has else 'added to'} primary document"
                })
        
        # Check for numerical differences (amounts, dates, percentages)
        primary_numbers = re.findall(r'\$?[\d,]+(?:\.\d{2})?|\d+%|\d+\s+days?', primary_content)
        comparison_numbers = re.findall(r'\$?[\d,]+(?:\.\d{2})?|\d+%|\d+\s+days?', comparison_content)
        
        if set(primary_numbers) != set(comparison_numbers):
            differences.append({
                "section": section_name,
                "type": "numerical_difference",
                "primary_values": primary_numbers,
                "comparison_values": comparison_numbers,
                "description": "Numerical values differ between documents"
            })
        
        return differences
    
    def _calculate_similarity_score(
        self, 
        primary_sections: Dict[str, str], 
        comparison_sections: Dict[str, str]
    ) -> float:
        """Calculate overall similarity score between documents"""
        
        all_sections = set(primary_sections.keys()) | set(comparison_sections.keys())
        if not all_sections:
            return 0.0
        
        common_sections = set(primary_sections.keys()) & set(comparison_sections.keys())
        section_coverage = len(common_sections) / len(all_sections)
        
        # Simple content similarity (could be enhanced with more sophisticated NLP)
        content_similarity = 0.0
        if common_sections:
            similarities = []
            for section in common_sections:
                # Basic word overlap similarity
                primary_words = set(primary_sections[section].lower().split())
                comparison_words = set(comparison_sections[section].lower().split())
                
                if primary_words or comparison_words:
                    overlap = len(primary_words & comparison_words)
                    total = len(primary_words | comparison_words)
                    similarities.append(overlap / total if total > 0 else 0)
            
            content_similarity = sum(similarities) / len(similarities) if similarities else 0
        
        # Weighted combination
        overall_similarity = (section_coverage * 0.4) + (content_similarity * 0.6)
        return round(overall_similarity * 100, 1)
    
    def _generate_comparison_recommendations(
        self, 
        missing_clauses: List[str], 
        additional_clauses: List[str], 
        different_terms: List[Dict[str, Any]], 
        comparison_type: str
    ) -> List[str]:
        """Generate recommendations based on comparison results"""
        recommendations = []
        
        if comparison_type == "template":
            if missing_clauses:
                recommendations.append("Consider adding missing standard clauses:")
                recommendations.extend([f"  - {clause}" for clause in missing_clauses[:5]])
            
            if additional_clauses:
                recommendations.append("Review additional clauses for necessity:")
                recommendations.extend([f"  - {clause}" for clause in additional_clauses[:5]])
        
        else:  # contract comparison
            if missing_clauses:
                recommendations.append("Clauses present in comparison but missing here:")
                recommendations.extend([f"  - {clause}" for clause in missing_clauses[:5]])
        
        if different_terms:
            recommendations.append("Review terms that differ between documents:")
            for diff in different_terms[:3]:
                recommendations.append(f"  - {diff['description']}")
        
        return recommendations
    
    def _get_overall_assessment(self, comparison_result: Dict[str, Any]) -> str:
        """Get overall assessment of the comparison"""
        similarity = comparison_result["similarity_score"]
        missing_count = len(comparison_result["missing_clauses"])
        different_count = len(comparison_result["different_terms"])
        
        if similarity >= 90 and missing_count == 0:
            return "Excellent alignment with comparison document"
        elif similarity >= 75 and missing_count <= 2:
            return "Good alignment with minor differences"
        elif similarity >= 50:
            return "Moderate alignment with several differences requiring review"
        else:
            return "Significant differences requiring comprehensive review"