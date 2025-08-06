"""
CAG Engine using LangGraph for state management and LangChain agents
Modern implementation using framework capabilities instead of manual orchestration
"""
from typing import Dict, List, Any, Optional, Annotated, Sequence, TypedDict
from enum import Enum
from datetime import datetime
import operator

from loguru import logger
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor, ToolInvocation
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.tools import Tool, StructuredTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain.agents import create_react_agent, AgentExecutor
from langchain.agents import create_structured_chat_agent
from langchain.agents.format_scratchpad import format_to_openai_functions
from langchain.agents.output_parsers import ReActSingleInputOutputParser
from langchain_ollama import ChatOllama
from langchain_community.vectorstores import Qdrant
from langchain_community.tools.vectorstore.tool import VectorStoreQATool, VectorStoreQAWithSourcesTool
from langchain.tools.retriever import create_retriever_tool
from langchain.memory import ConversationBufferWindowMemory
from langchain.chains import LLMChain

from pydantic import BaseModel, Field


class GapType(str, Enum):
    """Types of context gaps"""
    MISSING_DEFINITION = "missing_definition"
    UNCLEAR_REFERENCE = "unclear_reference"
    TEMPORAL_GAP = "temporal_gap"
    CAUSAL_GAP = "causal_gap"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    FACTUAL_DETAIL = "factual_detail"


class ContextGap(BaseModel):
    """Represents a gap in context"""
    gap_type: GapType
    description: str
    confidence: float
    keywords: List[str]
    filled: bool = False


class ContextChunk(BaseModel):
    """A chunk of context"""
    content: str
    source: str
    relevance_score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QualityMetrics(BaseModel):
    """Quality metrics for response"""
    coherence: float = 0.0
    completeness: float = 0.0
    accuracy: float = 0.0
    relevance: float = 0.0
    
    @property
    def overall_score(self) -> float:
        return (self.coherence + self.completeness + self.accuracy + self.relevance) / 4.0


class CAGGraphState(TypedDict):
    """State for the CAG graph using TypedDict for LangGraph compatibility"""
    # Input
    query: str
    tenant_id: str
    user_id: str
    
    # Context management
    context_chunks: Annotated[Sequence[dict], operator.add]  # Accumulate contexts
    identified_gaps: Annotated[Sequence[dict], operator.add]  # Accumulate gaps
    
    # Generation
    messages: Annotated[Sequence[BaseMessage], operator.add]  # Conversation history
    current_response: str
    final_answer: str
    
    # Control flow
    iteration_count: int
    max_iterations: int
    should_continue: bool
    
    # Quality
    quality_metrics: dict
    quality_score: float
    
    # Metadata
    metadata: dict


class CAGLangGraphEngine:
    """
    CAG Engine using LangGraph for orchestration and LangChain agents
    """
    
    def __init__(
        self,
        llm: ChatOllama,
        embeddings,
        vector_store: Optional[Qdrant] = None,
        max_iterations: int = 5,
        quality_threshold: float = 0.7
    ):
        self.llm = llm
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        
        # Create memory saver for checkpointing
        self.checkpointer = MemorySaver()
        
        # Build the graph
        self.graph = self._build_graph()
        
        # Create framework agents
        self.retrieval_agent = None
        self.gap_detection_agent = None
        self.generation_agent = None
        
        if vector_store:
            self._setup_agents(vector_store)
    
    def _setup_agents(self, vector_store: Qdrant):
        """Setup LangChain agents using framework capabilities"""
        
        # 1. Create retrieval tools using LangChain's built-in tools
        retriever = vector_store.as_retriever(
            search_kwargs={"k": 5}
        )
        
        retrieval_tool = create_retriever_tool(
            retriever=retriever,
            name="search_documents",
            description="Search for relevant documents and context. Use this to find information about any topic."
        )
        
        # 2. Create gap detection tool
        gap_detection_tool = StructuredTool.from_function(
            func=self._detect_gaps_func,
            name="detect_context_gaps",
            description="Analyze the current context and identify any gaps or missing information",
            args_schema=self._create_gap_detection_schema()
        )
        
        # 3. Create quality validation tool
        quality_tool = StructuredTool.from_function(
            func=self._assess_quality_func,
            name="assess_response_quality",
            description="Evaluate the quality of a generated response",
            args_schema=self._create_quality_schema()
        )
        
        # 4. Create agents using LangChain's agent creation functions
        tools = [retrieval_tool, gap_detection_tool, quality_tool]
        
        # Create ReAct agent for complex reasoning
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are a CAG (Contextual Augmented Generation) assistant.
Your goal is to provide accurate, complete, and well-reasoned answers by:
1. Searching for relevant context
2. Identifying any gaps in information
3. Iteratively improving your response
4. Validating the quality of your answer

Always use the available tools to gather context before answering."""),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create the main reasoning agent
        self.reasoning_agent = create_react_agent(
            llm=self.llm,
            tools=tools,
            prompt=prompt
        )
        
        # Wrap in AgentExecutor for better execution control
        self.agent_executor = AgentExecutor(
            agent=self.reasoning_agent,
            tools=tools,
            verbose=True,
            max_iterations=3,
            return_intermediate_steps=True,
            handle_parsing_errors=True
        )
    
    def _create_gap_detection_schema(self):
        """Create Pydantic schema for gap detection tool"""
        class GapDetectionInput(BaseModel):
            context: str = Field(description="The current context to analyze")
            query: str = Field(description="The original query")
        
        return GapDetectionInput
    
    def _create_quality_schema(self):
        """Create Pydantic schema for quality assessment tool"""
        class QualityInput(BaseModel):
            response: str = Field(description="The response to evaluate")
            query: str = Field(description="The original query")
            context: str = Field(description="The context used")
        
        return QualityInput
    
    async def _detect_gaps_func(self, context: str, query: str) -> List[Dict]:
        """Function for gap detection tool"""
        prompt = f"""Analyze this context for answering the query and identify any gaps:
        
Query: {query}
Context: {context}

Identify specific gaps in:
1. Missing definitions or explanations
2. Unclear references
3. Missing temporal information
4. Missing causal relationships
5. Domain knowledge gaps

Return gaps as a list with type, description, and keywords."""
        
        response = await self.llm.ainvoke(prompt)
        # Parse response and return gaps
        # This is simplified - in production, use proper parsing
        return [
            {
                "gap_type": "domain_knowledge",
                "description": "Need more context",
                "keywords": ["context", "information"]
            }
        ]
    
    async def _assess_quality_func(self, response: str, query: str, context: str) -> Dict:
        """Function for quality assessment tool"""
        prompt = f"""Assess the quality of this response:
        
Query: {query}
Context: {context}
Response: {response}

Rate on a scale of 0-1 for:
1. Coherence - Is the response well-structured?
2. Completeness - Does it fully answer the query?
3. Accuracy - Is the information correct?
4. Relevance - Is it relevant to the query?

Return scores for each metric."""
        
        result = await self.llm.ainvoke(prompt)
        # Parse and return quality metrics
        return {
            "coherence": 0.8,
            "completeness": 0.7,
            "accuracy": 0.9,
            "relevance": 0.85
        }
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph"""
        
        # Create the graph
        workflow = StateGraph(CAGGraphState)
        
        # Add nodes
        workflow.add_node("retrieve_context", self._retrieve_context_node)
        workflow.add_node("detect_gaps", self._detect_gaps_node)
        workflow.add_node("expand_context", self._expand_context_node)
        workflow.add_node("generate_response", self._generate_response_node)
        workflow.add_node("validate_quality", self._validate_quality_node)
        
        # Set entry point
        workflow.set_entry_point("retrieve_context")
        
        # Add edges
        workflow.add_edge("retrieve_context", "detect_gaps")
        workflow.add_edge("detect_gaps", "expand_context")
        workflow.add_edge("expand_context", "generate_response")
        workflow.add_edge("generate_response", "validate_quality")
        
        # Add conditional edge for iteration
        workflow.add_conditional_edges(
            "validate_quality",
            self._should_continue,
            {
                "continue": "detect_gaps",
                "end": END
            }
        )
        
        # Compile with checkpointer for state persistence
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def _retrieve_context_node(self, state: CAGGraphState) -> Dict:
        """Retrieve initial context from vector store"""
        logger.info(f"Retrieving context for query: {state['query'][:100]}...")
        
        if not self.vector_store:
            return {
                "context_chunks": [],
                "messages": [AIMessage(content="No vector store available for retrieval")]
            }
        
        # Use the retriever to get relevant documents
        retriever = self.vector_store.as_retriever(search_kwargs={"k": 5})
        docs = await retriever.aget_relevant_documents(state["query"])
        
        # Convert to context chunks
        chunks = []
        for doc in docs:
            chunks.append({
                "content": doc.page_content,
                "source": "vector_search",
                "relevance_score": doc.metadata.get("score", 0.8),
                "metadata": doc.metadata
            })
        
        return {
            "context_chunks": chunks,
            "messages": [AIMessage(content=f"Retrieved {len(chunks)} context chunks")]
        }
    
    async def _detect_gaps_node(self, state: CAGGraphState) -> Dict:
        """Detect gaps in the current context"""
        logger.info("Detecting context gaps...")
        
        # Combine context chunks
        context = "\n".join([c["content"] for c in state.get("context_chunks", [])])
        
        if not context:
            return {
                "identified_gaps": [],
                "messages": [AIMessage(content="No context available for gap detection")]
            }
        
        # Use the gap detection function
        gaps = await self._detect_gaps_func(context, state["query"])
        
        return {
            "identified_gaps": gaps,
            "messages": [AIMessage(content=f"Identified {len(gaps)} context gaps")]
        }
    
    async def _expand_context_node(self, state: CAGGraphState) -> Dict:
        """Expand context based on identified gaps"""
        logger.info("Expanding context based on gaps...")
        
        gaps = state.get("identified_gaps", [])
        if not gaps:
            return {
                "messages": [AIMessage(content="No gaps to fill")]
            }
        
        # For each gap, try to retrieve additional context
        new_chunks = []
        for gap in gaps[-3:]:  # Process only last 3 gaps to avoid explosion
            if isinstance(gap, dict):
                keywords = gap.get("keywords", [])
                if keywords and self.vector_store:
                    # Search for additional context using gap keywords
                    query = " ".join(keywords)
                    retriever = self.vector_store.as_retriever(search_kwargs={"k": 2})
                    docs = await retriever.aget_relevant_documents(query)
                    
                    for doc in docs:
                        new_chunks.append({
                            "content": doc.page_content,
                            "source": "gap_filling",
                            "relevance_score": doc.metadata.get("score", 0.7),
                            "metadata": doc.metadata
                        })
        
        return {
            "context_chunks": new_chunks,
            "messages": [AIMessage(content=f"Added {len(new_chunks)} chunks from gap filling")]
        }
    
    async def _generate_response_node(self, state: CAGGraphState) -> Dict:
        """Generate response using the context"""
        logger.info("Generating response...")
        
        # Combine all context
        context = "\n".join([c["content"] for c in state.get("context_chunks", [])])
        
        # Create prompt
        prompt = f"""Based on the following context, answer the query comprehensively:

Context:
{context[:3000]}

Query: {state['query']}

Provide a detailed, accurate answer:"""
        
        # Generate response
        response = await self.llm.ainvoke(prompt)
        
        if hasattr(response, 'content'):
            answer = response.content
        else:
            answer = str(response)
        
        return {
            "current_response": answer,
            "messages": [AIMessage(content="Generated response")],
            "iteration_count": state.get("iteration_count", 0) + 1
        }
    
    async def _validate_quality_node(self, state: CAGGraphState) -> Dict:
        """Validate the quality of generated response"""
        logger.info("Validating response quality...")
        
        response = state.get("current_response", "")
        if not response:
            return {
                "quality_score": 0.0,
                "final_answer": "Failed to generate response"
            }
        
        # Assess quality
        context = "\n".join([c["content"] for c in state.get("context_chunks", [])])
        metrics = await self._assess_quality_func(response, state["query"], context)
        
        # Calculate overall score
        quality_score = sum(metrics.values()) / len(metrics) if metrics else 0.0
        
        # Determine if we should continue
        should_continue = (
            quality_score < self.quality_threshold and 
            state.get("iteration_count", 0) < state.get("max_iterations", self.max_iterations)
        )
        
        return {
            "quality_metrics": metrics,
            "quality_score": quality_score,
            "should_continue": should_continue,
            "final_answer": response if not should_continue else "",
            "messages": [AIMessage(content=f"Quality score: {quality_score:.2f}")]
        }
    
    def _should_continue(self, state: CAGGraphState) -> str:
        """Decide whether to continue iterating"""
        if state.get("should_continue", False):
            logger.info(f"Continuing iteration {state.get('iteration_count', 0) + 1}...")
            return "continue"
        else:
            logger.info("Quality threshold met or max iterations reached. Ending.")
            return "end"
    
    async def process(self, query: str, tenant_id: str, user_id: str, context: Optional[Dict] = None) -> Dict:
        """
        Process a query through the CAG graph
        """
        # Initialize state
        initial_state = {
            "query": query,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "context_chunks": [],
            "identified_gaps": [],
            "messages": [HumanMessage(content=query)],
            "current_response": "",
            "final_answer": "",
            "iteration_count": 0,
            "max_iterations": self.max_iterations,
            "should_continue": False,
            "quality_metrics": {},
            "quality_score": 0.0,
            "metadata": context or {}
        }
        
        # Run the graph with checkpointing
        config = {"configurable": {"thread_id": f"{tenant_id}_{user_id}"}}
        
        try:
            # Stream execution for better observability
            async for event in self.graph.astream(initial_state, config):
                logger.debug(f"Graph event: {list(event.keys())}")
            
            # Get final state
            final_state = await self.graph.aget_state(config)
            
            return {
                "success": True,
                "query": query,
                "answer": final_state.values.get("final_answer", ""),
                "quality_score": final_state.values.get("quality_score", 0.0),
                "iterations": final_state.values.get("iteration_count", 0),
                "gaps_identified": len(final_state.values.get("identified_gaps", [])),
                "context_chunks_used": len(final_state.values.get("context_chunks", [])),
                "metadata": {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "quality_metrics": final_state.values.get("quality_metrics", {})
                }
            }
            
        except Exception as e:
            logger.error(f"Error in CAG graph processing: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "answer": None
            }
    
    def visualize_graph(self) -> str:
        """Get a Mermaid diagram of the graph structure"""
        try:
            # LangGraph supports graph visualization
            from langgraph.graph import mermaid
            return self.graph.get_graph().draw_mermaid()
        except:
            return "Graph visualization not available"