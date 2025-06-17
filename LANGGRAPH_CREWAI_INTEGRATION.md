# LangGraph + CrewAI Integration: Agent Orchestration & Memory Management

## Executive Summary

This document outlines the integration strategy for combining LangGraph's stateful workflow capabilities with CrewAI's agent orchestration framework to create a powerful multi-agent system with advanced memory management for Nexus Document.

## 1. Architecture Overview

### 1.1 Current State
- **LangGraph**: Stateful workflows, checkpointing, conditional logic
- **CrewAI**: Agent roles, task delegation, team coordination
- **Need**: Combine both for sophisticated multi-agent orchestration

### 1.2 Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Orchestrator                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   CrewAI    │  │   Memory    │  │ Checkpoint  │         │
│  │   Agents    │  │   Manager   │  │   Store     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         │                │                 │                  │
│  ┌──────┴──────┬────────┴────────┬───────┴──────┐          │
│  │ Research    │ Document        │ Analysis      │          │
│  │ Agent       │ Processor       │ Agent         │          │
│  └─────────────┘ Agent          └───────────────┘          │
│                 └────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

## 2. Integration Design

### 2.1 CrewAI Agent Types for Nexus Document

```python
from crewai import Agent, Task, Crew
from typing import List, Dict, Any

class NexusAgentFactory:
    """Factory for creating specialized agents"""
    
    @staticmethod
    def create_research_agent(llm) -> Agent:
        return Agent(
            role='Document Research Specialist',
            goal='Find and analyze relevant documents for user queries',
            backstory='Expert in document retrieval and semantic search',
            tools=['qdrant_search', 'keyword_search', 'metadata_filter'],
            llm=llm,
            verbose=True
        )
    
    @staticmethod
    def create_analyst_agent(llm) -> Agent:
        return Agent(
            role='Financial Document Analyst',
            goal='Extract insights from financial documents',
            backstory='Specialized in invoice analysis and financial reporting',
            tools=['extract_tables', 'calculate_totals', 'identify_patterns'],
            llm=llm,
            verbose=True
        )
    
    @staticmethod
    def create_summarizer_agent(llm) -> Agent:
        return Agent(
            role='Document Summarizer',
            goal='Create concise summaries of complex documents',
            backstory='Expert in distilling key information',
            tools=['text_rank', 'extractive_summary', 'abstractive_summary'],
            llm=llm,
            verbose=True
        )
```

### 2.2 LangGraph + CrewAI Orchestration Graph

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any
import json

class CrewState(TypedDict):
    """State for CrewAI orchestration"""
    query: str
    agents: List[str]
    tasks: List[Dict[str, Any]]
    results: Dict[str, Any]
    memory: Dict[str, Any]
    iteration: int
    crew_output: Optional[str]

class CrewAIOrchestrationGraph:
    """LangGraph for orchestrating CrewAI agents"""
    
    def __init__(self, llm, embeddings, memory_store, checkpointer):
        self.llm = llm
        self.embeddings = embeddings
        self.memory_store = memory_store
        self.checkpointer = checkpointer
        self.agent_factory = NexusAgentFactory()
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(CrewState)
        
        # Nodes
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("select_agents", self.select_agents)
        workflow.add_node("create_tasks", self.create_tasks)
        workflow.add_node("execute_crew", self.execute_crew)
        workflow.add_node("update_memory", self.update_memory)
        workflow.add_node("synthesize_results", self.synthesize_results)
        workflow.add_node("quality_check", self.quality_check)
        workflow.add_node("refine_with_memory", self.refine_with_memory)
        
        # Flow
        workflow.set_entry_point("analyze_query")
        workflow.add_edge("analyze_query", "select_agents")
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
        
        return workflow.compile(checkpointer=self.checkpointer)
```

## 3. Memory Management System

### 3.1 Unified Memory Architecture

```python
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

class UnifiedMemoryManager:
    """Manages memory across LangGraph state and CrewAI agents"""
    
    def __init__(self, redis_client, vector_store):
        self.redis_client = redis_client
        self.vector_store = vector_store
        self.memory_types = {
            'episodic': EpisodicMemory(),      # Specific interactions
            'semantic': SemanticMemory(),       # Domain knowledge
            'procedural': ProceduralMemory(),   # Task patterns
            'working': WorkingMemory()          # Current context
        }
    
    async def store_interaction(
        self,
        agent_id: str,
        task: str,
        result: Any,
        metadata: Dict[str, Any]
    ):
        """Store agent interaction in multiple memory types"""
        
        # Episodic memory - specific event
        episode = {
            'agent_id': agent_id,
            'task': task,
            'result': result,
            'timestamp': datetime.utcnow().isoformat(),
            'metadata': metadata
        }
        await self.memory_types['episodic'].store(episode)
        
        # Semantic memory - extract knowledge
        if knowledge := self._extract_knowledge(result):
            await self.memory_types['semantic'].store(knowledge)
        
        # Procedural memory - successful patterns
        if metadata.get('success', False):
            pattern = {
                'task_type': metadata.get('task_type'),
                'agent_role': metadata.get('agent_role'),
                'approach': metadata.get('approach'),
                'effectiveness': metadata.get('effectiveness_score')
            }
            await self.memory_types['procedural'].store(pattern)
    
    async def retrieve_relevant_memories(
        self,
        query: str,
        context: Dict[str, Any],
        memory_types: List[str] = None
    ) -> Dict[str, List[Any]]:
        """Retrieve relevant memories for current task"""
        
        memories = {}
        types_to_search = memory_types or self.memory_types.keys()
        
        for mem_type in types_to_search:
            if mem_type in self.memory_types:
                memories[mem_type] = await self.memory_types[mem_type].retrieve(
                    query, context
                )
        
        return memories
```

### 3.2 Memory-Enhanced Agent Decision Making

```python
class MemoryEnhancedAgent:
    """CrewAI agent with integrated memory capabilities"""
    
    def __init__(self, base_agent: Agent, memory_manager: UnifiedMemoryManager):
        self.agent = base_agent
        self.memory = memory_manager
    
    async def execute_with_memory(self, task: Task) -> Any:
        """Execute task with memory context"""
        
        # Retrieve relevant memories
        memories = await self.memory.retrieve_relevant_memories(
            query=task.description,
            context={
                'agent_role': self.agent.role,
                'task_type': task.metadata.get('type')
            }
        )
        
        # Enhance task context with memories
        enhanced_context = self._build_enhanced_context(task, memories)
        
        # Execute task
        result = await self.agent.execute(task, context=enhanced_context)
        
        # Store new memory
        await self.memory.store_interaction(
            agent_id=self.agent.id,
            task=task.description,
            result=result,
            metadata={
                'task_type': task.metadata.get('type'),
                'agent_role': self.agent.role,
                'success': self._evaluate_success(result),
                'approach': enhanced_context.get('approach_used')
            }
        )
        
        return result
```

## 4. Implementation Examples

### 4.1 Financial Document Analysis Crew

```python
class FinancialAnalysisCrew:
    """Multi-agent crew for financial document analysis"""
    
    def __init__(self, llm, memory_manager):
        self.llm = llm
        self.memory = memory_manager
        
        # Create specialized agents
        self.invoice_agent = Agent(
            role='Invoice Specialist',
            goal='Extract and validate invoice data',
            tools=['ocr_extract', 'validate_totals', 'check_tax']
        )
        
        self.expense_agent = Agent(
            role='Expense Analyst',
            goal='Categorize and analyze expenses',
            tools=['categorize_expense', 'trend_analysis', 'anomaly_detection']
        )
        
        self.compliance_agent = Agent(
            role='Compliance Officer',
            goal='Ensure regulatory compliance',
            tools=['check_regulations', 'validate_format', 'flag_issues']
        )
    
    async def analyze_financial_documents(self, documents: List[Dict]):
        """Orchestrate financial analysis across multiple agents"""
        
        # Create crew with memory enhancement
        crew = Crew(
            agents=[
                MemoryEnhancedAgent(self.invoice_agent, self.memory),
                MemoryEnhancedAgent(self.expense_agent, self.memory),
                MemoryEnhancedAgent(self.compliance_agent, self.memory)
            ],
            tasks=[
                Task(
                    description="Extract all invoice data",
                    agent=self.invoice_agent,
                    tools=['ocr_extract']
                ),
                Task(
                    description="Analyze expense patterns",
                    agent=self.expense_agent,
                    dependencies=['extract_invoice_data']
                ),
                Task(
                    description="Verify compliance",
                    agent=self.compliance_agent,
                    dependencies=['extract_invoice_data']
                )
            ],
            verbose=True
        )
        
        # Execute with LangGraph orchestration
        return await crew.kickoff()
```

### 4.2 Document Research and Synthesis Workflow

```python
class ResearchSynthesisGraph:
    """LangGraph for research and synthesis with CrewAI"""
    
    async def research_and_synthesize(self, state: Dict[str, Any]):
        """Complex research workflow with multiple agents"""
        
        # Phase 1: Research Crew
        research_crew = Crew(
            agents=[
                self.create_research_agent("legal_specialist"),
                self.create_research_agent("technical_specialist"),
                self.create_research_agent("business_specialist")
            ],
            tasks=self._create_research_tasks(state['query'])
        )
        
        research_results = await research_crew.kickoff()
        
        # Phase 2: Analysis Crew
        analysis_crew = Crew(
            agents=[
                self.create_analyst_agent("comparative_analyst"),
                self.create_analyst_agent("risk_analyst")
            ],
            tasks=self._create_analysis_tasks(research_results)
        )
        
        analysis_results = await analysis_crew.kickoff()
        
        # Phase 3: Synthesis with Memory
        synthesis_agent = MemoryEnhancedAgent(
            Agent(
                role='Master Synthesizer',
                goal='Create comprehensive report',
                tools=['markdown_formatter', 'citation_manager']
            ),
            self.memory_manager
        )
        
        # Retrieve similar past syntheses
        past_syntheses = await self.memory_manager.retrieve_relevant_memories(
            query=state['query'],
            memory_types=['semantic', 'episodic']
        )
        
        final_report = await synthesis_agent.execute_with_memory(
            Task(
                description="Create final synthesis report",
                context={
                    'research': research_results,
                    'analysis': analysis_results,
                    'past_examples': past_syntheses
                }
            )
        )
        
        return final_report
```

## 5. Advanced Memory Patterns

### 5.1 Collaborative Memory

```python
class CollaborativeMemory:
    """Shared memory system for agent collaboration"""
    
    def __init__(self):
        self.shared_insights = {}
        self.agent_expertise = {}
        self.task_history = []
    
    async def share_insight(
        self,
        agent_id: str,
        insight: Dict[str, Any],
        visibility: str = 'crew'  # 'crew', 'role', 'all'
    ):
        """Share insights between agents"""
        
        insight_id = f"{agent_id}_{datetime.utcnow().timestamp()}"
        
        self.shared_insights[insight_id] = {
            'agent_id': agent_id,
            'insight': insight,
            'visibility': visibility,
            'timestamp': datetime.utcnow(),
            'accessed_by': []
        }
        
        # Notify relevant agents
        await self._notify_agents(insight, visibility)
    
    async def learn_from_crew(
        self,
        task_result: Dict[str, Any],
        crew_performance: Dict[str, float]
    ):
        """Learn from crew performance"""
        
        # Update agent expertise based on performance
        for agent_id, performance in crew_performance.items():
            if agent_id not in self.agent_expertise:
                self.agent_expertise[agent_id] = {
                    'task_types': {},
                    'success_rate': 0.0,
                    'total_tasks': 0
                }
            
            # Update expertise metrics
            task_type = task_result.get('task_type')
            self.agent_expertise[agent_id]['task_types'][task_type] = performance
            self.agent_expertise[agent_id]['total_tasks'] += 1
```

### 5.2 Memory-Driven Agent Selection

```python
class IntelligentAgentSelector:
    """Select best agents based on memory and past performance"""
    
    def __init__(self, memory_manager: UnifiedMemoryManager):
        self.memory = memory_manager
    
    async def select_optimal_agents(
        self,
        task_requirements: Dict[str, Any],
        available_agents: List[Agent]
    ) -> List[Agent]:
        """Select best agents for task based on historical performance"""
        
        # Retrieve procedural memories (successful patterns)
        successful_patterns = await self.memory.retrieve_relevant_memories(
            query=task_requirements['description'],
            memory_types=['procedural']
        )
        
        # Score agents based on past performance
        agent_scores = {}
        
        for agent in available_agents:
            score = await self._calculate_agent_score(
                agent,
                task_requirements,
                successful_patterns
            )
            agent_scores[agent.id] = score
        
        # Select top agents
        sorted_agents = sorted(
            available_agents,
            key=lambda a: agent_scores[a.id],
            reverse=True
        )
        
        return sorted_agents[:task_requirements.get('team_size', 3)]
```

## 6. Integration with Existing Nexus Document System

### 6.1 Enhanced Document Processing Pipeline

```python
class EnhancedDocumentPipeline:
    """Document processing with CrewAI agents and LangGraph orchestration"""
    
    async def process_document_with_crew(
        self,
        document: Dict[str, Any],
        user_context: Dict[str, Any]
    ):
        """Process document using specialized agent crew"""
        
        # Initialize state
        state = CrewState(
            query=f"Process document: {document['filename']}",
            agents=[],
            tasks=[],
            results={},
            memory={},
            iteration=0
        )
        
        # Run through LangGraph orchestration
        graph = CrewAIOrchestrationGraph(
            llm=self.llm,
            embeddings=self.embeddings,
            memory_store=self.memory_store,
            checkpointer=self.checkpointer
        )
        
        result = await graph.ainvoke(state)
        
        # Store in vector database with enhanced metadata
        await self.store_processed_document(
            document=document,
            processing_result=result,
            agent_metadata=result.get('agent_contributions', {})
        )
        
        return result
```

### 6.2 API Endpoints for CrewAI Integration

```python
@router.post("/crew/execute")
async def execute_crew_task(
    request: CrewExecutionRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Execute a task using CrewAI agents with LangGraph orchestration"""
    
    # Initialize memory manager
    memory_manager = UnifiedMemoryManager(
        redis_client=redis_client,
        vector_store=qdrant_client
    )
    
    # Create crew based on task type
    crew = await create_specialized_crew(
        task_type=request.task_type,
        memory_manager=memory_manager
    )
    
    # Execute with LangGraph
    result = await execute_with_langgraph(
        crew=crew,
        task=request.task,
        context=request.context
    )
    
    return CrewExecutionResponse(
        task_id=result['task_id'],
        status=result['status'],
        results=result['results'],
        agent_contributions=result['agent_contributions'],
        memory_updates=result['memory_updates']
    )
```

## 7. Memory Persistence and Scaling

### 7.1 Distributed Memory Architecture

```python
class DistributedMemoryStore:
    """Scalable memory storage across multiple backends"""
    
    def __init__(self):
        self.backends = {
            'redis': RedisMemoryBackend(),      # Fast access
            'postgres': PostgresMemoryBackend(), # Structured queries
            'qdrant': QdrantMemoryBackend(),     # Semantic search
            's3': S3MemoryBackend()             # Long-term storage
        }
    
    async def store_memory(
        self,
        memory_type: str,
        content: Any,
        ttl: Optional[int] = None
    ):
        """Store memory with appropriate backend selection"""
        
        # Route to appropriate backend based on memory type
        if memory_type == 'working':
            # Short-term, fast access
            await self.backends['redis'].store(content, ttl=ttl or 3600)
        
        elif memory_type == 'episodic':
            # Structured storage with search
            await self.backends['postgres'].store(content)
            # Also store embeddings for semantic search
            embeddings = await generate_embeddings(content)
            await self.backends['qdrant'].store(embeddings)
        
        elif memory_type == 'semantic':
            # Vector storage for similarity search
            await self.backends['qdrant'].store(content)
        
        elif memory_type == 'archival':
            # Long-term storage
            await self.backends['s3'].store(content)
```

## 8. Monitoring and Analytics

### 8.1 Agent Performance Tracking

```python
class AgentPerformanceMonitor:
    """Track and analyze agent performance"""
    
    async def track_agent_metrics(
        self,
        agent_id: str,
        task: Task,
        result: Any,
        execution_time: float
    ):
        """Track detailed agent performance metrics"""
        
        metrics = {
            'agent_id': agent_id,
            'task_type': task.metadata.get('type'),
            'execution_time': execution_time,
            'success': self._evaluate_success(result),
            'confidence': result.get('confidence', 0.0),
            'memory_usage': result.get('memory_stats', {}),
            'timestamp': datetime.utcnow()
        }
        
        # Store in time-series database
        await self.store_metrics(metrics)
        
        # Update agent profile
        await self.update_agent_profile(agent_id, metrics)
        
        # Check for performance anomalies
        if anomaly := await self.detect_anomaly(agent_id, metrics):
            await self.handle_anomaly(anomaly)
```

## 9. Best Practices and Recommendations

### 9.1 Agent Design Principles
1. **Single Responsibility**: Each agent should have one clear role
2. **Memory-Aware**: Agents should leverage historical context
3. **Collaborative**: Design for inter-agent communication
4. **Observable**: Comprehensive logging and metrics

### 9.2 Memory Management Guidelines
1. **Selective Storage**: Not all interactions need long-term memory
2. **Privacy-Aware**: Implement memory access controls
3. **Performance**: Use appropriate backends for memory types
4. **Cleanup**: Implement memory decay and pruning

### 9.3 Orchestration Patterns
1. **Hierarchical**: Lead agents coordinating specialist agents
2. **Peer-to-Peer**: Agents collaborating as equals
3. **Dynamic**: Runtime agent selection based on task
4. **Hybrid**: Combining multiple patterns as needed

## 10. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Install CrewAI dependencies
- [ ] Create base agent templates
- [ ] Implement unified memory manager
- [ ] Basic CrewAI + LangGraph integration

### Phase 2: Core Features (Week 3-4)
- [ ] Financial analysis crew
- [ ] Document research crew
- [ ] Memory persistence layer
- [ ] Performance monitoring

### Phase 3: Advanced Features (Week 5-6)
- [ ] Collaborative memory system
- [ ] Dynamic agent selection
- [ ] Complex orchestration patterns
- [ ] Analytics dashboard

### Phase 4: Production (Week 7-8)
- [ ] Performance optimization
- [ ] Scaling tests
- [ ] Documentation
- [ ] Training materials

## Conclusion

The integration of LangGraph and CrewAI provides a powerful foundation for sophisticated multi-agent systems with advanced memory management. This architecture enables:

1. **Intelligent Orchestration**: LangGraph manages complex workflows while CrewAI handles agent coordination
2. **Persistent Memory**: Unified memory system enhances agent decision-making
3. **Scalability**: Distributed architecture supports growth
4. **Flexibility**: Easy to add new agents and workflows

This combination positions Nexus Document as a leader in intelligent document processing with true multi-agent collaboration.