"""
Agent Definition Schema for dynamic agent loading
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class AgentCapability(str, Enum):
    """Standard agent capabilities"""
    ANALYSIS = "analysis"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    COMPLIANCE = "compliance"
    RISK_ASSESSMENT = "risk_assessment"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    CLASSIFICATION = "classification"
    SIGNATURE_MANAGEMENT = "signature_management"
    FINANCIAL_ANALYSIS = "financial_analysis"
    LEGAL_REVIEW = "legal_review"
    DATA_PROCESSING = "data_processing"
    REPORT_GENERATION = "report_generation"
    QUALITY_CONTROL = "quality_control"
    RESEARCH = "research"


class AgentTool(BaseModel):
    """Tool that an agent can use"""
    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = None
    required: bool = False


class AgentDefinition(BaseModel):
    """Schema for agent definition"""
    id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Human-readable agent name")
    role: str = Field(..., description="Agent's role/title")
    goal: str = Field(..., description="Agent's primary goal")
    backstory: str = Field(..., description="Agent's background and expertise")
    
    # Capabilities and specializations
    capabilities: List[AgentCapability] = Field(default_factory=list)
    specializations: List[str] = Field(default_factory=list, description="Specific areas of expertise")
    
    # Document types this agent can handle
    document_types: List[str] = Field(default_factory=list, description="Document types agent specializes in")
    
    # Tools and permissions
    tools: List[AgentTool] = Field(default_factory=list, description="Tools available to this agent")
    allow_delegation: bool = Field(default=False, description="Can delegate tasks to other agents")
    
    # Behavioral settings
    verbose: bool = Field(default=True, description="Verbose output during execution")
    max_iterations: int = Field(default=5, description="Maximum thinking iterations")
    temperature: float = Field(default=0.7, description="LLM temperature for this agent")
    
    # System prompts and instructions
    system_prompt_template: Optional[str] = Field(None, description="Custom system prompt template")
    task_prompt_template: Optional[str] = Field(None, description="Template for task instructions")
    output_format: Optional[str] = Field(None, description="Expected output format")
    
    # Constraints and guidelines
    constraints: List[str] = Field(default_factory=list, description="Operational constraints")
    guidelines: List[str] = Field(default_factory=list, description="Best practices to follow")
    
    # Performance and quality metrics
    expected_output_quality: str = Field(default="high", description="Expected quality level")
    time_limit_seconds: Optional[int] = Field(None, description="Time limit for task completion")
    
    # Dependencies and requirements
    required_context: List[str] = Field(default_factory=list, description="Required context keys")
    depends_on: List[str] = Field(default_factory=list, description="Other agents this depends on")
    
    # Metadata
    version: str = Field(default="1.0.0", description="Agent definition version")
    author: str = Field(default="system", description="Who created this agent")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    active: bool = Field(default=True, description="Whether agent is active")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "contract_reviewer",
                "name": "Contract Review Specialist",
                "role": "Senior Contract Analyst",
                "goal": "Analyze contracts for key terms, obligations, and potential risks",
                "backstory": "20+ years experience in corporate law, specializing in commercial contracts",
                "capabilities": ["legal_review", "risk_assessment", "compliance"],
                "specializations": ["commercial_contracts", "ndas", "service_agreements"],
                "document_types": ["contract", "agreement", "legal"],
                "tools": [
                    {
                        "name": "clause_extractor",
                        "description": "Extract specific clauses from contracts",
                        "required": True
                    }
                ],
                "allow_delegation": False,
                "verbose": True,
                "system_prompt_template": "You are a senior contract analyst with expertise in {specialization}.",
                "constraints": [
                    "Always identify governing law",
                    "Flag any unusual termination clauses",
                    "Check for limitation of liability"
                ],
                "guidelines": [
                    "Summarize key terms first",
                    "Identify all parties clearly",
                    "Note any missing standard clauses"
                ],
                "tags": ["legal", "contracts", "compliance"]
            }
        }


class AgentCollection(BaseModel):
    """Collection of agent definitions"""
    agents: List[AgentDefinition]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def get_agent(self, agent_id: str) -> Optional[AgentDefinition]:
        """Get agent by ID"""
        for agent in self.agents:
            if agent.id == agent_id:
                return agent
        return None
    
    def get_agents_for_document_type(self, doc_type: str) -> List[AgentDefinition]:
        """Get agents that can handle a specific document type"""
        return [
            agent for agent in self.agents
            if doc_type in agent.document_types or "all" in agent.document_types
        ]
    
    def get_agents_with_capability(self, capability: AgentCapability) -> List[AgentDefinition]:
        """Get agents with a specific capability"""
        return [
            agent for agent in self.agents
            if capability in agent.capabilities
        ]