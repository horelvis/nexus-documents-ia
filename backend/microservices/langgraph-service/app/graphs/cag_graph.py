"""
CAG Graph - Contextual Augmented Generation with LangGraph
Integrates CAG Engine with RAG for superior document-based Q&A
"""
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
import asyncio
from datetime import datetime

from app.schemas.graph import GraphNode
from app.core.cag_engine import (
    CAGEngine, 
    CAGConfig, 
    ContextChunk, 
    ContextSource,
    ContextGapType
)
from app.graphs.rag_graph import EnhancedRAGGraph


class CAGGraphState(TypedDict):
    """State for CAG-enhanced RAG graph"""
    # Input
    query: str
    tenant_id: str
    user_id: Optional[str]
    
    # Configuration
    enable_cag: bool
    max_iterations: int
    quality_threshold: float
    
    # RAG State
    rag_results: Optional[List[Dict[str, Any]]]
    rag_context: Optional[str]
    
    # CAG State
    context_chunks: List[Dict[str, Any]]
    identified_gaps: List[Dict[str, Any]]
    expansion_history: List[Dict[str, Any]]
    
    # Generation State
    current_response: Optional[str]
    quality_metrics: Dict[str, float]
    iteration_count: int
    
    # Final Output
    final_answer: Optional[str]
    confidence_score: Optional[float]
    metadata: Dict[str, Any]


class CAGGraph:
    """CAG-enhanced RAG graph with iterative context expansion"""
    
    def __init__(
        self, 
        llm, 
        embeddings, 
        qdrant_client, 
        checkpointer, 
        tenant_id: str,
        cag_config: Optional[CAGConfig] = None,
        **kwargs
    ):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.checkpointer = checkpointer
        self.tenant_id = tenant_id
        
        # Initialize CAG Engine
        from app.services.vector_service import VectorService
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=qdrant_client,
            embeddings=embeddings
        )
        
        self.cag_config = cag_config or CAGConfig()
        self.cag_engine = CAGEngine(
            llm=llm,
            embeddings=embeddings,
            vector_service=vector_service,
            config=self.cag_config
        )
        
        # Initialize RAG Graph
        self.rag_graph = EnhancedRAGGraph(
            llm=llm,
            embeddings=embeddings,
            qdrant_client=qdrant_client,
            checkpointer=checkpointer,
            tenant_id=tenant_id
        )
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the CAG-enhanced graph"""
        workflow = StateGraph(CAGGraphState)
        
        # Add nodes
        workflow.add_node("initialize", self.initialize_state)
        workflow.add_node("initial_rag_search", self.initial_rag_search)
        workflow.add_node("evaluate_context", self.evaluate_context)
        workflow.add_node("detect_gaps", self.detect_gaps)
        workflow.add_node("expand_context", self.expand_context)
        workflow.add_node("generate_response", self.generate_response)
        workflow.add_node("validate_quality", self.validate_quality)
        workflow.add_node("finalize_response", self.finalize_response)
        
        # Set entry point
        workflow.set_entry_point("initialize")
        
        # Add edges
        workflow.add_edge("initialize", "initial_rag_search")
        workflow.add_edge("initial_rag_search", "evaluate_context")
        
        # Conditional edges based on CAG enablement
        workflow.add_conditional_edges(
            "evaluate_context",
            self.should_use_cag,
            {
                "use_cag": "detect_gaps",
                "skip_cag": "generate_response"
            }
        )
        
        workflow.add_edge("detect_gaps", "expand_context")
        workflow.add_edge("expand_context", "generate_response")
        workflow.add_edge("generate_response", "validate_quality")
        
        # Conditional iteration or finalization
        workflow.add_conditional_edges(
            "validate_quality",
            self.should_iterate,
            {
                "iterate": "detect_gaps",
                "finalize": "finalize_response"
            }
        )
        
        workflow.add_edge("finalize_response", END)
        
        # Compile without checkpointer for now (TODO: fix checkpointer type)
        return workflow.compile()
    
    async def initialize_state(self, state: CAGGraphState) -> CAGGraphState:
        """Initialize the state with defaults"""
        logger.info(f"Initializing CAG Graph for query: {state['query']}")
        
        state["enable_cag"] = state.get("enable_cag", True)
        state["max_iterations"] = state.get("max_iterations", self.cag_config.max_iterations)
        state["quality_threshold"] = state.get("quality_threshold", self.cag_config.quality_threshold)
        state["iteration_count"] = 0
        state["context_chunks"] = []
        state["identified_gaps"] = []
        state["expansion_history"] = []
        state["quality_metrics"] = {}
        state["metadata"] = {}
        
        return state
    
    async def initial_rag_search(self, state: CAGGraphState) -> CAGGraphState:
        """Perform initial RAG search"""
        logger.info("Performing initial RAG search")
        
        # Use the existing RAG graph
        rag_result = await self.rag_graph.ainvoke({
            "query": state["query"],
            "tenant_id": state["tenant_id"],
            "user_id": state.get("user_id"),
            "max_results": 10,
            "include_sources": True
        })
        
        # Extract results
        state["rag_results"] = rag_result.get("search_results", [])
        state["rag_context"] = self._build_rag_context(rag_result)
        
        # Convert RAG results to context chunks
        context_chunks = []
        for i, result in enumerate(state["rag_results"][:5]):
            chunk = {
                "content": result.get("content", ""),
                "source": ContextSource.VECTOR_SEARCH.value,
                "relevance_score": result.get("score", 0.0),
                "timestamp": datetime.utcnow().isoformat(),
                "chunk_id": f"rag_{i}",
                "metadata": result.get("metadata", {})
            }
            context_chunks.append(chunk)
        
        state["context_chunks"] = context_chunks
        
        return state
    
    async def evaluate_context(self, state: CAGGraphState) -> CAGGraphState:
        """Evaluate if context is sufficient"""
        logger.info("Evaluating context sufficiency")
        
        # Simple heuristic: check if we have enough high-quality context
        high_quality_chunks = [
            chunk for chunk in state["context_chunks"]
            if chunk["relevance_score"] > 0.7
        ]
        
        has_sufficient_context = len(high_quality_chunks) >= 3
        
        # Store evaluation in metadata
        state["metadata"]["initial_context_evaluation"] = {
            "total_chunks": len(state["context_chunks"]),
            "high_quality_chunks": len(high_quality_chunks),
            "sufficient": has_sufficient_context
        }
        
        return state
    
    def should_use_cag(self, state: CAGGraphState) -> str:
        """Decide whether to use CAG based on context evaluation"""
        if not state["enable_cag"]:
            return "skip_cag"
        
        # Use CAG if context might be insufficient
        evaluation = state["metadata"].get("initial_context_evaluation", {})
        if evaluation.get("sufficient", True):
            return "skip_cag"
        
        return "use_cag"
    
    async def detect_gaps(self, state: CAGGraphState) -> CAGGraphState:
        """Detect gaps in current context"""
        logger.info(f"Detecting gaps (iteration {state['iteration_count'] + 1})")
        
        # Convert state chunks to ContextChunk objects
        context_chunks = [
            ContextChunk(
                content=chunk["content"],
                source=ContextSource(chunk["source"]),
                relevance_score=chunk["relevance_score"],
                timestamp=datetime.fromisoformat(chunk["timestamp"]),
                chunk_id=chunk["chunk_id"],
                metadata=chunk.get("metadata", {})
            )
            for chunk in state["context_chunks"]
        ]
        
        # Use CAG engine's gap detector
        gaps = await self.cag_engine.gap_detector.detect_gaps(
            query=state["query"],
            current_context=context_chunks,
            current_response=state.get("current_response")
        )
        
        # Convert gaps to dict format for state
        gap_dicts = []
        for gap in gaps:
            gap_dict = {
                "gap_type": gap.gap_type.value,
                "description": gap.description,
                "confidence": gap.confidence,
                "keywords": gap.keywords,
                "priority": gap.priority,
                "filled": gap.filled
            }
            gap_dicts.append(gap_dict)
        
        state["identified_gaps"].extend(gap_dicts)
        
        return state
    
    async def expand_context(self, state: CAGGraphState) -> CAGGraphState:
        """Expand context based on identified gaps"""
        logger.info("Expanding context for identified gaps")
        
        # Get unfilled gaps
        unfilled_gaps = [
            gap for gap in state["identified_gaps"]
            if not gap["filled"]
        ]
        
        if not unfilled_gaps:
            return state
        
        # Sort by priority
        unfilled_gaps.sort(key=lambda g: g["priority"], reverse=True)
        
        # Expand for top gaps
        expansion_count = 0
        for gap in unfilled_gaps[:3]:  # Top 3 gaps
            try:
                # Create search query
                search_query = f"{gap['description']} {' '.join(gap['keywords'][:2])}"
                
                # Search for additional context
                from app.services.vector_service import VectorService
                vector_service = VectorService(
                    tenant_id=state["tenant_id"],
                    qdrant_client=self.qdrant_client,
                    embeddings=self.embeddings
                )
                
                results = await vector_service.search_similar(
                    query=search_query,
                    limit=3,
                    filters=None
                )
                
                # Add new chunks
                for result in results:
                    if result["score"] > self.cag_config.min_relevance_score:
                        chunk = {
                            "content": result["text"],
                            "source": ContextSource.VECTOR_SEARCH.value,
                            "relevance_score": result["score"],
                            "timestamp": datetime.utcnow().isoformat(),
                            "chunk_id": f"exp_{state['iteration_count']}_{expansion_count}",
                            "metadata": {
                                **result.get("metadata", {}),
                                "gap_type": gap["gap_type"],
                                "expansion_iteration": state["iteration_count"]
                            }
                        }
                        state["context_chunks"].append(chunk)
                        expansion_count += 1
                        gap["filled"] = True
                
            except Exception as e:
                logger.error(f"Error expanding context for gap: {e}")
        
        # Record expansion
        state["expansion_history"].append({
            "iteration": state["iteration_count"],
            "gaps_processed": len(unfilled_gaps[:3]),
            "chunks_added": expansion_count
        })
        
        return state
    
    async def generate_response(self, state: CAGGraphState) -> CAGGraphState:
        """Generate response with current context"""
        logger.info("Generating response with current context")
        
        # Build context text from chunks
        context_chunks = sorted(
            state["context_chunks"],
            key=lambda c: c["relevance_score"],
            reverse=True
        )
        
        context_text = "\n\n".join([
            f"[Score: {chunk['relevance_score']:.2f}]\n{chunk['content']}"
            for chunk in context_chunks[:10]  # Top 10 chunks
        ])
        
        # Generate response
        messages = [
            SystemMessage(content="""You are a helpful assistant that provides accurate, comprehensive answers based on the given context.
            Use the context to answer the query as completely as possible.
            If information is missing or unclear, acknowledge it.
            Cite context scores when referencing specific information."""),
            HumanMessage(content=f"""
Context:
{context_text}

Query: {state['query']}

Provide a comprehensive answer based on the context above.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        state["current_response"] = response.content
        
        return state
    
    async def validate_quality(self, state: CAGGraphState) -> CAGGraphState:
        """Validate response quality"""
        logger.info("Validating response quality")
        
        # Use quality validator
        context_chunks = [
            ContextChunk(
                content=chunk["content"],
                source=ContextSource(chunk["source"]),
                relevance_score=chunk["relevance_score"],
                timestamp=datetime.fromisoformat(chunk["timestamp"]),
                chunk_id=chunk["chunk_id"],
                metadata=chunk.get("metadata", {})
            )
            for chunk in state["context_chunks"]
        ]
        
        validation_result = await self.cag_engine.quality_validator.validate_response(
            query=state["query"],
            response=state["current_response"],
            context=context_chunks,
            config=self.cag_config
        )
        
        state["quality_metrics"] = validation_result["metrics"]
        state["confidence_score"] = validation_result["quality_score"]
        
        # Increment iteration count
        state["iteration_count"] += 1
        
        return state
    
    def should_iterate(self, state: CAGGraphState) -> str:
        """Decide whether to iterate or finalize"""
        
        # Check quality threshold
        quality_score = state.get("confidence_score", 0)
        if quality_score >= state["quality_threshold"]:
            return "finalize"
        
        # Check iteration limit
        if state["iteration_count"] >= state["max_iterations"]:
            return "finalize"
        
        # Check if there are unfilled gaps
        unfilled_gaps = [
            gap for gap in state["identified_gaps"]
            if not gap["filled"]
        ]
        
        if not unfilled_gaps:
            return "finalize"
        
        return "iterate"
    
    async def finalize_response(self, state: CAGGraphState) -> CAGGraphState:
        """Finalize the response with metadata"""
        logger.info("Finalizing CAG response")
        
        state["final_answer"] = state["current_response"]
        
        # Add comprehensive metadata
        state["metadata"].update({
            "cag_iterations": state["iteration_count"],
            "total_context_chunks": len(state["context_chunks"]),
            "gaps_identified": len(state["identified_gaps"]),
            "gaps_filled": len([g for g in state["identified_gaps"] if g["filled"]]),
            "quality_metrics": state["quality_metrics"],
            "confidence_score": state["confidence_score"],
            "expansion_history": state["expansion_history"]
        })
        
        return state
    
    def _build_rag_context(self, rag_result: Dict[str, Any]) -> str:
        """Build context text from RAG results"""
        sources = rag_result.get("sources", [])
        if not sources:
            return ""
        
        context_parts = []
        for source in sources[:5]:  # Top 5 sources
            context_parts.append(source.get("content", ""))
        
        return "\n\n".join(context_parts)
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the CAG graph"""
        
        # Initialize state
        initial_state = CAGGraphState(
            query=input_data["query"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            enable_cag=input_data.get("enable_cag", True),
            max_iterations=input_data.get("max_iterations", self.cag_config.max_iterations),
            quality_threshold=input_data.get("quality_threshold", self.cag_config.quality_threshold),
            rag_results=None,
            rag_context=None,
            context_chunks=[],
            identified_gaps=[],
            expansion_history=[],
            current_response=None,
            quality_metrics={},
            iteration_count=0,
            final_answer=None,
            confidence_score=None,
            metadata={}
        )
        
        # Run graph
        result = await self.graph.ainvoke(initial_state, config)
        
        # Return formatted result
        return {
            "answer": result.get("final_answer", ""),
            "confidence_score": result.get("confidence_score", 0.0),
            "metadata": result.get("metadata", {}),
            "sources": [
                {
                    "content": chunk["content"][:200] + "...",
                    "score": chunk["relevance_score"],
                    "metadata": chunk.get("metadata", {})
                }
                for chunk in result.get("context_chunks", [])[:5]
            ]
        }
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from graph execution"""
        initial_state = CAGGraphState(
            query=input_data["query"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            enable_cag=input_data.get("enable_cag", True),
            max_iterations=input_data.get("max_iterations", self.cag_config.max_iterations),
            quality_threshold=input_data.get("quality_threshold", self.cag_config.quality_threshold),
            rag_results=None,
            rag_context=None,
            context_chunks=[],
            identified_gaps=[],
            expansion_history=[],
            current_response=None,
            quality_metrics={},
            iteration_count=0,
            final_answer=None,
            confidence_score=None,
            metadata={}
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="initialize",
                    name="Initialize State",
                    type="setup",
                    description="Initialize CAG state with defaults"
                ).dict(),
                GraphNode(
                    id="initial_rag_search",
                    name="Initial RAG Search",
                    type="search",
                    description="Perform initial RAG search for context"
                ).dict(),
                GraphNode(
                    id="evaluate_context",
                    name="Evaluate Context",
                    type="analysis",
                    description="Evaluate if initial context is sufficient"
                ).dict(),
                GraphNode(
                    id="detect_gaps",
                    name="Detect Gaps",
                    type="analysis",
                    description="Identify missing information in context"
                ).dict(),
                GraphNode(
                    id="expand_context",
                    name="Expand Context",
                    type="search",
                    description="Search for additional context to fill gaps"
                ).dict(),
                GraphNode(
                    id="generate_response",
                    name="Generate Response",
                    type="llm",
                    description="Generate response with current context"
                ).dict(),
                GraphNode(
                    id="validate_quality",
                    name="Validate Quality",
                    type="validation",
                    description="Validate response quality and completeness"
                ).dict(),
                GraphNode(
                    id="finalize_response",
                    name="Finalize Response",
                    type="output",
                    description="Finalize response with metadata"
                ).dict()
            ],
            "edges": [
                {"from": "initialize", "to": "initial_rag_search"},
                {"from": "initial_rag_search", "to": "evaluate_context"},
                {"from": "evaluate_context", "to": "detect_gaps", "condition": "needs_cag"},
                {"from": "evaluate_context", "to": "generate_response", "condition": "skip_cag"},
                {"from": "detect_gaps", "to": "expand_context"},
                {"from": "expand_context", "to": "generate_response"},
                {"from": "generate_response", "to": "validate_quality"},
                {"from": "validate_quality", "to": "detect_gaps", "condition": "iterate"},
                {"from": "validate_quality", "to": "finalize_response", "condition": "finalize"},
                {"from": "finalize_response", "to": "END"}
            ],
            "entry_point": "initialize",
            "description": "CAG-enhanced RAG with iterative context expansion and quality validation"
        }