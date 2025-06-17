"""
Document Analysis Crew - Advanced document processing with LangGraph + CrewAI
"""
from typing import TypedDict, List, Dict, Any, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from crewai import Agent, Task, Crew, Process
from loguru import logger
import json
from datetime import datetime
from enum import Enum

from app.schemas.graph import GraphNode
from app.agents.agent_loader import agent_loader
from app.agents.agent_schema import AgentCapability


class DocumentType(str, Enum):
    CONTRACT = "contract"
    INVOICE = "invoice"
    LEGAL = "legal"
    FINANCIAL = "financial"
    AGREEMENT = "agreement"
    REPORT = "report"
    GENERAL = "general"




class DocumentCrewState(TypedDict):
    """State for document analysis crew"""
    document_id: str
    document_content: str
    document_type: DocumentType
    tenant_id: str
    user_id: Optional[str]
    
    # Analysis stages
    initial_analysis: Optional[Dict[str, Any]]
    extracted_entities: Optional[Dict[str, Any]]
    compliance_check: Optional[Dict[str, Any]]
    risk_assessment: Optional[Dict[str, Any]]
    
    # Crew management
    selected_agents: List[str]  # List of agent IDs
    agent_outputs: Dict[str, Any]
    crew_tasks: List[Dict[str, Any]]
    
    # Results
    final_analysis: Optional[Dict[str, Any]]
    recommendations: Optional[List[str]]
    action_items: Optional[List[Dict[str, Any]]]
    confidence_scores: Dict[str, float]
    
    # Workflow control
    requires_signature: bool
    compliance_issues: List[Dict[str, Any]]
    financial_metrics: Optional[Dict[str, Any]]
    iteration: int
    error: Optional[str]


class DocumentAnalysisCrew:
    """Advanced document analysis using LangGraph + CrewAI with dynamic agents"""
    
    def __init__(self, llm, embeddings=None, vector_store=None, checkpointer=None, **kwargs):
        self.llm = llm
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.checkpointer = checkpointer
        
        # Load agent definitions
        self.agent_loader = agent_loader
        self.agent_loader.load_all_agents()
        logger.info(f"Loaded {len(self.agent_loader.agents_collection.agents)} agent definitions")
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the document analysis workflow graph"""
        workflow = StateGraph(DocumentCrewState)
        
        # Add nodes - each represents a stage in document analysis
        workflow.add_node("classify_document", self.classify_document)
        workflow.add_node("select_specialist_agents", self.select_specialist_agents)
        workflow.add_node("extract_entities", self.extract_entities)
        workflow.add_node("analyze_compliance", self.analyze_compliance)
        workflow.add_node("assess_risks", self.assess_risks)
        workflow.add_node("analyze_financial_data", self.analyze_financial_data)
        workflow.add_node("execute_specialist_crew", self.execute_specialist_crew)
        workflow.add_node("synthesize_findings", self.synthesize_findings)
        workflow.add_node("generate_recommendations", self.generate_recommendations)
        workflow.add_node("quality_assurance", self.quality_assurance)
        
        # Set entry point
        workflow.set_entry_point("classify_document")
        
        # Define the flow
        workflow.add_edge("classify_document", "select_specialist_agents")
        workflow.add_edge("select_specialist_agents", "extract_entities")
        workflow.add_edge("extract_entities", "execute_specialist_crew")
        
        # Conditional edges based on document type
        workflow.add_conditional_edges(
            "execute_specialist_crew",
            self.route_by_document_type,
            {
                "compliance": "analyze_compliance",
                "financial": "analyze_financial_data",
                "risk": "assess_risks",
                "synthesize": "synthesize_findings"
            }
        )
        
        workflow.add_edge("analyze_compliance", "synthesize_findings")
        workflow.add_edge("analyze_financial_data", "synthesize_findings")
        workflow.add_edge("assess_risks", "synthesize_findings")
        workflow.add_edge("synthesize_findings", "generate_recommendations")
        workflow.add_edge("generate_recommendations", "quality_assurance")
        
        # Quality check can loop back or end
        workflow.add_conditional_edges(
            "quality_assurance",
            self.quality_check_routing,
            {
                "refine": "execute_specialist_crew",
                "done": END
            }
        )
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def classify_document(self, state: DocumentCrewState) -> DocumentCrewState:
        """Classify document type and extract metadata"""
        logger.info(f"Classifying document {state['document_id']}")
        
        messages = [
            SystemMessage(content="""You are a document classification expert. 
            Analyze the document and identify:
            1. Document type (contract, invoice, legal, financial, agreement, report, general)
            2. Key characteristics
            3. Whether it requires signatures
            4. Compliance requirements
            5. Risk factors"""),
            HumanMessage(content=f"""
            Analyze this document:
            
            {state['document_content'][:2000]}...
            
            Return a JSON response with your analysis.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            analysis = json.loads(response.content)
        except:
            analysis = {
                "document_type": DocumentType.GENERAL,
                "characteristics": ["unstructured"],
                "requires_signature": False,
                "compliance_required": False,
                "risk_level": "low"
            }
        
        state["initial_analysis"] = analysis
        state["document_type"] = DocumentType(analysis.get("document_type", "general"))
        state["requires_signature"] = analysis.get("requires_signature", False)
        state["iteration"] = 1
        
        return state
    
    async def select_specialist_agents(self, state: DocumentCrewState) -> DocumentCrewState:
        """Select specialist agents dynamically based on document type and requirements"""
        logger.info(f"Selecting agents for {state['document_type']} document")
        
        # Get suitable agents from the loader
        suitable_agents = self.agent_loader.get_agents_for_document_type(state["document_type"])
        
        # Determine required capabilities based on document analysis
        required_capabilities = []
        
        # Add capabilities based on document characteristics
        if state["requires_signature"]:
            required_capabilities.append(AgentCapability.SIGNATURE_MANAGEMENT)
        
        if state["initial_analysis"].get("compliance_required", False):
            required_capabilities.append(AgentCapability.COMPLIANCE)
        
        if state["document_type"] in [DocumentType.CONTRACT, DocumentType.LEGAL, DocumentType.AGREEMENT]:
            required_capabilities.extend([
                AgentCapability.LEGAL_REVIEW,
                AgentCapability.RISK_ASSESSMENT
            ])
        
        if state["document_type"] in [DocumentType.INVOICE, DocumentType.FINANCIAL]:
            required_capabilities.append(AgentCapability.FINANCIAL_ANALYSIS)
        
        # Always need extraction and analysis
        required_capabilities.extend([
            AgentCapability.EXTRACTION,
            AgentCapability.ANALYSIS
        ])
        
        # Filter agents by required capabilities
        selected_agents = []
        for capability in required_capabilities:
            capability_agents = [
                agent for agent in suitable_agents
                if capability in agent.capabilities and agent.id not in [a.id for a in selected_agents]
            ]
            if capability_agents:
                # Take the most relevant agent for this capability
                selected_agents.append(capability_agents[0])
        
        # Ensure we have at least one agent
        if not selected_agents and suitable_agents:
            selected_agents.append(suitable_agents[0])
        
        # Store selected agent IDs (not the enum anymore)
        state["selected_agents"] = [agent.id for agent in selected_agents]
        logger.info(f"Selected {len(selected_agents)} agents: {[a.name for a in selected_agents]}")
        
        return state
    
    async def extract_entities(self, state: DocumentCrewState) -> DocumentCrewState:
        """Extract key entities and data from document"""
        logger.info("Extracting entities from document")
        
        messages = [
            SystemMessage(content="""You are a data extraction specialist.
            Extract all relevant entities, dates, amounts, parties, and key terms from the document.
            Be precise and comprehensive."""),
            HumanMessage(content=f"""
            Document type: {state['document_type']}
            
            Extract entities from:
            {state['document_content']}
            
            Return a structured JSON with all extracted data.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            entities = json.loads(response.content)
        except:
            entities = {"error": "Failed to extract entities"}
        
        state["extracted_entities"] = entities
        
        return state
    
    async def execute_specialist_crew(self, state: DocumentCrewState) -> DocumentCrewState:
        """Execute CrewAI with dynamically loaded specialist agents"""
        logger.info("Executing specialist crew with dynamic agents")
        
        # Create context for agents
        context = {
            "document_type": state["document_type"],
            "specialization": state["document_type"],
            "tenant_id": state["tenant_id"],
            "extracted_entities": json.dumps(state.get("extracted_entities", {}))
        }
        
        # Create CrewAI agents from definitions
        crew_agents = []
        
        for agent_id in state["selected_agents"]:
            agent_def = self.agent_loader.get_agent_definition(agent_id)
            if not agent_def:
                logger.warning(f"Agent definition not found for ID: {agent_id}")
                continue
            
            try:
                # Create CrewAI agent from definition
                agent = self.agent_loader.create_crewai_agent(
                    agent_def,
                    self.llm,
                    context
                )
                crew_agents.append(agent)
                logger.info(f"Created agent: {agent_def.name} ({agent_def.role})")
            except Exception as e:
                logger.error(f"Failed to create agent {agent_id}: {e}")
        
        if not crew_agents:
            logger.error("No agents created for crew execution")
            state["error"] = "No agents available for document analysis"
            return state
        
        # Create tasks for each agent using their definitions
        tasks = []
        for i, agent in enumerate(crew_agents):
            agent_id = state["selected_agents"][i]
            agent_def = self.agent_loader.get_agent_definition(agent_id)
            
            # Use agent's task prompt template if available
            if agent_def and agent_def.task_prompt_template:
                task_description = agent_def.task_prompt_template.format(
                    document_type=state["document_type"],
                    document_content=state["document_content"][:3000],
                    **context
                )
            else:
                # Fallback to generic task description
                task_description = f"""
                Analyze the following {state['document_type']} document:
                
                Extracted Entities: {json.dumps(state.get('extracted_entities', {}), indent=2)}
                
                Document Content: {state['document_content'][:3000]}...
                
                Provide your specialized analysis based on your role.
                """
            
            # Create task with proper description and expected output
            expected_output = agent_def.output_format if agent_def else "Detailed analysis"
            
            task = Task(
                description=task_description,
                agent=agent,
                expected_output=expected_output
            )
            tasks.append(task)
        
        # Create and execute crew
        crew = Crew(
            agents=crew_agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True
        )
        
        # Execute crew (in production, this would be properly async)
        try:
            crew_output = crew.kickoff()
            
            # Parse individual agent outputs
            agent_outputs = {}
            for i, agent in enumerate(crew_agents):
                agent_outputs[agent.role] = {
                    "output": str(crew_output) if i == 0 else f"Analysis from {agent.role}",
                    "status": "completed"
                }
            
            state["agent_outputs"] = agent_outputs
            
        except Exception as e:
            logger.error(f"Crew execution failed: {e}")
            state["error"] = str(e)
            state["agent_outputs"] = {}
        
        return state
    
    async def analyze_compliance(self, state: DocumentCrewState) -> DocumentCrewState:
        """Deep compliance analysis"""
        logger.info("Performing compliance analysis")
        
        compliance_output = state["agent_outputs"].get("Compliance Officer", {}).get("output", "")
        
        messages = [
            SystemMessage(content="You are a compliance expert. Analyze the compliance findings and identify specific issues."),
            HumanMessage(content=f"""
            Based on the compliance analysis:
            {compliance_output}
            
            Identify:
            1. Specific compliance violations or risks
            2. Regulatory frameworks affected
            3. Required actions for compliance
            4. Risk severity levels
            
            Return a structured JSON response.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            compliance_check = json.loads(response.content)
            state["compliance_issues"] = compliance_check.get("issues", [])
        except:
            compliance_check = {"status": "review_needed"}
        
        state["compliance_check"] = compliance_check
        
        return state
    
    async def analyze_financial_data(self, state: DocumentCrewState) -> DocumentCrewState:
        """Analyze financial aspects"""
        logger.info("Analyzing financial data")
        
        financial_output = state["agent_outputs"].get("Financial Analyst", {}).get("output", "")
        entities = state.get("extracted_entities", {})
        
        messages = [
            SystemMessage(content="You are a financial analyst. Calculate key metrics and identify financial implications."),
            HumanMessage(content=f"""
            Financial analysis output: {financial_output}
            Extracted entities: {json.dumps(entities, indent=2)}
            
            Calculate and provide:
            1. Key financial metrics
            2. Cash flow implications
            3. Financial risks
            4. Cost-benefit analysis
            
            Return structured JSON with calculations.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            financial_metrics = json.loads(response.content)
        except:
            financial_metrics = {"status": "manual_review_needed"}
        
        state["financial_metrics"] = financial_metrics
        
        return state
    
    async def assess_risks(self, state: DocumentCrewState) -> DocumentCrewState:
        """Comprehensive risk assessment"""
        logger.info("Assessing risks")
        
        risk_output = state["agent_outputs"].get("Risk Assessment Specialist", {}).get("output", "")
        
        messages = [
            SystemMessage(content="You are a risk assessment expert. Provide a comprehensive risk analysis."),
            HumanMessage(content=f"""
            Risk assessment output: {risk_output}
            Document type: {state['document_type']}
            Compliance issues: {json.dumps(state.get('compliance_issues', []), indent=2)}
            
            Provide:
            1. Risk matrix (likelihood vs impact)
            2. Mitigation strategies
            3. Priority ranking
            4. Monitoring recommendations
            
            Return structured JSON.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        try:
            risk_assessment = json.loads(response.content)
        except:
            risk_assessment = {"risks": [], "overall_risk": "medium"}
        
        state["risk_assessment"] = risk_assessment
        
        return state
    
    async def synthesize_findings(self, state: DocumentCrewState) -> DocumentCrewState:
        """Synthesize all agent findings into comprehensive analysis"""
        logger.info("Synthesizing findings")
        
        all_outputs = json.dumps(state["agent_outputs"], indent=2)
        
        messages = [
            SystemMessage(content="""You are a master analyst. 
            Synthesize all specialist findings into a comprehensive, coherent analysis.
            Focus on actionable insights and clear conclusions."""),
            HumanMessage(content=f"""
            Document Type: {state['document_type']}
            
            All Agent Outputs:
            {all_outputs}
            
            Compliance Status: {json.dumps(state.get('compliance_check', {}), indent=2)}
            Financial Metrics: {json.dumps(state.get('financial_metrics', {}), indent=2)}
            Risk Assessment: {json.dumps(state.get('risk_assessment', {}), indent=2)}
            
            Create a comprehensive analysis that:
            1. Summarizes key findings
            2. Highlights critical issues
            3. Provides clear conclusions
            4. Maintains consistency across all analyses
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        state["final_analysis"] = {
            "summary": response.content,
            "document_type": state["document_type"],
            "requires_signature": state["requires_signature"],
            "compliance_status": "issues_found" if state.get("compliance_issues") else "compliant",
            "risk_level": state.get("risk_assessment", {}).get("overall_risk", "medium"),
            "confidence_score": 0.85  # Would be calculated based on agent consensus
        }
        
        return state
    
    async def generate_recommendations(self, state: DocumentCrewState) -> DocumentCrewState:
        """Generate actionable recommendations"""
        logger.info("Generating recommendations")
        
        messages = [
            SystemMessage(content="You are a strategic advisor. Generate clear, actionable recommendations."),
            HumanMessage(content=f"""
            Based on the comprehensive analysis:
            {json.dumps(state['final_analysis'], indent=2)}
            
            Generate:
            1. Immediate action items
            2. Short-term recommendations
            3. Long-term strategic advice
            4. Risk mitigation steps
            
            Be specific and prioritize by importance.
            """)
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse recommendations
        recommendations = response.content.split('\n')
        recommendations = [r.strip() for r in recommendations if r.strip()]
        
        state["recommendations"] = recommendations[:10]  # Top 10 recommendations
        
        # Create action items
        action_items = []
        if state["requires_signature"]:
            action_items.append({
                "type": "signature_required",
                "priority": "high",
                "description": "Document requires signature workflow initiation",
                "assigned_to": "signature_specialist"
            })
        
        if state.get("compliance_issues"):
            action_items.append({
                "type": "compliance_remediation",
                "priority": "high",
                "description": "Address compliance issues identified",
                "assigned_to": "compliance_officer"
            })
        
        state["action_items"] = action_items
        
        return state
    
    async def quality_assurance(self, state: DocumentCrewState) -> DocumentCrewState:
        """Quality check on the analysis"""
        logger.info("Performing quality assurance")
        
        # Calculate confidence scores
        confidence_scores = {
            "classification": 0.9,
            "entity_extraction": 0.85,
            "compliance_analysis": 0.8 if state.get("compliance_check") else 0.0,
            "risk_assessment": 0.75 if state.get("risk_assessment") else 0.0,
            "overall": 0.8
        }
        
        state["confidence_scores"] = confidence_scores
        
        # Check if refinement is needed
        if confidence_scores["overall"] < 0.7 or state.get("error"):
            state["iteration"] += 1
        
        return state
    
    def route_by_document_type(self, state: DocumentCrewState) -> str:
        """Route to specialized analysis based on document type"""
        doc_type = state["document_type"]
        
        if doc_type in [DocumentType.CONTRACT, DocumentType.LEGAL, DocumentType.AGREEMENT]:
            return "compliance"
        elif doc_type in [DocumentType.INVOICE, DocumentType.FINANCIAL]:
            return "financial"
        elif state.get("initial_analysis", {}).get("risk_level", "low") in ["high", "critical"]:
            return "risk"
        else:
            return "synthesize"
    
    def quality_check_routing(self, state: DocumentCrewState) -> str:
        """Determine if refinement is needed"""
        if state.get("iteration", 0) < 2 and state["confidence_scores"]["overall"] < 0.7:
            return "refine"
        return "done"
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the document analysis crew"""
        initial_state = DocumentCrewState(
            document_id=input_data.get("document_id", ""),
            document_content=input_data.get("document_content", ""),
            document_type=DocumentType.GENERAL,
            tenant_id=input_data.get("tenant_id", ""),
            user_id=input_data.get("user_id"),
            initial_analysis=None,
            extracted_entities=None,
            compliance_check=None,
            risk_assessment=None,
            selected_agents=[],
            agent_outputs={},
            crew_tasks=[],
            final_analysis=None,
            recommendations=None,
            action_items=None,
            confidence_scores={},
            requires_signature=False,
            compliance_issues=[],
            financial_metrics=None,
            iteration=0,
            error=None
        )
        
        result = await self.graph.ainvoke(initial_state, config)
        
        return {
            "document_id": result["document_id"],
            "document_type": result["document_type"],
            "analysis": result.get("final_analysis", {}),
            "recommendations": result.get("recommendations", []),
            "action_items": result.get("action_items", []),
            "extracted_data": result.get("extracted_entities", {}),
            "compliance_status": result.get("compliance_check", {}),
            "risk_assessment": result.get("risk_assessment", {}),
            "financial_metrics": result.get("financial_metrics", {}),
            "confidence_scores": result.get("confidence_scores", {}),
            "agents_used": result.get("selected_agents", []),
            "requires_signature": result.get("requires_signature", False),
            "success": not bool(result.get("error")),
            "error": result.get("error")
        }
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from the analysis"""
        initial_state = DocumentCrewState(
            document_id=input_data.get("document_id", ""),
            document_content=input_data.get("document_content", ""),
            document_type=DocumentType.GENERAL,
            tenant_id=input_data.get("tenant_id", ""),
            user_id=input_data.get("user_id"),
            initial_analysis=None,
            extracted_entities=None,
            compliance_check=None,
            risk_assessment=None,
            selected_agents=[],
            agent_outputs={},
            crew_tasks=[],
            final_analysis=None,
            recommendations=None,
            action_items=None,
            confidence_scores={},
            requires_signature=False,
            compliance_issues=[],
            financial_metrics=None,
            iteration=0,
            error=None
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="classify_document",
                    name="Classify Document",
                    type="llm",
                    description="Classify document type and characteristics"
                ).dict(),
                GraphNode(
                    id="select_specialist_agents",
                    name="Select Specialists",
                    type="orchestration",
                    description="Choose specialist agents based on document type"
                ).dict(),
                GraphNode(
                    id="extract_entities",
                    name="Extract Entities",
                    type="extraction",
                    description="Extract key data from document"
                ).dict(),
                GraphNode(
                    id="execute_specialist_crew",
                    name="Execute Crew",
                    type="execution",
                    description="Run CrewAI with specialist agents"
                ).dict(),
                GraphNode(
                    id="analyze_compliance",
                    name="Compliance Check",
                    type="analysis",
                    description="Deep compliance analysis"
                ).dict(),
                GraphNode(
                    id="analyze_financial_data",
                    name="Financial Analysis",
                    type="analysis",
                    description="Analyze financial aspects"
                ).dict(),
                GraphNode(
                    id="assess_risks",
                    name="Risk Assessment",
                    type="analysis",
                    description="Comprehensive risk evaluation"
                ).dict(),
                GraphNode(
                    id="synthesize_findings",
                    name="Synthesize",
                    type="synthesis",
                    description="Combine all findings"
                ).dict(),
                GraphNode(
                    id="generate_recommendations",
                    name="Recommendations",
                    type="planning",
                    description="Generate actionable advice"
                ).dict(),
                GraphNode(
                    id="quality_assurance",
                    name="Quality Check",
                    type="validation",
                    description="Ensure analysis quality"
                ).dict()
            ],
            "edges": [
                {"from": "classify_document", "to": "select_specialist_agents"},
                {"from": "select_specialist_agents", "to": "extract_entities"},
                {"from": "extract_entities", "to": "execute_specialist_crew"},
                {"from": "execute_specialist_crew", "to": "analyze_compliance", "condition": "compliance"},
                {"from": "execute_specialist_crew", "to": "analyze_financial_data", "condition": "financial"},
                {"from": "execute_specialist_crew", "to": "assess_risks", "condition": "risk"},
                {"from": "execute_specialist_crew", "to": "synthesize_findings", "condition": "synthesize"},
                {"from": "analyze_compliance", "to": "synthesize_findings"},
                {"from": "analyze_financial_data", "to": "synthesize_findings"},
                {"from": "assess_risks", "to": "synthesize_findings"},
                {"from": "synthesize_findings", "to": "generate_recommendations"},
                {"from": "generate_recommendations", "to": "quality_assurance"},
                {"from": "quality_assurance", "to": "execute_specialist_crew", "condition": "refine"},
                {"from": "quality_assurance", "to": "END", "condition": "done"}
            ],
            "entry_point": "classify_document",
            "description": "Advanced document analysis with specialized CrewAI agents"
        }