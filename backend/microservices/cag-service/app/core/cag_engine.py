"""
Contextual Augmented Generation (CAG) Engine
A sophisticated system for dynamic context expansion and iterative generation refinement
"""
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime
import hashlib
import json

from loguru import logger
from pydantic import BaseModel, Field
import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.language_models import BaseLLM
from langchain_core.embeddings import Embeddings

# Vector store will be injected per-tenant


class ContextGapType(str, Enum):
    """Types of context gaps that can be identified"""
    MISSING_DEFINITION = "missing_definition"
    UNCLEAR_REFERENCE = "unclear_reference"
    TEMPORAL_GAP = "temporal_gap"
    CAUSAL_GAP = "causal_gap"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    FACTUAL_DETAIL = "factual_detail"
    RELATIONSHIP_GAP = "relationship_gap"


# Alias for compatibility
GapType = ContextGapType


@dataclass
class ResponseQuality:
    """Quality assessment for a response"""
    coherence_score: float
    completeness_score: float
    accuracy_score: float
    relevance_score: float
    overall_score: float
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class ContextSource(str, Enum):
    """Sources for context expansion"""
    VECTOR_SEARCH = "vector_search"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    EXTERNAL_API = "external_api"
    DOCUMENT_STORE = "document_store"
    CONVERSATION_HISTORY = "conversation_history"
    AGENT_MEMORY = "agent_memory"


@dataclass
class ContextGap:
    """Represents a gap in the current context"""
    gap_type: ContextGapType
    description: str
    confidence: float
    keywords: List[str]
    priority: int = 5  # 1-10, higher is more important
    filled: bool = False
    fill_attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextChunk:
    """A chunk of context with metadata"""
    content: str
    source: ContextSource
    relevance_score: float
    timestamp: datetime
    chunk_id: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.chunk_id:
            # Generate deterministic ID based on content
            self.chunk_id = hashlib.md5(self.content.encode()).hexdigest()[:12]


class CAGState(BaseModel):
    """Complete state for CAG processing"""
    query: str
    context_chunks: List[ContextChunk] = Field(default_factory=list)  # For service compatibility
    initial_context: List[ContextChunk] = Field(default_factory=list)
    expanded_context: List[ContextChunk] = Field(default_factory=list)
    identified_gaps: List[ContextGap] = Field(default_factory=list)
    generation_history: List[Dict[str, Any]] = Field(default_factory=list)
    current_response: str = ""  # Changed to non-optional with default
    final_answer: str = ""  # Added for service compatibility
    quality_metrics: Dict[str, float] = Field(default_factory=dict)
    quality_score: float = 0.0  # Added for service compatibility
    iteration_count: int = 0
    max_iterations: int = 5
    tenant_id: str = "default"  # Made optional with default
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


class CAGConfig(BaseModel):
    """Configuration for CAG Engine"""
    max_context_size: int = 10000  # tokens
    max_iterations: int = 5
    min_relevance_score: float = 0.6
    gap_detection_threshold: float = 0.7
    quality_threshold: float = 0.8
    enable_external_sources: bool = False
    context_overlap_ratio: float = 0.2
    temperature_schedule: List[float] = Field(default=[0.3, 0.5, 0.7])  # Temperature per iteration
    
    # Advanced settings
    enable_semantic_clustering: bool = True
    cluster_similarity_threshold: float = 0.85
    enable_contradiction_detection: bool = True
    enable_fact_checking: bool = True
    
    # Performance settings
    parallel_context_expansion: bool = True
    max_parallel_searches: int = 3
    cache_ttl_seconds: int = 3600


class ContextExpansionStrategy:
    """Strategy for expanding context based on identified gaps"""
    
    def __init__(self, vector_store, llm: BaseLLM, embeddings: Embeddings):
        self.vector_store = vector_store
        self.llm = llm
        self.embeddings = embeddings
    
    async def expand_for_gap(
        self,
        gap: ContextGap,
        current_context: List[ContextChunk],
        config: CAGConfig
    ) -> List[ContextChunk]:
        """Expand context for a specific gap"""
        
        # Build search query based on gap type and keywords
        search_query = self._build_search_query(gap)
        
        # Search for relevant content
        if config.parallel_context_expansion:
            search_tasks = [
                self._search_vector_store(search_query, config),
                self._search_conversation_history(gap, current_context),
                self._search_domain_knowledge(gap) if gap.gap_type == ContextGapType.DOMAIN_KNOWLEDGE else None
            ]
            
            results = await asyncio.gather(*[task for task in search_tasks if task])
            new_chunks = []
            for result in results:
                if result:
                    new_chunks.extend(result)
        else:
            new_chunks = await self._search_vector_store(search_query, config)
        
        # Filter and rank new chunks
        filtered_chunks = await self._filter_and_rank_chunks(
            new_chunks,
            current_context,
            gap,
            config
        )
        
        return filtered_chunks
    
    def _build_search_query(self, gap: ContextGap) -> str:
        """Build an optimized search query for the gap"""
        query_parts = [gap.description]
        
        if gap.keywords:
            # Add important keywords
            query_parts.extend(gap.keywords[:3])
        
        # Add gap-type specific terms
        gap_type_queries = {
            ContextGapType.MISSING_DEFINITION: "definition meaning explanation",
            ContextGapType.UNCLEAR_REFERENCE: "refers to reference about",
            ContextGapType.TEMPORAL_GAP: "when timeline chronology date",
            ContextGapType.CAUSAL_GAP: "because cause reason why",
            ContextGapType.DOMAIN_KNOWLEDGE: "background context domain",
            ContextGapType.FACTUAL_DETAIL: "fact detail specific information",
            ContextGapType.RELATIONSHIP_GAP: "relationship between connection"
        }
        
        if gap.gap_type in gap_type_queries:
            query_parts.append(gap_type_queries[gap.gap_type])
        
        return " ".join(query_parts)
    
    async def _search_vector_store(
        self,
        query: str,
        config: CAGConfig
    ) -> List[ContextChunk]:
        """Search vector store for relevant content"""
        try:
            if not self.vector_store:
                logger.warning("No vector store available for search")
                return []
            
            # Use Qdrant vector store's similarity search
            results = await asyncio.to_thread(
                self.vector_store.similarity_search_with_score,
                query,
                k=5
            )
            
            chunks = []
            for doc, score in results:
                # Qdrant returns score as distance, convert to similarity
                relevance_score = 1.0 - score  # Assuming cosine distance
                if relevance_score >= config.min_relevance_score:
                    chunk = ContextChunk(
                        content=doc.page_content,
                        source=ContextSource.VECTOR_SEARCH,
                        relevance_score=relevance_score,
                        timestamp=datetime.utcnow(),
                        chunk_id=doc.metadata.get("id", ""),
                        metadata=doc.metadata
                    )
                    chunks.append(chunk)
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []
    
    async def _search_conversation_history(
        self,
        gap: ContextGap,
        current_context: List[ContextChunk]
    ) -> List[ContextChunk]:
        """Search conversation history for relevant context"""
        # Extract conversation history from current context
        history_chunks = [
            chunk for chunk in current_context
            if chunk.source == ContextSource.CONVERSATION_HISTORY
        ]
        
        # TODO: Implement more sophisticated history search
        return []
    
    async def _search_domain_knowledge(self, gap: ContextGap) -> List[ContextChunk]:
        """Search domain-specific knowledge bases"""
        # TODO: Implement domain knowledge search
        return []
    
    async def _filter_and_rank_chunks(
        self,
        new_chunks: List[ContextChunk],
        current_context: List[ContextChunk],
        gap: ContextGap,
        config: CAGConfig
    ) -> List[ContextChunk]:
        """Filter and rank chunks to avoid redundancy and ensure quality"""
        
        # Remove duplicates
        unique_chunks = self._remove_duplicate_chunks(new_chunks, current_context, config)
        
        # Score chunks based on gap relevance
        scored_chunks = await self._score_chunks_for_gap(unique_chunks, gap)
        
        # Sort by score and take top chunks
        scored_chunks.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return scored_chunks[:3]  # Take top 3 chunks per gap
    
    def _remove_duplicate_chunks(
        self,
        new_chunks: List[ContextChunk],
        current_context: List[ContextChunk],
        config: CAGConfig
    ) -> List[ContextChunk]:
        """Remove chunks that are too similar to existing context"""
        
        unique_chunks = []
        existing_contents = {chunk.content for chunk in current_context}
        
        for chunk in new_chunks:
            # Simple duplicate check - in production, use embeddings similarity
            if chunk.content not in existing_contents:
                unique_chunks.append(chunk)
        
        return unique_chunks
    
    async def _score_chunks_for_gap(
        self,
        chunks: List[ContextChunk],
        gap: ContextGap
    ) -> List[ContextChunk]:
        """Score chunks based on their relevance to the specific gap"""
        
        # For now, use existing relevance scores
        # In production, re-score based on gap-specific criteria
        return chunks


class GapDetector:
    """Detects gaps in the current context"""
    
    def __init__(self, llm: BaseLLM):
        self.llm = llm
    
    async def detect_gaps(
        self,
        query: str,
        current_context: List[ContextChunk],
        current_response: Optional[str] = None
    ) -> List[ContextGap]:
        """Detect gaps in the current context"""
        
        # Prepare context for analysis
        context_text = "\n\n".join([chunk.content for chunk in current_context])
        
        # Use LLM to identify gaps
        gap_detection_prompt = self._create_gap_detection_prompt(
            query, context_text, current_response
        )
        
        messages = [
            SystemMessage(content="""You are an expert at identifying missing information and context gaps.
            Analyze the query and available context to identify what information is missing or unclear.
            Return a JSON array of gaps with their type, description, and keywords."""),
            HumanMessage(content=gap_detection_prompt)
        ]
        
        try:
            response = await self.llm.ainvoke(messages, config={"temperature": 0.2})
            gaps = self._parse_gap_response(response.content)
            return gaps
            
        except Exception as e:
            logger.error(f"Error detecting gaps: {e}")
            return []
    
    def _create_gap_detection_prompt(
        self,
        query: str,
        context: str,
        current_response: Optional[str]
    ) -> str:
        """Create prompt for gap detection"""
        
        prompt = f"""
Query: {query}

Available Context:
{context[:2000]}  # Limit context size

{f"Current Response: {current_response}" if current_response else ""}

Identify gaps in the context that prevent a complete answer. For each gap, provide:
1. gap_type: One of [missing_definition, unclear_reference, temporal_gap, causal_gap, domain_knowledge, factual_detail, relationship_gap]
2. description: Brief description of what's missing
3. keywords: 2-3 keywords to search for this information
4. priority: 1-10 (10 being most critical)

Return as JSON array. Example:
[
    {{
        "gap_type": "missing_definition",
        "description": "Definition of 'CAG' acronym not provided",
        "keywords": ["CAG", "definition", "meaning"],
        "priority": 9
    }}
]
"""
        return prompt
    
    def _parse_gap_response(self, response: str) -> List[ContextGap]:
        """Parse LLM response into ContextGap objects"""
        gaps = []
        
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                gap_data = json.loads(json_match.group())
                
                for gap_dict in gap_data:
                    gap = ContextGap(
                        gap_type=ContextGapType(gap_dict.get("gap_type", "domain_knowledge")),
                        description=gap_dict.get("description", ""),
                        confidence=0.8,  # Default confidence
                        keywords=gap_dict.get("keywords", []),
                        priority=gap_dict.get("priority", 5)
                    )
                    gaps.append(gap)
                    
        except Exception as e:
            logger.warning(f"Failed to parse gap response: {e}")
        
        return gaps


class QualityValidator:
    """Validates the quality of generated responses"""
    
    def __init__(self, llm: BaseLLM):
        self.llm = llm
    
    async def validate_response(
        self,
        query: str,
        response: str,
        context: List[ContextChunk],
        config: CAGConfig
    ) -> Dict[str, Any]:
        """Validate response quality across multiple dimensions"""
        
        validation_tasks = [
            self._check_completeness(query, response),
            self._check_accuracy(response, context),
            self._check_coherence(response),
            self._check_relevance(query, response)
        ]
        
        if config.enable_contradiction_detection:
            validation_tasks.append(self._check_contradictions(response, context))
        
        results = await asyncio.gather(*validation_tasks)
        
        # Aggregate scores
        quality_metrics = {
            "completeness": results[0],
            "accuracy": results[1],
            "coherence": results[2],
            "relevance": results[3]
        }
        
        if config.enable_contradiction_detection:
            quality_metrics["no_contradictions"] = results[4]
        
        # Calculate overall quality score
        quality_score = np.mean(list(quality_metrics.values()))
        
        return {
            "quality_score": quality_score,
            "metrics": quality_metrics,
            "passes_threshold": quality_score >= config.quality_threshold
        }
    
    async def _check_completeness(self, query: str, response: str) -> float:
        """Check if response completely addresses the query"""
        
        prompt = f"""
Query: {query}
Response: {response}

Rate how completely the response addresses all aspects of the query on a scale of 0-1.
Consider if all questions are answered and all requested information is provided.
Return only a number between 0 and 1.
"""
        
        messages = [
            SystemMessage(content="You are an expert at evaluating response completeness."),
            HumanMessage(content=prompt)
        ]
        
        try:
            result = await self.llm.ainvoke(messages, config={"temperature": 0})
            score = float(result.content.strip())
            return min(max(score, 0), 1)  # Ensure in range [0, 1]
        except:
            return 0.5  # Default score on error
    
    async def _check_accuracy(self, response: str, context: List[ContextChunk]) -> float:
        """Check if response is accurate based on context"""
        # Simplified implementation - in production, use fact-checking
        return 0.85
    
    async def _check_coherence(self, response: str) -> float:
        """Check if response is coherent and well-structured"""
        # Simplified implementation
        return 0.9
    
    async def _check_relevance(self, query: str, response: str) -> float:
        """Check if response is relevant to the query"""
        # Simplified implementation
        return 0.85
    
    async def _check_contradictions(self, response: str, context: List[ContextChunk]) -> float:
        """Check for contradictions between response and context"""
        # Simplified implementation
        return 0.95


class CAGEngine:
    """Main Contextual Augmented Generation Engine"""
    
    def __init__(
        self,
        llm: BaseLLM,
        embeddings: Embeddings,
        vector_store=None,  # Will be set per-tenant
        config: Optional[CAGConfig] = None
    ):
        self.llm = llm
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.config = config or CAGConfig()
        
        # Initialize components
        self.context_expander = ContextExpansionStrategy(vector_store, llm, embeddings)
        self.gap_detector = GapDetector(llm)
        self.quality_validator = QualityValidator(llm)
        
        # Cache for context expansion
        self._context_cache: Dict[str, List[ContextChunk]] = {}
    
    async def generate(
        self,
        query: str,
        initial_context: Optional[List[ContextChunk]] = None,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Main CAG generation method"""
        
        # Initialize state
        state = CAGState(
            query=query,
            initial_context=initial_context or [],
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata or {},
            max_iterations=self.config.max_iterations
        )
        
        # Main CAG loop
        while state.iteration_count < state.max_iterations:
            state.iteration_count += 1
            logger.info(f"CAG iteration {state.iteration_count}/{state.max_iterations}")
            
            # 1. Detect gaps in current context
            gaps = await self.gap_detector.detect_gaps(
                state.query,
                state.initial_context + state.expanded_context,
                state.current_response
            )
            state.identified_gaps.extend(gaps)
            
            # 2. Expand context for high-priority gaps
            if gaps:
                await self._expand_context_for_gaps(state, gaps)
            
            # 3. Generate response with current context
            response = await self._generate_response(state)
            state.current_response = response
            
            # 4. Validate response quality
            validation_result = await self.quality_validator.validate_response(
                state.query,
                response,
                state.initial_context + state.expanded_context,
                self.config
            )
            state.quality_metrics = validation_result["metrics"]
            
            # 5. Store generation in history
            state.generation_history.append({
                "iteration": state.iteration_count,
                "response": response,
                "quality_metrics": validation_result["metrics"],
                "gaps_identified": len(gaps),
                "context_size": len(state.initial_context) + len(state.expanded_context)
            })
            
            # 6. Check if quality threshold is met
            if validation_result["passes_threshold"]:
                logger.info(f"Quality threshold met at iteration {state.iteration_count}")
                break
            
            # 7. Check if no more gaps to fill
            unfilled_gaps = [g for g in state.identified_gaps if not g.filled]
            if not unfilled_gaps:
                logger.info("No more gaps to fill")
                break
        
        # Update final state
        state.final_answer = state.current_response
        state.quality_score = state.quality_metrics.get("quality_score", 0)
        
        # Return final result
        return {
            "response": state.current_response,
            "quality_score": state.quality_metrics.get("quality_score", 0),
            "iterations": state.iteration_count,
            "context_chunks_used": len(state.initial_context) + len(state.expanded_context),
            "gaps_identified": len(state.identified_gaps),
            "gaps_filled": len([g for g in state.identified_gaps if g.filled]),
            "metadata": {
                "quality_metrics": state.quality_metrics,
                "generation_history": state.generation_history,
                "final_context_size": sum(len(c.content) for c in state.initial_context + state.expanded_context)
            }
        }
    
    async def process(self, state: CAGState) -> CAGState:
        """Process method for service compatibility - wraps generate method"""
        # Sync initial_context with context_chunks if provided
        if state.context_chunks and not state.initial_context:
            state.initial_context = state.context_chunks
        
        # Update vector store for tenant if needed
        if hasattr(self, 'context_expander') and self.vector_store:
            self.context_expander.vector_store = self.vector_store
        
        # Call generate with state data
        result = await self.generate(
            query=state.query,
            initial_context=state.initial_context,
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            metadata=state.metadata
        )
        
        # Update state with results
        state.final_answer = result["response"]
        state.quality_score = result["quality_score"]
        state.iteration_count = result["iterations"]
        state.quality_metrics = result["metadata"]["quality_metrics"]
        state.generation_history = result["metadata"]["generation_history"]
        
        # Update context chunks for compatibility
        state.context_chunks = state.initial_context + state.expanded_context
        
        return state
    
    async def _expand_context_for_gaps(self, state: CAGState, gaps: List[ContextGap]) -> None:
        """Expand context for identified gaps"""
        
        # Sort gaps by priority
        gaps.sort(key=lambda g: g.priority, reverse=True)
        
        # Expand context for top gaps
        expansion_tasks = []
        for gap in gaps[:self.config.max_parallel_searches]:
            if not gap.filled and gap.fill_attempts < 3:
                task = self.context_expander.expand_for_gap(
                    gap,
                    state.initial_context + state.expanded_context,
                    self.config
                )
                expansion_tasks.append((gap, task))
        
        # Execute expansions
        for gap, task in expansion_tasks:
            try:
                new_chunks = await task
                if new_chunks:
                    state.expanded_context.extend(new_chunks)
                    gap.filled = len(new_chunks) > 0
                gap.fill_attempts += 1
            except Exception as e:
                logger.error(f"Error expanding context for gap: {e}")
    
    async def _generate_response(self, state: CAGState) -> str:
        """Generate response with current context"""
        
        # Prepare context
        all_context = state.initial_context + state.expanded_context
        
        # Sort by relevance
        all_context.sort(key=lambda c: c.relevance_score, reverse=True)
        
        # Build context text
        context_text = "\n\n".join([
            f"[Source: {chunk.source.value}]\n{chunk.content}"
            for chunk in all_context[:10]  # Limit context items
        ])
        
        # Select temperature based on iteration
        temperature_idx = min(state.iteration_count - 1, len(self.config.temperature_schedule) - 1)
        temperature = self.config.temperature_schedule[temperature_idx]
        
        # Generate response
        messages = [
            SystemMessage(content="""You are a helpful assistant that provides comprehensive, accurate answers based on the given context.
            Use ALL relevant information from the context to answer the query completely.
            If the context contains contradictory information, acknowledge it.
            If information is missing, clearly state what is missing."""),
            HumanMessage(content=f"""
Context:
{context_text}

Query: {state.query}

Provide a comprehensive answer based on the context above.
""")
        ]
        
        response = await self.llm.ainvoke(messages, config={"temperature": temperature})
        
        return response.content