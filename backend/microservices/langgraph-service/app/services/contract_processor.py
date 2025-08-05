"""
Contract Processor Service - Core logic for contract analysis
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import json

from app.core.cag_engine import CAGEngine
from app.api.contract_intelligence import (
    ContractClause, ContractObligation, ContractRisk,
    ContractComparisonType
)

logger = logging.getLogger(__name__)


class ContractProcessor:
    """Process and analyze contracts using CAG"""
    
    def __init__(self, cag_engine: CAGEngine):
        self.cag_engine = cag_engine
        
        # Contract analysis patterns
        self.clause_patterns = {
            "termination": r"(terminat\w+|end\w+|expir\w+|cancel\w+)",
            "payment": r"(pay\w+|fee\s|cost\s|price\s|invoice\s)",
            "liability": r"(liabil\w+|indemni\w+|damage\s|loss\w+)",
            "intellectual_property": r"(intellectual property|copyright|patent|trademark|proprietary|ownership)",
            "confidentiality": r"(confident\w+|non-disclosure|proprietary|secret)",
            "warranty": r"(warrant\w+|guarantee\w+|represent\w+)",
            "force_majeure": r"(force majeure|act of god|unforeseeable)",
            "dispute": r"(dispute|arbitrat\w+|mediat\w+|litigation)",
            "assignment": r"(assign\w+|transfer\w+|delegate\w+)",
            "governing_law": r"(governing law|jurisdiction|applicable law)"
        }
    
    async def full_analysis(
        self,
        contract_content: str,
        industry: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        party_perspective: Optional[str] = None,
        custom_concerns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Perform comprehensive contract analysis"""
        
        logger.info("Starting full contract analysis")
        
        # Build analysis context
        context_parts = ["Analyze this contract comprehensively."]
        if industry:
            context_parts.append(f"Industry context: {industry}")
        if jurisdiction:
            context_parts.append(f"Jurisdiction: {jurisdiction}")
        if party_perspective:
            context_parts.append(f"Analyze from the perspective of: {party_perspective}")
        if custom_concerns:
            context_parts.append(f"Pay special attention to: {', '.join(custom_concerns)}")
        
        context = " ".join(context_parts)
        
        # Use CAG for comprehensive analysis
        query = f"""
        {context}
        
        Provide a comprehensive analysis including:
        1. Executive summary of the contract
        2. Key terms and conditions with risk assessment
        3. All party obligations with deadlines
        4. Potential risks and unfavorable terms
        5. Financial terms and payment obligations
        6. Termination conditions
        7. Liability and indemnification clauses
        8. Intellectual property provisions
        9. Recommendations for negotiation or acceptance
        
        Contract text:
        {contract_content}
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"contract_analysis": True},
            metadata={"analysis_type": "full_contract_analysis"}
        )
        
        # Extract structured information from CAG response
        analysis_text = cag_response.response
        
        # Parse the response into structured components
        result = {
            "summary": self._extract_section(analysis_text, "Executive summary", "Key terms"),
            "key_clauses": await self._extract_key_clauses(contract_content, analysis_text),
            "obligations": await self._extract_obligations_from_analysis(analysis_text, party_perspective),
            "risks": await self._extract_risks_from_analysis(analysis_text),
            "deadlines": self._extract_deadlines_from_text(contract_content),
            "financial_terms": await self._extract_financial_terms(contract_content, analysis_text),
            "recommendations": self._extract_recommendations(analysis_text),
            "total_clauses": len(self._split_into_clauses(contract_content)),
            "analysis_depth": "comprehensive",
            "confidence_score": cag_response.confidence_score
        }
        
        return result
    
    async def extract_key_terms(self, contract_content: str) -> Dict[str, Any]:
        """Extract and analyze key contractual terms"""
        
        query = """
        Extract and analyze all key terms from this contract. For each key term:
        1. Identify the clause type (payment, liability, termination, etc.)
        2. Quote the exact text
        3. Assess the risk level (low, medium, high, critical)
        4. Explain why it's important
        5. Provide any recommendations
        
        Focus on terms that create obligations, risks, or important rights.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        # Parse response into structured clauses
        key_clauses = await self._extract_key_clauses(contract_content, cag_response.response)
        
        return {
            "key_clauses": key_clauses,
            "total_clauses_analyzed": len(key_clauses),
            "summary": self._generate_terms_summary(key_clauses),
            "confidence_score": cag_response.confidence_score
        }
    
    async def extract_obligations(
        self,
        contract_content: str,
        party_perspective: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract all contractual obligations"""
        
        perspective_context = f"from the perspective of {party_perspective}" if party_perspective else "for all parties"
        
        query = f"""
        Extract all contractual obligations {perspective_context}. For each obligation:
        1. Identify which party is obligated
        2. Describe the specific obligation
        3. Extract any deadlines or time constraints
        4. Note any conditions or prerequisites
        5. Identify penalties for non-compliance
        6. Assess the priority (low, medium, high, critical)
        
        Be thorough and include both explicit and implied obligations.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        obligations = await self._extract_obligations_from_analysis(
            cag_response.response,
            party_perspective
        )
        
        return {
            "obligations": obligations,
            "total_obligations": len(obligations),
            "party_summary": self._summarize_obligations_by_party(obligations),
            "critical_obligations": [o for o in obligations if o.priority == "critical"],
            "confidence_score": cag_response.confidence_score
        }
    
    async def assess_risks(
        self,
        contract_content: str,
        industry: Optional[str] = None,
        custom_concerns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Assess risks in the contract"""
        
        context_parts = ["Perform a comprehensive risk assessment of this contract."]
        if industry:
            context_parts.append(f"Consider industry-specific risks for: {industry}")
        if custom_concerns:
            context_parts.append(f"Pay special attention to: {', '.join(custom_concerns)}")
        
        query = f"""
        {' '.join(context_parts)}
        
        For each risk identified:
        1. Categorize the risk type
        2. Describe the risk in detail
        3. Assess severity (low, medium, high, critical)
        4. Estimate likelihood (low, medium, high)
        5. Identify which contract clauses create or relate to this risk
        6. Suggest mitigation strategies
        
        Consider legal, financial, operational, and reputational risks.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        risks = await self._extract_risks_from_analysis(cag_response.response)
        
        return {
            "risks": risks,
            "total_risks": len(risks),
            "critical_risks": [r for r in risks if r.severity == "critical"],
            "risk_summary": self._generate_risk_summary(risks),
            "mitigation_plan": self._create_mitigation_plan(risks),
            "confidence_score": cag_response.confidence_score
        }
    
    async def extract_deadlines(self, contract_content: str) -> Dict[str, Any]:
        """Extract all deadlines and time-sensitive obligations"""
        
        query = """
        Extract all deadlines, milestones, and time-sensitive obligations from this contract.
        Include:
        1. Payment deadlines
        2. Delivery dates
        3. Notice periods
        4. Contract duration and renewal dates
        5. Performance milestones
        6. Cure periods for breaches
        7. Any other time-bound obligations
        
        For each deadline, specify:
        - The exact date or time period
        - What must be done
        - Consequences of missing the deadline
        - Which party is responsible
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        deadlines = self._extract_deadlines_from_text(contract_content)
        enhanced_deadlines = await self._enhance_deadlines_with_cag(deadlines, cag_response.response)
        
        return {
            "deadlines": enhanced_deadlines,
            "total_deadlines": len(enhanced_deadlines),
            "upcoming_deadlines": self._filter_upcoming_deadlines(enhanced_deadlines),
            "critical_dates": self._identify_critical_dates(enhanced_deadlines),
            "timeline_summary": self._create_timeline_summary(enhanced_deadlines),
            "confidence_score": cag_response.confidence_score
        }
    
    async def analyze_financial_terms(self, contract_content: str) -> Dict[str, Any]:
        """Analyze all financial aspects of the contract"""
        
        query = """
        Analyze all financial terms and monetary obligations in this contract:
        1. Base fees and pricing structure
        2. Payment terms and schedules
        3. Penalties and late fees
        4. Discounts and incentives
        5. Price adjustment mechanisms
        6. Currency and exchange rate provisions
        7. Tax responsibilities
        8. Insurance requirements
        9. Financial guarantees or bonds
        10. Total contract value estimation
        
        Provide specific amounts, percentages, and calculations where mentioned.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        financial_terms = await self._extract_financial_terms(contract_content, cag_response.response)
        
        return {
            "financial_terms": financial_terms,
            "total_value_estimate": financial_terms.get("total_value"),
            "payment_schedule": financial_terms.get("payment_schedule"),
            "financial_risks": financial_terms.get("financial_risks"),
            "cost_breakdown": financial_terms.get("cost_breakdown"),
            "confidence_score": cag_response.confidence_score
        }
    
    async def analyze_termination_clauses(self, contract_content: str) -> Dict[str, Any]:
        """Analyze termination and exit provisions"""
        
        query = """
        Analyze all termination and exit provisions in this contract:
        1. Termination for convenience clauses
        2. Termination for cause conditions
        3. Notice requirements for termination
        4. Post-termination obligations
        5. Survival clauses
        6. Return of property/data requirements
        7. Final payment provisions
        8. Non-compete/non-solicitation that survive termination
        
        Assess the balance and fairness of termination rights between parties.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        return await self._parse_termination_analysis(cag_response.response)
    
    async def analyze_liability(self, contract_content: str) -> Dict[str, Any]:
        """Analyze liability allocation and limitations"""
        
        query = """
        Analyze liability provisions in this contract:
        1. Liability limitations and caps
        2. Indemnification clauses
        3. Insurance requirements
        4. Warranty disclaimers
        5. Consequential damages exclusions
        6. Gross negligence and willful misconduct exceptions
        7. Third-party liability
        8. Mutual vs one-sided provisions
        
        Assess the risk allocation between parties and identify any imbalances.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        return await self._parse_liability_analysis(cag_response.response)
    
    async def analyze_ip_clauses(self, contract_content: str) -> Dict[str, Any]:
        """Analyze intellectual property provisions"""
        
        query = """
        Analyze all intellectual property provisions in this contract:
        1. Ownership of pre-existing IP
        2. Ownership of newly created IP
        3. License grants and restrictions
        4. Rights to derivatives and improvements
        5. Moral rights waivers
        6. Open source software provisions
        7. IP indemnification
        8. Confidentiality and trade secrets
        
        Identify who owns what and any potential IP risks.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        return await self._parse_ip_analysis(cag_response.response)
    
    async def check_compliance(
        self,
        contract_content: str,
        jurisdiction: Optional[str] = None,
        industry: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check contract compliance with regulations"""
        
        context_parts = ["Check this contract for regulatory compliance."]
        if jurisdiction:
            context_parts.append(f"Jurisdiction: {jurisdiction}")
        if industry:
            context_parts.append(f"Industry regulations for: {industry}")
        
        query = f"""
        {' '.join(context_parts)}
        
        Review for compliance with:
        1. General contract law requirements
        2. Industry-specific regulations
        3. Data protection laws (GDPR, CCPA, etc.)
        4. Employment law (if applicable)
        5. Consumer protection laws
        6. Anti-corruption and bribery laws
        7. Export control regulations
        8. Accessibility requirements
        
        Identify any clauses that may violate regulations or create compliance risks.
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        return await self._parse_compliance_analysis(cag_response.response)
    
    async def compare_contracts(
        self,
        contracts: Dict[str, str],
        comparison_type: ContractComparisonType,
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Compare multiple contracts"""
        
        if comparison_type == ContractComparisonType.CLAUSE_COMPARISON:
            return await self._compare_clauses(contracts, focus_areas)
        elif comparison_type == ContractComparisonType.TERM_DIFFERENCES:
            return await self._compare_terms(contracts)
        elif comparison_type == ContractComparisonType.RISK_COMPARISON:
            return await self._compare_risks(contracts)
        elif comparison_type == ContractComparisonType.OBLIGATION_CHANGES:
            return await self._compare_obligations(contracts)
        elif comparison_type == ContractComparisonType.FINANCIAL_IMPACT:
            return await self._compare_financial_impact(contracts)
        else:
            raise ValueError(f"Unknown comparison type: {comparison_type}")
    
    async def get_industry_templates(self, industry: str) -> Dict[str, Any]:
        """Get industry-specific contract templates and best practices"""
        
        query = f"""
        Provide standard contract templates and best practices for the {industry} industry.
        Include:
        1. Essential clauses that should be present
        2. Industry-specific terms and conditions
        3. Common negotiation points
        4. Red flags to watch for
        5. Typical contract structure
        6. Industry-standard risk allocations
        7. Recommended protective clauses
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"industry_templates": True}
        )
        
        return await self._parse_template_recommendations(cag_response.response, industry)
    
    async def validate_contract(
        self,
        contract_content: str,
        custom_rules: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Validate contract against best practices and custom rules"""
        
        base_rules = [
            "Contract must have clear parties identification",
            "Must include governing law clause",
            "Must have dispute resolution mechanism",
            "Payment terms must be clearly defined",
            "Termination conditions must be specified",
            "Must include limitation of liability",
            "Confidentiality provisions required",
            "Must be dated and signed by all parties"
        ]
        
        rules = base_rules + (custom_rules or [])
        
        query = f"""
        Validate this contract against the following rules:
        {json.dumps(rules, indent=2)}
        
        For each rule:
        1. Check if the contract satisfies the rule
        2. If not, explain what's missing
        3. Suggest specific language to add
        4. Rate the importance of the violation
        """
        
        cag_response = await self.cag_engine.process(
            query=query,
            context={"document": contract_content}
        )
        
        return await self._parse_validation_results(cag_response.response, rules)
    
    # Helper methods
    def _extract_section(self, text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between two markers"""
        try:
            start = text.lower().find(start_marker.lower())
            if start == -1:
                return ""
            
            end = text.lower().find(end_marker.lower(), start + len(start_marker))
            if end == -1:
                # Take next 500 characters if no end marker
                return text[start:start+500].strip()
            
            return text[start:end].strip()
        except:
            return ""
    
    async def _extract_key_clauses(self, contract_content: str, analysis_text: str) -> List[ContractClause]:
        """Extract key clauses from contract and analysis"""
        clauses = []
        
        # Extract clauses based on patterns
        for clause_type, pattern in self.clause_patterns.items():
            matches = re.finditer(pattern, contract_content, re.IGNORECASE)
            for match in matches:
                # Get surrounding context (200 chars before and after)
                start = max(0, match.start() - 200)
                end = min(len(contract_content), match.end() + 200)
                clause_text = contract_content[start:end].strip()
                
                # Determine risk level from analysis
                risk_level = self._assess_clause_risk(clause_type, clause_text, analysis_text)
                
                clause = ContractClause(
                    clause_type=clause_type.replace("_", " ").title(),
                    text=clause_text,
                    risk_level=risk_level,
                    explanation=self._get_clause_explanation(clause_type, analysis_text)
                )
                clauses.append(clause)
        
        return clauses[:20]  # Limit to top 20 clauses
    
    def _assess_clause_risk(self, clause_type: str, clause_text: str, analysis_text: str) -> str:
        """Assess risk level of a clause"""
        # Check for risk indicators in analysis
        high_risk_indicators = ["critical", "severe", "dangerous", "unacceptable", "highly unfavorable"]
        medium_risk_indicators = ["concerning", "problematic", "unfavorable", "risky", "caution"]
        
        clause_section = self._find_clause_in_analysis(clause_type, analysis_text)
        
        for indicator in high_risk_indicators:
            if indicator in clause_section.lower():
                return "high"
        
        for indicator in medium_risk_indicators:
            if indicator in clause_section.lower():
                return "medium"
        
        return "low"
    
    def _find_clause_in_analysis(self, clause_type: str, analysis_text: str) -> str:
        """Find clause discussion in analysis text"""
        # Search for clause type in analysis
        search_term = clause_type.replace("_", " ")
        index = analysis_text.lower().find(search_term.lower())
        
        if index != -1:
            # Return surrounding context
            start = max(0, index - 100)
            end = min(len(analysis_text), index + 300)
            return analysis_text[start:end]
        
        return ""
    
    def _get_clause_explanation(self, clause_type: str, analysis_text: str) -> str:
        """Get explanation for a clause from analysis"""
        clause_section = self._find_clause_in_analysis(clause_type, analysis_text)
        if clause_section:
            # Extract first complete sentence
            sentences = clause_section.split(".")
            if sentences:
                return sentences[0].strip() + "."
        return f"Standard {clause_type.replace('_', ' ')} clause"
    
    async def _extract_obligations_from_analysis(
        self,
        analysis_text: str,
        party_perspective: Optional[str] = None
    ) -> List[ContractObligation]:
        """Extract obligations from CAG analysis"""
        obligations = []
        
        # Parse obligations section
        obligations_section = self._extract_section(analysis_text, "obligations", "risks")
        if not obligations_section:
            obligations_section = analysis_text
        
        # Split into individual obligations
        lines = obligations_section.split("\n")
        current_party = party_perspective or "Party"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract party if mentioned
            party_match = re.search(r"(Party A|Party B|Buyer|Seller|Client|Vendor|Contractor|Customer)", line, re.IGNORECASE)
            if party_match:
                current_party = party_match.group(1)
            
            # Extract deadline if mentioned
            deadline = None
            deadline_match = re.search(r"(within \d+ days|by [A-Za-z]+ \d+|before [A-Za-z]+ \d+|monthly|annually)", line, re.IGNORECASE)
            if deadline_match:
                deadline = datetime.now()  # Placeholder - would parse actual date
            
            # Determine priority
            priority = "medium"
            if any(word in line.lower() for word in ["must", "shall", "critical", "immediately"]):
                priority = "high"
            elif any(word in line.lower() for word in ["may", "should", "recommended"]):
                priority = "low"
            
            if len(line) > 20:  # Filter out very short lines
                obligation = ContractObligation(
                    party=current_party,
                    obligation=line,
                    deadline=deadline,
                    priority=priority
                )
                obligations.append(obligation)
        
        return obligations[:30]  # Limit to 30 obligations
    
    async def _extract_risks_from_analysis(self, analysis_text: str) -> List[ContractRisk]:
        """Extract risks from CAG analysis"""
        risks = []
        
        # Parse risks section
        risks_section = self._extract_section(analysis_text, "risks", "recommendations")
        if not risks_section:
            risks_section = self._extract_section(analysis_text, "risk", "financial")
        
        # Common risk patterns
        risk_patterns = {
            "liability": "Unlimited liability exposure",
            "termination": "Unfavorable termination conditions",
            "payment": "Payment terms risk",
            "intellectual_property": "IP ownership concerns",
            "compliance": "Regulatory compliance risk",
            "performance": "Performance obligation risk",
            "force_majeure": "Limited force majeure protection",
            "dispute": "Unfavorable dispute resolution"
        }
        
        for risk_type, default_desc in risk_patterns.items():
            if risk_type in risks_section.lower():
                # Extract specific risk description
                risk_desc = self._find_clause_in_analysis(risk_type, risks_section)
                if not risk_desc:
                    risk_desc = default_desc
                
                # Determine severity
                severity = "medium"
                if any(word in risk_desc.lower() for word in ["critical", "severe", "high risk", "significant"]):
                    severity = "high"
                elif any(word in risk_desc.lower() for word in ["low", "minimal", "minor"]):
                    severity = "low"
                
                risk = ContractRisk(
                    risk_type=risk_type.replace("_", " ").title(),
                    description=risk_desc[:200],  # Limit description length
                    severity=severity,
                    affected_clauses=[risk_type],
                    mitigation_suggestions=[f"Review and negotiate {risk_type} terms"],
                    likelihood="medium"
                )
                risks.append(risk)
        
        return risks
    
    def _extract_deadlines_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract deadline mentions from contract text"""
        deadlines = []
        
        # Patterns for deadlines
        deadline_patterns = [
            r"within (\d+) (days|weeks|months|years)",
            r"by ([A-Za-z]+ \d+, \d{4})",
            r"before ([A-Za-z]+ \d+, \d{4})",
            r"no later than ([A-Za-z]+ \d+, \d{4})",
            r"(monthly|quarterly|annually|yearly)",
            r"(\d+) days after",
            r"(\d+) days before"
        ]
        
        for pattern in deadline_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                deadline = {
                    "text": match.group(0),
                    "context": text[max(0, match.start()-50):min(len(text), match.end()+50)],
                    "type": "deadline",
                    "position": match.start()
                }
                deadlines.append(deadline)
        
        return deadlines
    
    async def _extract_financial_terms(self, contract_content: str, analysis_text: str) -> Dict[str, Any]:
        """Extract financial terms from contract"""
        financial_data = {
            "base_fees": [],
            "payment_terms": [],
            "penalties": [],
            "total_value": None,
            "currency": "USD",  # Default
            "payment_schedule": [],
            "financial_risks": [],
            "cost_breakdown": {}
        }
        
        # Extract monetary amounts
        amount_pattern = r"\$[\d,]+\.?\d*|\d+\.?\d*\s*(USD|EUR|GBP)"
        amounts = re.findall(amount_pattern, contract_content)
        
        if amounts:
            financial_data["base_fees"] = amounts[:5]  # Top 5 amounts
        
        # Extract payment terms from analysis
        payment_section = self._extract_section(analysis_text, "payment", "deadline")
        if payment_section:
            financial_data["payment_terms"] = [payment_section[:200]]
        
        # Look for penalties
        penalty_pattern = r"(penalty|late fee|interest).*?\$[\d,]+\.?\d*"
        penalties = re.findall(penalty_pattern, contract_content, re.IGNORECASE)
        financial_data["penalties"] = penalties[:3]
        
        return financial_data
    
    def _extract_recommendations(self, analysis_text: str) -> List[str]:
        """Extract recommendations from analysis"""
        recommendations = []
        
        # Find recommendations section
        rec_section = self._extract_section(analysis_text, "recommendation", "")
        if not rec_section:
            rec_section = self._extract_section(analysis_text, "suggest", "")
        
        if rec_section:
            # Split into individual recommendations
            lines = rec_section.split("\n")
            for line in lines:
                line = line.strip()
                if line and len(line) > 20:
                    # Clean up numbering
                    line = re.sub(r"^\d+\.\s*", "", line)
                    line = re.sub(r"^-\s*", "", line)
                    recommendations.append(line)
        
        return recommendations[:10]  # Top 10 recommendations
    
    def _split_into_clauses(self, contract_content: str) -> List[str]:
        """Split contract into individual clauses"""
        # Simple clause splitting by numbering or paragraphs
        clauses = []
        
        # Try numbered clauses first
        numbered_pattern = r"\n\s*\d+\.\s+"
        parts = re.split(numbered_pattern, contract_content)
        
        if len(parts) > 5:
            clauses = parts[1:]  # Skip preamble
        else:
            # Fall back to paragraph splitting
            clauses = contract_content.split("\n\n")
        
        # Filter out very short clauses
        return [c for c in clauses if len(c.strip()) > 50]
    
    def _generate_terms_summary(self, clauses: List[ContractClause]) -> str:
        """Generate summary of key terms"""
        if not clauses:
            return "No key terms identified"
        
        high_risk = len([c for c in clauses if c.risk_level in ["high", "critical"]])
        medium_risk = len([c for c in clauses if c.risk_level == "medium"])
        
        return f"Identified {len(clauses)} key terms: {high_risk} high-risk, {medium_risk} medium-risk clauses requiring attention"
    
    def _summarize_obligations_by_party(self, obligations: List[ContractObligation]) -> Dict[str, int]:
        """Summarize obligations by party"""
        summary = {}
        for obligation in obligations:
            party = obligation.party
            summary[party] = summary.get(party, 0) + 1
        return summary
    
    def _generate_risk_summary(self, risks: List[ContractRisk]) -> str:
        """Generate risk summary"""
        if not risks:
            return "No significant risks identified"
        
        critical = len([r for r in risks if r.severity in ["critical", "high"]])
        return f"Identified {len(risks)} risks, {critical} require immediate attention"
    
    def _create_mitigation_plan(self, risks: List[ContractRisk]) -> List[Dict[str, Any]]:
        """Create risk mitigation plan"""
        plan = []
        for risk in risks:
            if risk.severity in ["critical", "high"]:
                plan.append({
                    "risk": risk.risk_type,
                    "priority": "immediate",
                    "actions": risk.mitigation_suggestions
                })
        return plan
    
    def _filter_upcoming_deadlines(self, deadlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter deadlines occurring in next 30 days"""
        # In real implementation, would parse dates and compare
        return deadlines[:5]  # Return first 5 as placeholder
    
    def _identify_critical_dates(self, deadlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify critical dates"""
        critical = []
        for deadline in deadlines:
            if any(word in deadline.get("context", "").lower() for word in ["terminate", "expire", "renew", "payment due"]):
                critical.append(deadline)
        return critical
    
    def _create_timeline_summary(self, deadlines: List[Dict[str, Any]]) -> str:
        """Create timeline summary"""
        if not deadlines:
            return "No specific deadlines identified"
        return f"Contract contains {len(deadlines)} time-sensitive obligations and deadlines"
    
    async def _enhance_deadlines_with_cag(
        self,
        basic_deadlines: List[Dict[str, Any]],
        cag_analysis: str
    ) -> List[Dict[str, Any]]:
        """Enhance basic deadline extraction with CAG analysis"""
        enhanced = []
        
        for deadline in basic_deadlines:
            # Find context in CAG analysis
            context = self._find_clause_in_analysis(deadline["text"], cag_analysis)
            
            enhanced_deadline = deadline.copy()
            enhanced_deadline.update({
                "importance": "high" if "critical" in context.lower() else "medium",
                "party_responsible": self._extract_responsible_party(context),
                "consequences": self._extract_consequences(context)
            })
            enhanced.append(enhanced_deadline)
        
        return enhanced
    
    def _extract_responsible_party(self, text: str) -> str:
        """Extract responsible party from text"""
        party_match = re.search(r"(Party A|Party B|Buyer|Seller|Client|Vendor)", text, re.IGNORECASE)
        return party_match.group(1) if party_match else "Contracting Party"
    
    def _extract_consequences(self, text: str) -> str:
        """Extract consequences from text"""
        if "penalty" in text.lower():
            return "Financial penalties may apply"
        elif "terminate" in text.lower():
            return "May result in contract termination"
        elif "breach" in text.lower():
            return "Constitutes breach of contract"
        return "See contract for specific consequences"
    
    # Comparison methods
    async def _compare_clauses(
        self,
        contracts: Dict[str, str],
        focus_areas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Compare clauses across contracts"""
        
        contract_ids = list(contracts.keys())
        comparison_query = f"""
        Compare the following contracts clause by clause:
        
        {' '.join([f'Contract {id}: {content[:500]}...' for id, content in contracts.items()])}
        
        Focus on:
        1. Clauses present in some contracts but missing in others
        2. Similar clauses with different terms
        3. Risk allocation differences
        4. Favorable vs unfavorable variations
        
        {'Pay special attention to: ' + ', '.join(focus_areas) if focus_areas else ''}
        """
        
        cag_response = await self.cag_engine.process(
            query=comparison_query,
            context={"comparison": True}
        )
        
        return {
            "differences": self._parse_differences(cag_response.response),
            "similarities": self._parse_similarities(cag_response.response),
            "summary": self._extract_section(cag_response.response, "summary", "differences")
        }
    
    async def _compare_terms(self, contracts: Dict[str, str]) -> Dict[str, Any]:
        """Compare specific terms across contracts"""
        # Implementation similar to _compare_clauses but focused on terms
        pass
    
    async def _compare_risks(self, contracts: Dict[str, str]) -> Dict[str, Any]:
        """Compare risk profiles across contracts"""
        # Implementation for risk comparison
        pass
    
    async def _compare_obligations(self, contracts: Dict[str, str]) -> Dict[str, Any]:
        """Compare obligations across contracts"""
        # Implementation for obligation comparison
        pass
    
    async def _compare_financial_impact(self, contracts: Dict[str, str]) -> Dict[str, Any]:
        """Compare financial impact across contracts"""
        # Implementation for financial comparison
        pass
    
    def _parse_differences(self, text: str) -> List[Dict[str, Any]]:
        """Parse differences from comparison text"""
        differences = []
        diff_section = self._extract_section(text, "differences", "similarities")
        
        if diff_section:
            lines = diff_section.split("\n")
            for line in lines:
                if line.strip() and len(line) > 20:
                    differences.append({
                        "description": line.strip(),
                        "impact": "medium"  # Would be determined by analysis
                    })
        
        return differences[:10]
    
    def _parse_similarities(self, text: str) -> List[Dict[str, Any]]:
        """Parse similarities from comparison text"""
        similarities = []
        sim_section = self._extract_section(text, "similarities", "recommendation")
        
        if sim_section:
            lines = sim_section.split("\n")
            for line in lines:
                if line.strip() and len(line) > 20:
                    similarities.append({
                        "description": line.strip(),
                        "present_in": "all contracts"  # Would be determined by analysis
                    })
        
        return similarities[:10]
    
    # Additional parsing methods
    async def _parse_termination_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse termination clause analysis"""
        return {
            "termination_rights": self._extract_section(analysis, "termination", "notice"),
            "notice_requirements": self._extract_section(analysis, "notice", "post-termination"),
            "post_termination": self._extract_section(analysis, "post-termination", "survival"),
            "survival_clauses": self._extract_section(analysis, "survival", ""),
            "balance_assessment": "Requires review"  # Would be extracted from analysis
        }
    
    async def _parse_liability_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse liability analysis"""
        return {
            "liability_caps": self._extract_section(analysis, "liability", "indemnification"),
            "indemnification": self._extract_section(analysis, "indemnification", "insurance"),
            "insurance_requirements": self._extract_section(analysis, "insurance", ""),
            "risk_allocation": "To be determined"  # Would be extracted
        }
    
    async def _parse_ip_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse IP analysis"""
        return {
            "ownership": self._extract_section(analysis, "ownership", "license"),
            "licenses": self._extract_section(analysis, "license", "confidential"),
            "confidentiality": self._extract_section(analysis, "confidential", ""),
            "ip_risks": []  # Would be extracted
        }
    
    async def _parse_compliance_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse compliance analysis"""
        return {
            "compliant_areas": [],
            "violations": [],
            "recommendations": self._extract_recommendations(analysis),
            "risk_level": "medium"  # Would be determined
        }
    
    async def _parse_template_recommendations(self, analysis: str, industry: str) -> Dict[str, Any]:
        """Parse template recommendations"""
        return {
            "industry": industry,
            "essential_clauses": self._extract_section(analysis, "essential", "negotiation"),
            "negotiation_points": self._extract_section(analysis, "negotiation", "red flags"),
            "red_flags": self._extract_section(analysis, "red flags", ""),
            "best_practices": self._extract_recommendations(analysis)
        }
    
    async def _parse_validation_results(self, analysis: str, rules: List[str]) -> Dict[str, Any]:
        """Parse validation results"""
        return {
            "rules_checked": len(rules),
            "violations": [],  # Would be extracted
            "suggestions": self._extract_recommendations(analysis),
            "overall_compliance": "Needs review"  # Would be determined
        }