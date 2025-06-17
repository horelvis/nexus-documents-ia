from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
import asyncio

from app.schemas.graph import GraphNode


class RAGState(TypedDict):
    """State for RAG graph"""
    query: str
    tenant_id: str
    user_id: Optional[str]
    max_results: int
    filters: Optional[Dict[str, Any]]
    include_sources: bool
    
    # Search results from different strategies
    vector_results: Optional[List[Dict[str, Any]]]
    keyword_results: Optional[List[Dict[str, Any]]]
    metadata_results: Optional[List[Dict[str, Any]]]
    
    # Merged and ranked results
    merged_results: Optional[List[Dict[str, Any]]]
    reranked_results: Optional[List[Dict[str, Any]]]
    
    # Generation
    generated_answer: Optional[str]
    confidence_score: Optional[float]
    needs_refinement: bool
    refinement_notes: Optional[str]
    
    # Tracking
    iteration: int


class EnhancedRAGGraph:
    """Enhanced RAG graph with multiple search strategies and quality checks"""
    
    def __init__(self, llm, embeddings, qdrant_client, checkpointer, tenant_id: str, **kwargs):
        self.llm = llm
        self.embeddings = embeddings
        self.qdrant_client = qdrant_client
        self.checkpointer = checkpointer
        self.tenant_id = tenant_id
        self.collection_name = f"documents_{tenant_id}"
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the RAG graph"""
        workflow = StateGraph(RAGState)
        
        # Add nodes
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("vector_search", self.vector_search)
        workflow.add_node("keyword_search", self.keyword_search)
        workflow.add_node("metadata_search", self.metadata_search)
        workflow.add_node("merge_results", self.merge_results)
        workflow.add_node("rerank_results", self.rerank_results)
        workflow.add_node("generate_answer", self.generate_answer)
        workflow.add_node("check_answer_quality", self.check_answer_quality)
        workflow.add_node("refine_answer", self.refine_answer)
        
        # Set entry point
        workflow.set_entry_point("analyze_query")
        
        # Add edges - parallel search
        workflow.add_edge("analyze_query", "vector_search")
        workflow.add_edge("analyze_query", "keyword_search")
        workflow.add_edge("analyze_query", "metadata_search")
        
        # Merge all search results
        workflow.add_edge(["vector_search", "keyword_search", "metadata_search"], "merge_results")
        
        # Continue processing
        workflow.add_edge("merge_results", "rerank_results")
        workflow.add_edge("rerank_results", "generate_answer")
        workflow.add_edge("generate_answer", "check_answer_quality")
        
        # Conditional refinement
        workflow.add_conditional_edges(
            "check_answer_quality",
            self.should_refine,
            {
                "refine": "refine_answer",
                "done": END
            }
        )
        
        workflow.add_edge("refine_answer", END)
        
        # Compile with checkpointer
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def analyze_query(self, state: RAGState) -> RAGState:
        """Analyze query to understand intent and optimize search"""
        logger.info(f"Analyzing query: {state['query']}")
        
        messages = [
            SystemMessage(content="You are a query analyzer. Analyze the user's query and identify key concepts."),
            HumanMessage(content=f"""
Analyze this query and extract:
1. Main intent
2. Key terms for search
3. Type of information needed

Query: {state['query']}

Return a brief analysis.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        
        # Store analysis in state (could be used to optimize search)
        state["iteration"] = state.get("iteration", 0) + 1
        
        return state
    
    async def vector_search(self, state: RAGState) -> RAGState:
        """Perform vector similarity search"""
        logger.info("Performing vector search")
        
        # Simulate vector search results
        # In real implementation, would use embeddings and Qdrant
        state["vector_results"] = [
            {
                "id": "vec_1",
                "content": "Sample vector search result 1",
                "score": 0.95,
                "metadata": {"source": "document1.pdf", "page": 5}
            },
            {
                "id": "vec_2",
                "content": "Sample vector search result 2",
                "score": 0.87,
                "metadata": {"source": "document2.pdf", "page": 12}
            }
        ]
        
        return state
    
    async def keyword_search(self, state: RAGState) -> RAGState:
        """Perform keyword-based search"""
        logger.info("Performing keyword search")
        
        # Simulate keyword search results
        state["keyword_results"] = [
            {
                "id": "key_1",
                "content": "Sample keyword search result 1",
                "score": 0.82,
                "metadata": {"source": "document3.pdf", "page": 3}
            }
        ]
        
        return state
    
    async def metadata_search(self, state: RAGState) -> RAGState:
        """Search based on metadata filters"""
        logger.info("Performing metadata search")
        
        # Simulate metadata search results
        state["metadata_results"] = [
            {
                "id": "meta_1",
                "content": "Sample metadata search result 1",
                "score": 0.78,
                "metadata": {"source": "document4.pdf", "page": 7, "type": "report"}
            }
        ]
        
        return state
    
    async def merge_results(self, state: RAGState) -> RAGState:
        """Merge results from different search strategies"""
        logger.info("Merging search results")
        
        all_results = []
        
        # Add results with source tracking
        for result in state.get("vector_results", []):
            result["search_type"] = "vector"
            all_results.append(result)
        
        for result in state.get("keyword_results", []):
            result["search_type"] = "keyword"
            all_results.append(result)
        
        for result in state.get("metadata_results", []):
            result["search_type"] = "metadata"
            all_results.append(result)
        
        # Remove duplicates and sort by score
        seen_ids = set()
        unique_results = []
        for result in sorted(all_results, key=lambda x: x["score"], reverse=True):
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                unique_results.append(result)
        
        state["merged_results"] = unique_results[:state["max_results"]]
        
        return state
    
    async def rerank_results(self, state: RAGState) -> RAGState:
        """Rerank results using cross-encoder or LLM"""
        logger.info("Reranking results")
        
        # For POC, simple reranking based on relevance prompt
        if not state.get("merged_results"):
            state["reranked_results"] = []
            return state
        
        # In real implementation, would use cross-encoder or LLM-based reranking
        state["reranked_results"] = state["merged_results"]
        
        return state
    
    async def generate_answer(self, state: RAGState) -> RAGState:
        """Generate answer using retrieved context"""
        logger.info("Generating answer")
        
        if not state.get("reranked_results"):
            state["generated_answer"] = "I couldn't find relevant information to answer your question."
            state["confidence_score"] = 0.2
            return state
        
        # Build context from results
        context = "\n\n".join([
            f"[Source: {r['metadata']['source']}, Page: {r['metadata'].get('page', 'N/A')}]\n{r['content']}"
            for r in state["reranked_results"][:3]
        ])
        
        messages = [
            SystemMessage(content="You are a helpful assistant. Answer questions based on the provided context."),
            HumanMessage(content=f"""
Based on the following context, answer the user's question.

Context:
{context}

Question: {state['query']}

Provide a comprehensive answer. If the context doesn't contain enough information, say so.
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        state["generated_answer"] = response.content
        
        # Calculate confidence based on result quality
        if state["reranked_results"]:
            avg_score = sum(r["score"] for r in state["reranked_results"][:3]) / min(3, len(state["reranked_results"]))
            state["confidence_score"] = avg_score
        else:
            state["confidence_score"] = 0.3
        
        return state
    
    async def check_answer_quality(self, state: RAGState) -> RAGState:
        """Check quality of generated answer"""
        logger.info("Checking answer quality")
        
        # Simple quality checks
        answer_length = len(state.get("generated_answer", ""))
        confidence = state.get("confidence_score", 0)
        
        # Determine if refinement is needed
        if answer_length < 50 or confidence < 0.6:
            state["needs_refinement"] = True
        else:
            state["needs_refinement"] = False
        
        return state
    
    async def refine_answer(self, state: RAGState) -> RAGState:
        """Refine answer if quality is low"""
        logger.info("Refining answer")
        
        messages = [
            SystemMessage(content="You are a helpful assistant tasked with improving answers."),
            HumanMessage(content=f"""
The following answer was generated but may need improvement:

Original answer: {state['generated_answer']}
Confidence score: {state['confidence_score']}

Please provide a refined answer that:
1. Is more comprehensive
2. Addresses potential gaps
3. Maintains accuracy

Question: {state['query']}
""")
        ]
        
        response = await self.llm.ainvoke(messages)
        state["generated_answer"] = response.content
        state["refinement_notes"] = "Answer refined for better quality"
        
        return state
    
    def should_refine(self, state: RAGState) -> str:
        """Determine if refinement is needed"""
        if state.get("needs_refinement", False) and state.get("iteration", 0) < 2:
            return "refine"
        return "done"
    
    async def ainvoke(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None):
        """Invoke the graph"""
        # Initialize state
        initial_state = RAGState(
            query=input_data["query"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            max_results=input_data.get("max_results", 5),
            filters=input_data.get("filters"),
            include_sources=input_data.get("include_sources", True),
            vector_results=None,
            keyword_results=None,
            metadata_results=None,
            merged_results=None,
            reranked_results=None,
            generated_answer=None,
            confidence_score=None,
            needs_refinement=False,
            refinement_notes=None,
            iteration=0
        )
        
        # Run graph
        result = await self.graph.ainvoke(initial_state, config)
        
        # Return formatted result
        output = {
            "answer": result.get("generated_answer", ""),
            "confidence_score": result.get("confidence_score", 0.0),
            "refinement_notes": result.get("refinement_notes"),
            "_iterations": result.get("iteration", 0)
        }
        
        if input_data.get("include_sources", True) and result.get("reranked_results"):
            output["sources"] = [
                {
                    "content": r["content"],
                    "metadata": r["metadata"],
                    "score": r["score"]
                }
                for r in result["reranked_results"][:3]
            ]
            output["search_results"] = result.get("reranked_results", [])
        
        return output
    
    async def astream_events(self, input_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None, version: str = "v1"):
        """Stream events from graph execution"""
        initial_state = RAGState(
            query=input_data["query"],
            tenant_id=input_data["tenant_id"],
            user_id=input_data.get("user_id"),
            max_results=input_data.get("max_results", 5),
            filters=input_data.get("filters"),
            include_sources=input_data.get("include_sources", True),
            vector_results=None,
            keyword_results=None,
            metadata_results=None,
            merged_results=None,
            reranked_results=None,
            generated_answer=None,
            confidence_score=None,
            needs_refinement=False,
            refinement_notes=None,
            iteration=0
        )
        
        async for event in self.graph.astream_events(initial_state, config, version=version):
            yield event
    
    @staticmethod
    def get_structure() -> Dict[str, Any]:
        """Get the structure of this graph"""
        return {
            "nodes": [
                GraphNode(
                    id="analyze_query",
                    name="Analyze Query",
                    type="llm",
                    description="Analyze query intent and extract key terms"
                ).dict(),
                GraphNode(
                    id="vector_search",
                    name="Vector Search",
                    type="search",
                    description="Semantic similarity search using embeddings"
                ).dict(),
                GraphNode(
                    id="keyword_search",
                    name="Keyword Search",
                    type="search",
                    description="Traditional keyword-based search"
                ).dict(),
                GraphNode(
                    id="metadata_search",
                    name="Metadata Search",
                    type="search",
                    description="Search using document metadata"
                ).dict(),
                GraphNode(
                    id="merge_results",
                    name="Merge Results",
                    type="processing",
                    description="Merge and deduplicate search results"
                ).dict(),
                GraphNode(
                    id="rerank_results",
                    name="Rerank Results",
                    type="ml",
                    description="Rerank results for relevance"
                ).dict(),
                GraphNode(
                    id="generate_answer",
                    name="Generate Answer",
                    type="llm",
                    description="Generate answer using context"
                ).dict(),
                GraphNode(
                    id="check_answer_quality",
                    name="Check Quality",
                    type="analysis",
                    description="Evaluate answer quality"
                ).dict(),
                GraphNode(
                    id="refine_answer",
                    name="Refine Answer",
                    type="llm",
                    description="Improve answer if needed"
                ).dict()
            ],
            "edges": [
                {"from": "analyze_query", "to": "vector_search"},
                {"from": "analyze_query", "to": "keyword_search"},
                {"from": "analyze_query", "to": "metadata_search"},
                {"from": "vector_search", "to": "merge_results"},
                {"from": "keyword_search", "to": "merge_results"},
                {"from": "metadata_search", "to": "merge_results"},
                {"from": "merge_results", "to": "rerank_results"},
                {"from": "rerank_results", "to": "generate_answer"},
                {"from": "generate_answer", "to": "check_answer_quality"},
                {"from": "check_answer_quality", "to": "refine_answer", "condition": "needs_refinement"},
                {"from": "check_answer_quality", "to": "END", "condition": "done"},
                {"from": "refine_answer", "to": "END"}
            ],
            "entry_point": "analyze_query",
            "description": "Enhanced RAG with multiple search strategies, reranking, and quality checks"
        }