"""
Agent Factory for creating specialized CrewAI agents for Nexus Document
"""
from typing import Dict, List, Any, Optional
from crewai import Agent, Tool
from langchain_core.language_models import BaseLLM
from loguru import logger


class NexusAgentFactory:
    """Factory for creating specialized CrewAI agents"""
    
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self.agent_registry = self._initialize_agent_registry()
        self.tools = self._initialize_tools()
    
    def _initialize_agent_registry(self) -> Dict[str, Dict[str, Any]]:
        """Initialize registry of available agent types"""
        return {
            # Financial Analysis Agents
            "invoice_analyst": {
                "role": "Invoice Analysis Specialist",
                "goal": "Extract, validate, and analyze invoice data with high accuracy",
                "backstory": """You are an expert in invoice processing with years of experience
                in financial document analysis. You can identify discrepancies, validate totals,
                and extract key information from any invoice format.""",
                "tools": ["extract_tables", "validate_totals", "check_tax_calculations"],
                "capabilities": ["ocr", "validation", "calculation"]
            },
            
            "expense_tracker": {
                "role": "Expense Tracking Expert",
                "goal": "Categorize expenses and identify spending patterns",
                "backstory": """You specialize in expense analysis and budgeting. You can
                categorize expenses accurately and identify trends or anomalies in spending.""",
                "tools": ["categorize_expense", "trend_analysis", "anomaly_detection"],
                "capabilities": ["categorization", "analysis", "reporting"]
            },
            
            "compliance_officer": {
                "role": "Financial Compliance Officer",
                "goal": "Ensure all financial documents meet regulatory requirements",
                "backstory": """You are a compliance expert who ensures all financial documents
                adhere to regulations and company policies. You can identify compliance issues
                and suggest corrections.""",
                "tools": ["check_regulations", "validate_format", "flag_compliance_issues"],
                "capabilities": ["compliance", "validation", "regulation"]
            },
            
            # Document Research Agents
            "research_specialist": {
                "role": "Document Research Specialist",
                "goal": "Find and analyze relevant documents for any query",
                "backstory": """You are an expert researcher who can quickly find relevant
                information across large document collections. You excel at understanding
                context and finding the most pertinent information.""",
                "tools": ["semantic_search", "keyword_search", "metadata_filter"],
                "capabilities": ["search", "retrieval", "relevance_ranking"]
            },
            
            "fact_checker": {
                "role": "Fact Verification Expert",
                "goal": "Verify facts and cross-reference information across documents",
                "backstory": """You specialize in verifying information accuracy. You can
                cross-reference facts across multiple sources and identify inconsistencies
                or contradictions.""",
                "tools": ["cross_reference", "verify_facts", "check_sources"],
                "capabilities": ["verification", "cross_referencing", "accuracy"]
            },
            
            "summarizer": {
                "role": "Document Summarization Expert",
                "goal": "Create clear, concise summaries of complex documents",
                "backstory": """You excel at distilling complex information into clear,
                actionable summaries. You understand what information is most important
                and can present it concisely.""",
                "tools": ["extractive_summary", "abstractive_summary", "key_points_extraction"],
                "capabilities": ["summarization", "synthesis", "clarity"]
            },
            
            # Analysis and Synthesis Agents
            "analyst": {
                "role": "Business Analyst",
                "goal": "Analyze data and provide actionable insights",
                "backstory": """You are a skilled analyst who can identify patterns,
                trends, and insights from complex data. You provide clear, actionable
                recommendations based on thorough analysis.""",
                "tools": ["data_analysis", "pattern_recognition", "insight_generation"],
                "capabilities": ["analysis", "insights", "recommendations"]
            },
            
            "writer": {
                "role": "Technical Writer",
                "goal": "Create well-structured, clear documentation",
                "backstory": """You are an expert technical writer who can transform
                complex information into clear, well-organized documents. You excel
                at structuring information logically.""",
                "tools": ["document_structuring", "markdown_formatting", "clarity_enhancement"],
                "capabilities": ["writing", "structuring", "formatting"]
            },
            
            "editor": {
                "role": "Content Editor",
                "goal": "Ensure content quality, clarity, and consistency",
                "backstory": """You are a meticulous editor who ensures all content
                is clear, consistent, and error-free. You improve readability while
                maintaining accuracy.""",
                "tools": ["grammar_check", "consistency_check", "readability_improvement"],
                "capabilities": ["editing", "proofreading", "quality_assurance"]
            }
        }
    
    def _initialize_tools(self) -> Dict[str, Tool]:
        """Initialize tools available to agents"""
        
        # Define tool functions (these would connect to actual implementations)
        def semantic_search(query: str) -> str:
            """Perform semantic search in document collection"""
            return f"Semantic search results for: {query}"
        
        def extract_tables(document: str) -> str:
            """Extract tables from document"""
            return "Extracted table data"
        
        def validate_totals(data: Dict) -> str:
            """Validate invoice totals"""
            return "Validation results"
        
        def categorize_expense(expense: str) -> str:
            """Categorize an expense item"""
            return f"Categorized as: Business expense"
        
        # Create Tool objects
        tools = {
            "semantic_search": Tool(
                name="Semantic Search",
                description="Search documents using semantic similarity",
                func=semantic_search
            ),
            "extract_tables": Tool(
                name="Extract Tables",
                description="Extract table data from documents",
                func=extract_tables
            ),
            "validate_totals": Tool(
                name="Validate Totals",
                description="Validate numerical totals in invoices",
                func=validate_totals
            ),
            "categorize_expense": Tool(
                name="Categorize Expense",
                description="Categorize expense items",
                func=categorize_expense
            ),
            # Add more tools as needed
        }
        
        # Create placeholder tools for those not implemented
        tool_names = [
            "keyword_search", "metadata_filter", "check_tax_calculations",
            "trend_analysis", "anomaly_detection", "check_regulations",
            "validate_format", "flag_compliance_issues", "cross_reference",
            "verify_facts", "check_sources", "extractive_summary",
            "abstractive_summary", "key_points_extraction", "data_analysis",
            "pattern_recognition", "insight_generation", "document_structuring",
            "markdown_formatting", "clarity_enhancement", "grammar_check",
            "consistency_check", "readability_improvement"
        ]
        
        for tool_name in tool_names:
            if tool_name not in tools:
                tools[tool_name] = Tool(
                    name=tool_name.replace("_", " ").title(),
                    description=f"Tool for {tool_name.replace('_', ' ')}",
                    func=lambda x, name=tool_name: f"{name} results for: {x}"
                )
        
        return tools
    
    def create_agent(
        self,
        agent_type: str,
        memory_context: Optional[Dict[str, Any]] = None,
        custom_tools: Optional[List[Tool]] = None
    ) -> Agent:
        """Create a specialized agent with memory context"""
        
        if agent_type not in self.agent_registry:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_config = self.agent_registry[agent_type]
        
        # Get tools for this agent
        agent_tools = []
        for tool_name in agent_config["tools"]:
            if tool_name in self.tools:
                agent_tools.append(self.tools[tool_name])
        
        # Add custom tools if provided
        if custom_tools:
            agent_tools.extend(custom_tools)
        
        # Enhance backstory with memory context if available
        backstory = agent_config["backstory"]
        if memory_context:
            memory_summary = self._summarize_memory_context(memory_context)
            if memory_summary:
                backstory += f"\n\nBased on past experience: {memory_summary}"
        
        # Create agent
        agent = Agent(
            role=agent_config["role"],
            goal=agent_config["goal"],
            backstory=backstory,
            tools=agent_tools,
            llm=self.llm,
            verbose=True,
            allow_delegation=False,  # Agents work independently
            max_iter=3  # Limit iterations
        )
        
        logger.info(f"Created agent: {agent_type} with {len(agent_tools)} tools")
        
        return agent
    
    def create_agent_team(
        self,
        task_type: str,
        memory_context: Optional[Dict[str, Any]] = None
    ) -> List[Agent]:
        """Create a team of agents for a specific task type"""
        
        team_compositions = {
            "financial_analysis": [
                "invoice_analyst",
                "expense_tracker",
                "compliance_officer"
            ],
            "document_research": [
                "research_specialist",
                "fact_checker",
                "summarizer"
            ],
            "content_creation": [
                "analyst",
                "writer",
                "editor"
            ],
            "comprehensive_analysis": [
                "research_specialist",
                "analyst",
                "summarizer"
            ]
        }
        
        # Get team composition
        agent_types = team_compositions.get(task_type, ["research_specialist", "analyst"])
        
        # Create agents
        team = []
        for agent_type in agent_types:
            agent = self.create_agent(agent_type, memory_context)
            team.append(agent)
        
        logger.info(f"Created team of {len(team)} agents for {task_type}")
        
        return team
    
    def get_available_agents(self) -> List[str]:
        """Get list of available agent types"""
        return list(self.agent_registry.keys())
    
    def get_agent_capabilities(self, agent_type: str) -> List[str]:
        """Get capabilities of a specific agent type"""
        if agent_type in self.agent_registry:
            return self.agent_registry[agent_type]["capabilities"]
        return []
    
    def recommend_agents(
        self,
        task_description: str,
        required_capabilities: List[str]
    ) -> List[str]:
        """Recommend agents based on task requirements"""
        
        recommended = []
        
        for agent_type, config in self.agent_registry.items():
            agent_capabilities = set(config["capabilities"])
            required_set = set(required_capabilities)
            
            # Check if agent has any required capabilities
            if agent_capabilities.intersection(required_set):
                match_score = len(agent_capabilities.intersection(required_set)) / len(required_set)
                recommended.append((agent_type, match_score))
        
        # Sort by match score
        recommended.sort(key=lambda x: x[1], reverse=True)
        
        # Return top recommendations
        return [agent_type for agent_type, _ in recommended[:3]]
    
    def _summarize_memory_context(self, memory_context: Dict[str, Any]) -> str:
        """Summarize memory context for agent backstory"""
        
        summary_parts = []
        
        # Summarize episodic memories
        if episodic := memory_context.get("episodic", []):
            summary_parts.append(f"You have handled {len(episodic)} similar tasks recently")
        
        # Summarize semantic knowledge
        if semantic := memory_context.get("semantic", []):
            summary_parts.append(f"You have access to {len(semantic)} relevant facts")
        
        # Summarize procedural patterns
        if procedural := memory_context.get("procedural", []):
            successful_patterns = [p for p in procedural if p.get("content", {}).get("pattern", {}).get("effectiveness", 0) > 0.7]
            if successful_patterns:
                summary_parts.append(f"You know {len(successful_patterns)} successful approaches")
        
        return ". ".join(summary_parts) if summary_parts else ""