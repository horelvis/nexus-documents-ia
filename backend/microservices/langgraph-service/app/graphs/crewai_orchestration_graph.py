"""
CrewAI Orchestration Graph - Combines LangGraph state management with CrewAI agent coordination
"""
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from crewai import Agent, Task, Crew, Process
from loguru import logger
import json
from datetime import datetime

from app.schemas.graph import GraphNode
from app.services.memory_manager import UnifiedMemoryManager
from app.services.agent_factory import NexusAgentFactory


class CrewState(TypedDict):
    """State for CrewAI orchestration"""
    query: str
    task_type: str
    tenant_id: str
    user_id: Optional[str]
    selected_agents: List[str]
    tasks: List[Dict[str, Any]]
    crew_results: Optional[Dict[str, Any]]
    memory_context: Dict[str, Any]
    synthesis: Optional[str]
    confidence_score: Optional[float]
    needs_refinement: bool
    iteration: int
    metadata: Dict[str, Any]


class CrewAIOrchestrationGraph:
    """LangGraph for orchestrating CrewAI agents with memory management"""
    
    def __init__(self, llm, embeddings, qdrant_client, checkpointer, tenant_id: str, **kwargs):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.checkpointer = checkpointer
        self.tenant_id = tenant_id
        self.memory_manager = UnifiedMemoryManager(
            tenant_id=tenant_id,
            vector_store=qdrant_client,
            embeddings=embeddings
        )
        self.agent_factory = NexusAgentFactory(llm)
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the CrewAI orchestration graph"""
        workflow = StateGraph(CrewState)
        
        # Add nodes
        workflow.add_node("analyze_task", self.analyze_task)
        workflow.add_node("retrieve_memory", self.retrieve_memory)
        workflow.add_node("select_agents", self.select_agents)
        workflow.add_node("create_tasks", self.create_tasks)
        workflow.add_node("execute_crew", self.execute_crew)
        workflow.add_node("update_memory", self.update_memory)
        workflow.add_node("synthesize_results", self.synthesize_results)
        workflow.add_node("quality_check", self.quality_check)
        workflow.add_node("refine_with_memory", self.refine_with_memory)
        
        # Set entry point
        workflow.set_entry_point("analyze_task")
        
        # Add edges
        workflow.add_edge("analyze_task", "retrieve_memory")
        workflow.add_edge("retrieve_memory", "select_agents")
        workflow.add_edge("select_agents", "create_tasks")
        workflow.add_edge("create_tasks", "execute_crew")
        workflow.add_edge("execute_crew", "update_memory")
        workflow.add_edge("update_memory", "synthesize_results")
        workflow.add_edge("synthesize_results", "quality_check")
        
        # Conditional refinement
        workflow.add_conditional_edges(
            "quality_check",
            self.should_refine,
            {
                "refine": "refine_with_memory",
                "done": END
            }
        )
        
        workflow.add_edge("refine_with_memory", END)
        
        # Compile with checkpointer
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def analyze_task(self, state: CrewState) -> CrewState:
        """Analyze the task to understand requirements"""
        logger.info(f"Analyzing task: {state['query']}")
        
        messages = [
            SystemMessage(content="You are a task analyzer. Analyze the user's request and identify the type of task and required capabilities."),
            HumanMessage(content=f"""
Analyze this request and identify:
1. Task type (research, analysis, synthesis, etc.)
2. Required agent capabilities
3. Complexity level
4. Expected output format

Request: {state['query']}

Return a JSON response.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Parse analysis (simplified for POC)
        try:
            analysis = json.loads(response.content)
        except:
            analysis = {
                "task_type": "general",
                "capabilities": ["research", "analysis"],
                "complexity": "medium",
                "output_format": "report"
            }
        
        state["task_type"] = analysis.get("task_type", "general")
        state["metadata"]["task_analysis"] = analysis
        state["iteration"] = state.get("iteration", 0) + 1
        
        return state
    
    async def retrieve_memory(self, state: CrewState) -> CrewState:
        """Retrieve relevant memories for the task"""
        logger.info("Retrieving relevant memories")
        
        # Retrieve memories of different types
        memories = await self.memory_manager.retrieve_relevant_memories(
            query=state['query'],
            context={
                'task_type': state['task_type'],
                'tenant_id': state['tenant_id'],
                'user_id': state.get('user_id')
            },
            memory_types=['episodic', 'semantic', 'procedural']
        )
        
        state["memory_context"] = memories
        
        # Log memory retrieval stats
        logger.info(f"Retrieved memories - Episodic: {len(memories.get('episodic', []))}, "
                   f"Semantic: {len(memories.get('semantic', []))}, "
                   f"Procedural: {len(memories.get('procedural', []))}")
        
        return state
    
    async def select_agents(self, state: CrewState) -> CrewState:
        """Select appropriate agents based on task and memory"""
        logger.info("Selecting agents for task")
        
        # Get available agent types
        available_agents = self.agent_factory.get_available_agents()
        
        # Use procedural memory to inform selection
        successful_patterns = state['memory_context'].get('procedural', [])
        
        # Select agents based on task type and past success
        if state['task_type'] == 'financial_analysis':
            state["selected_agents"] = ['invoice_analyst', 'expense_tracker', 'compliance_officer']
        elif state['task_type'] == 'document_research':
            state["selected_agents"] = ['research_specialist', 'fact_checker', 'summarizer']
        elif state['task_type'] == 'synthesis':
            state["selected_agents"] = ['analyst', 'writer', 'editor']
        else:
            # Default selection
            state["selected_agents"] = ['researcher', 'analyst', 'summarizer']
        
        logger.info(f"Selected agents: {state['selected_agents']}")
        
        return state
    
    async def create_tasks(self, state: CrewState) -> CrewState:
        """Create tasks for the selected agents"""
        logger.info("Creating tasks for crew")
        
        tasks = []
        
        # Create tasks based on selected agents and query
        for agent_type in state['selected_agents']:
            if agent_type == 'invoice_analyst':
                tasks.append({
                    'description': f"Extract and validate invoice data from: {state['query']}",
                    'agent': agent_type,
                    'expected_output': 'Structured invoice data with validation results'
                })
            elif agent_type == 'research_specialist':
                tasks.append({
                    'description': f"Research and find relevant information for: {state['query']}",
                    'agent': agent_type,
                    'expected_output': 'Comprehensive research findings with sources'
                })
            elif agent_type == 'summarizer':
                tasks.append({
                    'description': f"Create a concise summary of findings for: {state['query']}",
                    'agent': agent_type,
                    'expected_output': 'Clear, concise summary with key points'
                })
            # Add more task templates as needed
        
        state["tasks"] = tasks
        
        return state
    
    async def execute_crew(self, state: CrewState) -> CrewState:
        """Execute the crew with selected agents and tasks"""
        logger.info("Executing crew")
        
        try:
            # Create agents
            agents = []
            for agent_type in state['selected_agents']:
                agent = self.agent_factory.create_agent(
                    agent_type,
                    memory_context=state['memory_context']
                )
                agents.append(agent)
            
            # Create CrewAI tasks
            crew_tasks = []
            for task_config in state['tasks']:
                # Find corresponding agent
                agent = next(a for a in agents if a.role.lower().replace(' ', '_') == task_config['agent'])
                
                task = Task(
                    description=task_config['description'],
                    agent=agent,
                    expected_output=task_config['expected_output']
                )
                crew_tasks.append(task)
            
            # Create and execute crew
            crew = Crew(
                agents=agents,
                tasks=crew_tasks,
                process=Process.sequential,  # or Process.hierarchical
                verbose=True
            )
            
            # Execute crew (in real implementation, this would be async)
            # For POC, we'll simulate the result
            crew_output = {
                'raw_output': f"Crew completed analysis for: {state['query']}",
                'agent_outputs': {
                    agent_type: f"Output from {agent_type}"
                    for agent_type in state['selected_agents']
                },
                'success': True
            }
            
            state["crew_results"] = crew_output
            
        except Exception as e:
            logger.error(f"Crew execution failed: {e}")
            state["crew_results"] = {
                'raw_output': f"Error: {str(e)}",
                'agent_outputs': {},
                'success': False
            }
        
        return state
    
    async def update_memory(self, state: CrewState) -> CrewState:
        """Update memory with crew execution results"""
        logger.info("Updating memory with results")
        
        if state['crew_results'].get('success', False):
            # Store successful execution pattern
            await self.memory_manager.store_interaction(
                agent_id='crew_orchestrator',
                task=state['query'],
                result=state['crew_results'],
                metadata={
                    'task_type': state['task_type'],
                    'agents_used': state['selected_agents'],
                    'success': True,
                    'tenant_id': state['tenant_id'],
                    'effectiveness_score': 0.85  # Would be calculated
                }
            )
            
            # Store individual agent contributions
            for agent_type, output in state['crew_results'].get('agent_outputs', {}).items():
                await self.memory_manager.store_agent_contribution(
                    agent_type=agent_type,
                    contribution=output,
                    task_context=state['query']
                )
        
        return state
    
    async def synthesize_results(self, state: CrewState) -> CrewState:
        """Synthesize crew results into final output"""
        logger.info("Synthesizing results")
        
        if not state['crew_results'].get('success', False):
            state["synthesis"] = "Unable to complete the requested task due to errors."
            state["confidence_score"] = 0.2
            return state
        
        # Use LLM to synthesize all agent outputs
        agent_outputs = state['crew_results'].get('agent_outputs', {})
        
        messages = [
            SystemMessage(content="You are a master synthesizer. Create a comprehensive response from multiple agent outputs."),
            HumanMessage(content=f"""
Original query: {state['query']}

Agent outputs:
{json.dumps(agent_outputs, indent=2)}

Memory context:
- Similar past tasks: {len(state['memory_context'].get('episodic', []))}
- Relevant knowledge: {len(state['memory_context'].get('semantic', []))}

Create a cohesive, well-structured response that addresses the original query.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        state["synthesis"] = response.content
        state["confidence_score"] = 0.85  # Would be calculated based on agent consensus
        
        return state
    
    async def quality_check(self, state: CrewState) -> CrewState:
        """Check quality of synthesized results"""
        logger.info("Performing quality check")
        
        # Simple quality checks
        synthesis_length = len(state.get("synthesis", ""))
        confidence = state.get("confidence_score", 0)
        
        # Determine if refinement is needed
        if synthesis_length < 100 or confidence < 0.7:
            state["needs_refinement"] = True
        else:
            state["needs_refinement"] = False
        
        return state
    
    async def refine_with_memory(self, state: CrewState) -> CrewState:
        """Refine results using additional memory context"""
        logger.info("Refining with memory insights")
        
        # Retrieve more specific memories
        detailed_memories = await self.memory_manager.retrieve_relevant_memories(
            query=state['synthesis'],
            context={
                'task_type': state['task_type'],
                'refinement': True
            },
            memory_types=['semantic']
        )
        
        messages = [
            SystemMessage(content="You are a quality improver. Enhance the response using additional context."),
            HumanMessage(content=f"""
Original response: {state['synthesis']}

Additional context from memory:
{json.dumps(detailed_memories.get('semantic', [])[:3], indent=2)}

Improve the response by:
1. Adding relevant details from memory
2. Ensuring completeness
3. Improving clarity

Query: {state['query']}
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        state["synthesis"] = response.content
        state["confidence_score"] = min(0.95, state.get("confidence_score", 0.7) + 0.1)
        
        return state
    
    def should_refine(self, state: CrewState) -> str:
        """Determine if refinement is needed"""
        if state.get("needs_refinement", False) and state.get("iteration", 0) < 2:
            return "refine"
        return "done"
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the graph"""
        # Initialize state
        initial_state = CrewState(
            query=input_data.get("query", ""),
            task_type=input_data.get("task_type", "general"),
            tenant_id=input_data.get("tenant_id", self.tenant_id),
            user_id=input_data.get("user_id"),
            selected_agents=[],
            tasks=[],
            crew_results=None,
            memory_context={},
            synthesis=None,
            confidence_score=None,
            needs_refinement=False,
            iteration=0,
            metadata=input_data.get("metadata", {})
        )
        
        # Run graph
        result = await self.graph.ainvoke(initial_state, config)
        
        # Return formatted result
        return {
            "synthesis": result.get("synthesis", ""),
            "confidence_score": result.get("confidence_score", 0.0),
            "agents_used": result.get("selected_agents", []),
            "memory_insights": len(result.get("memory_context", {}).get("semantic", [])),
            "success": result.get("crew_results", {}).get("success", False),
            "_iterations": result.get("iteration", 0)
        }
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from graph execution"""
        initial_state = CrewState(
            query=input_data.get("query", ""),
            task_type=input_data.get("task_type", "general"),
            tenant_id=input_data.get("tenant_id", self.tenant_id),
            user_id=input_data.get("user_id"),
            selected_agents=[],
            tasks=[],
            crew_results=None,
            memory_context={},
            synthesis=None,
            confidence_score=None,
            needs_refinement=False,
            iteration=0,
            metadata=input_data.get("metadata", {})
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="analyze_task",
                    name="Analyze Task",
                    type="llm",
                    description="Analyze task requirements and complexity"
                ).dict(),
                GraphNode(
                    id="retrieve_memory",
                    name="Retrieve Memory",
                    type="memory",
                    description="Retrieve relevant memories for context"
                ).dict(),
                GraphNode(
                    id="select_agents",
                    name="Select Agents",
                    type="orchestration",
                    description="Select appropriate agents based on task"
                ).dict(),
                GraphNode(
                    id="create_tasks",
                    name="Create Tasks",
                    type="planning",
                    description="Create specific tasks for agents"
                ).dict(),
                GraphNode(
                    id="execute_crew",
                    name="Execute Crew",
                    type="execution",
                    description="Execute CrewAI with selected agents"
                ).dict(),
                GraphNode(
                    id="update_memory",
                    name="Update Memory",
                    type="memory",
                    description="Store results in memory"
                ).dict(),
                GraphNode(
                    id="synthesize_results",
                    name="Synthesize Results",
                    type="llm",
                    description="Synthesize agent outputs"
                ).dict(),
                GraphNode(
                    id="quality_check",
                    name="Quality Check",
                    type="analysis",
                    description="Check output quality"
                ).dict(),
                GraphNode(
                    id="refine_with_memory",
                    name="Refine with Memory",
                    type="llm",
                    description="Enhance using memory insights"
                ).dict()
            ],
            "edges": [
                {"from": "analyze_task", "to": "retrieve_memory"},
                {"from": "retrieve_memory", "to": "select_agents"},
                {"from": "select_agents", "to": "create_tasks"},
                {"from": "create_tasks", "to": "execute_crew"},
                {"from": "execute_crew", "to": "update_memory"},
                {"from": "update_memory", "to": "synthesize_results"},
                {"from": "synthesize_results", "to": "quality_check"},
                {"from": "quality_check", "to": "refine_with_memory", "condition": "needs_refinement"},
                {"from": "quality_check", "to": "END", "condition": "done"},
                {"from": "refine_with_memory", "to": "END"}
            ],
            "entry_point": "analyze_task",
            "description": "Orchestrate CrewAI agents with memory-enhanced decision making"
        }