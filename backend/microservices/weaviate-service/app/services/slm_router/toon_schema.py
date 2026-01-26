"""
TOON Schema: Task-Oriented Orchestration Notation

Defines the structured output format for the SLM Router.
TOON plans are deterministic, validated query execution plans that:
1. Route to the appropriate data source (Graph, Vector, Hybrid)
2. Extract and validate entities from queries
3. Define parameterized queries with guardrails
4. Handle ambiguous queries with clarification requests

Version 1.0 - January 2026
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date, datetime
import re
import yaml
import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# GUARDRAILS - Safety limits for query execution
# =============================================================================

class TOONGuardrails:
    """
    Safety guardrails for TOON plan execution.

    These limits prevent runaway queries and protect system resources.
    """

    GRAPH = {
        "limit": {"max": 300, "default": 50},
        "hops": {"max": 4, "default": 2},
        "timeout_ms": {"max": 5000, "default": 2000},
    }

    VECTOR = {
        "top_k": {"max": 12, "default": 5},
        "rerank_limit": {"max": 20, "default": 10},
    }

    SLM = {
        "max_tokens": 512,  # TOON plans are concise
        "temperature": {"max": 0.2, "default": 0.0},
        "timeout_ms": 3000,
    }

    HISTORY = {
        "max_turns": 5,
        "max_tokens": 500,
        "entity_retention": 10,
        "ttl_seconds": 3600,
    }


# =============================================================================
# ENUMS - Route and Operation Types
# =============================================================================

class TOONRoute(str, Enum):
    """
    Primary routing decision for a query.

    - GRAPH_ONLY: Query can be answered entirely from structural graph (Apache AGE)
    - VECTOR_ONLY: Query needs semantic search in vector store (Weaviate)
    - HYBRID: Query needs both graph structure AND semantic content
    - ASK_CLARIFY: Query is too ambiguous, needs user clarification
    """
    GRAPH_ONLY = "GRAPH_ONLY"
    VECTOR_ONLY = "VECTOR_ONLY"
    HYBRID = "HYBRID"
    ASK_CLARIFY = "ASK_CLARIFY"


class GraphOperation(str, Enum):
    """Operations for graph queries."""
    COUNT = "COUNT"        # Count matching nodes
    LIST = "LIST"          # List matching nodes with properties
    EXISTS = "EXISTS"      # Check if nodes exist
    TRAVERSE = "TRAVERSE"  # Traverse relationships
    AGGREGATE = "AGGREGATE"  # Aggregate properties (sum, avg, etc.)


class VectorOperation(str, Enum):
    """Operations for vector queries."""
    SEMANTIC_SEARCH = "SEMANTIC_SEARCH"  # Standard semantic search
    SIMILARITY = "SIMILARITY"              # Find similar documents
    RERANK = "RERANK"                      # Search + rerank results


class EntitySource(str, Enum):
    """Where an entity was extracted from."""
    QUERY = "query"        # Extracted from current query
    HISTORY = "history"    # Resolved from conversation history
    CONTEXT = "context"    # Inferred from tenant context


# =============================================================================
# ENTITY MODELS
# =============================================================================

class ExtractedEntity(BaseModel):
    """
    An entity extracted from the query or resolved from context.

    Entities are the key nouns/concepts that inform query planning:
    - Clients, employees, departments (named entities)
    - Document types, folder types (semantic types)
    - Dates, amounts (value entities)
    """
    name: str = Field(..., description="Entity value (e.g., 'ACME', 'contract')")
    type: str = Field(..., description="Entity type (e.g., 'client', 'document_type')")
    graph_label: Optional[str] = Field(
        None,
        description="Corresponding Apache AGE node label (e.g., 'Entity', 'structural_document')"
    )
    source: EntitySource = Field(
        default=EntitySource.QUERY,
        description="Where this entity came from"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in entity extraction"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure entity name is not empty and sanitized."""
        v = v.strip()
        if not v:
            raise ValueError("Entity name cannot be empty")
        # Prevent injection by removing dangerous characters
        v = re.sub(r'[;\'"\\]', '', v)
        return v


# =============================================================================
# GRAPH QUERY CONFIGURATION
# =============================================================================

class GraphQueryConfig(BaseModel):
    """
    Configuration for graph-based queries using Apache AGE.

    Generates parameterized Cypher queries with safety guardrails.
    """
    enabled: bool = Field(default=False, description="Whether graph query is enabled")
    operation: GraphOperation = Field(
        default=GraphOperation.LIST,
        description="Type of graph operation"
    )
    cypher_template: str = Field(
        default="",
        description="Cypher query template with $param placeholders"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters to bind to the Cypher template"
    )

    # Guardrails
    limit: int = Field(
        default=TOONGuardrails.GRAPH["limit"]["default"],
        le=TOONGuardrails.GRAPH["limit"]["max"],
        description="Maximum results to return"
    )
    hops: int = Field(
        default=TOONGuardrails.GRAPH["hops"]["default"],
        le=TOONGuardrails.GRAPH["hops"]["max"],
        description="Maximum traversal depth"
    )
    timeout_ms: int = Field(
        default=TOONGuardrails.GRAPH["timeout_ms"]["default"],
        le=TOONGuardrails.GRAPH["timeout_ms"]["max"],
        description="Query timeout in milliseconds"
    )

    @field_validator('cypher_template')
    @classmethod
    def validate_cypher(cls, v: str) -> str:
        """Basic validation of Cypher template safety."""
        if not v:
            return v
        # Prevent dangerous operations
        dangerous_patterns = [
            r'\bDELETE\b',
            r'\bDETACH\b',
            r'\bDROP\b',
            r'\bCREATE\b',
            r'\bSET\b',
            r'\bMERGE\b',
            r'\bREMOVE\b',
        ]
        upper_v = v.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, upper_v):
                raise ValueError(f"Dangerous Cypher operation detected: {pattern}")
        return v

    def get_safe_cypher(self) -> str:
        """
        Get the Cypher query with parameters safely bound.

        Uses parameterized queries to prevent injection.
        """
        if not self.cypher_template:
            return ""

        # The template should use $param style placeholders
        # Apache AGE will bind them safely
        return self.cypher_template


# =============================================================================
# VECTOR QUERY CONFIGURATION
# =============================================================================

class DateRange(BaseModel):
    """Date range filter for vector search."""
    start: Optional[date] = None
    end: Optional[date] = None


class VectorFilters(BaseModel):
    """Filters for vector search."""
    document_types: List[str] = Field(
        default_factory=list,
        description="Filter by document types"
    )
    date_range: Optional[DateRange] = Field(
        default=None,
        description="Filter by date range"
    )
    tenant_scope: bool = Field(
        default=True,
        description="True = tenant docs, False = public knowledge"
    )
    folder_paths: List[str] = Field(
        default_factory=list,
        description="Filter by folder paths"
    )
    domains: List[str] = Field(
        default_factory=list,
        description="Filter by domains (legal, fiscal, hr, etc.)"
    )


class VectorQueryConfig(BaseModel):
    """
    Configuration for vector-based queries using Weaviate.

    Supports semantic search with filters and optional reranking.
    """
    enabled: bool = Field(default=False, description="Whether vector query is enabled")
    operation: VectorOperation = Field(
        default=VectorOperation.SEMANTIC_SEARCH,
        description="Type of vector operation"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters for the search"
    )

    # Search configuration
    top_k: int = Field(
        default=TOONGuardrails.VECTOR["top_k"]["default"],
        le=TOONGuardrails.VECTOR["top_k"]["max"],
        description="Number of results to retrieve"
    )
    filters: VectorFilters = Field(
        default_factory=VectorFilters,
        description="Filters to apply to the search"
    )
    rerank: bool = Field(
        default=False,
        description="Whether to apply reranking"
    )
    rerank_limit: int = Field(
        default=TOONGuardrails.VECTOR["rerank_limit"]["default"],
        le=TOONGuardrails.VECTOR["rerank_limit"]["max"],
        description="Number of results to consider for reranking"
    )


# =============================================================================
# CLARIFICATION CONFIGURATION
# =============================================================================

class ClarificationConfig(BaseModel):
    """
    Configuration for asking user clarification.

    Used when the query is too ambiguous to route confidently.
    """
    question: str = Field(
        default="",
        description="The clarification question to ask the user"
    )
    options: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Suggested options for the user"
    )
    missing_info: str = Field(
        default="",
        description="What information is needed to proceed"
    )

    @field_validator('question')
    @classmethod
    def validate_question(cls, v: str) -> str:
        """Ensure question is not empty for ASK_CLARIFY route."""
        return v.strip()


# =============================================================================
# MAIN TOON PLAN MODEL
# =============================================================================

class TOONPlan(BaseModel):
    """
    TOON: Task-Oriented Orchestration Notation

    A complete, validated query execution plan that:
    1. Routes to the appropriate data source
    2. Extracts and validates entities
    3. Defines parameterized queries
    4. Includes safety guardrails

    This is the PRIMARY OUTPUT of the SLM Router.
    """
    version: str = Field(default="1.0", description="TOON schema version")

    # Routing decision
    route: TOONRoute = Field(
        ...,
        description="Primary routing decision"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence in routing decision"
    )

    # Extracted entities
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Entities extracted from the query"
    )

    # Query configurations
    graph: GraphQueryConfig = Field(
        default_factory=GraphQueryConfig,
        description="Graph query configuration"
    )
    vector: VectorQueryConfig = Field(
        default_factory=VectorQueryConfig,
        description="Vector query configuration"
    )

    # Clarification (for ASK_CLARIFY route)
    clarify: ClarificationConfig = Field(
        default_factory=ClarificationConfig,
        description="Clarification configuration"
    )

    # Metadata
    reasoning: str = Field(
        default="",
        description="Explanation of why this plan was generated"
    )
    original_query: str = Field(
        default="",
        description="The original user query"
    )
    tenant_id: str = Field(
        default="",
        description="Tenant ID for isolation"
    )
    session_id: str = Field(
        default="",
        description="Session ID for history tracking"
    )

    @model_validator(mode='after')
    def validate_plan_consistency(self) -> 'TOONPlan':
        """Ensure the plan is internally consistent."""
        route = self.route

        if route == TOONRoute.GRAPH_ONLY:
            if not self.graph.enabled:
                self.graph.enabled = True
            self.vector.enabled = False

        elif route == TOONRoute.VECTOR_ONLY:
            self.graph.enabled = False
            if not self.vector.enabled:
                self.vector.enabled = True

        elif route == TOONRoute.HYBRID:
            if not self.graph.enabled:
                self.graph.enabled = True
            if not self.vector.enabled:
                self.vector.enabled = True

        elif route == TOONRoute.ASK_CLARIFY:
            self.graph.enabled = False
            self.vector.enabled = False
            if not self.clarify.question:
                self.clarify.question = "Could you please provide more details about your request?"
                self.clarify.missing_info = "specific context or intent"

        return self

    def to_yaml(self) -> str:
        """Serialize to YAML for logging/debugging."""
        return yaml.dump(
            self.model_dump(exclude_none=True, exclude_defaults=True),
            default_flow_style=False,
            allow_unicode=True
        )

    def to_json(self) -> str:
        """Serialize to JSON for API responses."""
        return self.model_dump_json(exclude_none=True)

    def apply_guardrails(self) -> 'TOONPlan':
        """
        Apply guardrails to ensure safe execution.

        This is called before execution to enforce limits.
        """
        # Graph guardrails
        if self.graph.enabled:
            self.graph.limit = min(
                self.graph.limit,
                TOONGuardrails.GRAPH["limit"]["max"]
            )
            self.graph.hops = min(
                self.graph.hops,
                TOONGuardrails.GRAPH["hops"]["max"]
            )
            self.graph.timeout_ms = min(
                self.graph.timeout_ms,
                TOONGuardrails.GRAPH["timeout_ms"]["max"]
            )

        # Vector guardrails
        if self.vector.enabled:
            self.vector.top_k = min(
                self.vector.top_k,
                TOONGuardrails.VECTOR["top_k"]["max"]
            )
            self.vector.rerank_limit = min(
                self.vector.rerank_limit,
                TOONGuardrails.VECTOR["rerank_limit"]["max"]
            )

        return self

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get a summary of what this plan will do."""
        summary = {
            "route": self.route.value,
            "confidence": self.confidence,
            "entities_count": len(self.entities),
        }

        if self.graph.enabled:
            summary["graph"] = {
                "operation": self.graph.operation.value,
                "limit": self.graph.limit,
                "hops": self.graph.hops,
            }

        if self.vector.enabled:
            summary["vector"] = {
                "operation": self.vector.operation.value,
                "top_k": self.vector.top_k,
                "rerank": self.vector.rerank,
                "tenant_scope": self.vector.filters.tenant_scope,
            }

        if self.route == TOONRoute.ASK_CLARIFY:
            summary["clarify"] = {
                "question": self.clarify.question,
                "options_count": len(self.clarify.options),
            }

        return summary


# =============================================================================
# TOON PLAN PARSER
# =============================================================================

class TOONParser:
    """
    Parser for TOON plans from SLM output.

    Handles both YAML and JSON formats, with fallback strategies.
    """

    @staticmethod
    def parse(raw_output: str, fallback_route: TOONRoute = TOONRoute.VECTOR_ONLY) -> TOONPlan:
        """
        Parse SLM output into a validated TOONPlan.

        Args:
            raw_output: Raw text output from the SLM
            fallback_route: Route to use if parsing fails completely

        Returns:
            Validated TOONPlan
        """
        # Clean the output
        cleaned = TOONParser._clean_output(raw_output)

        # Try to parse as structured data FIRST (YAML/JSON)
        # This takes priority over direct route detection
        plan_dict = None

        # Try YAML first (most common for structured output)
        try:
            plan_dict = yaml.safe_load(cleaned)
            if isinstance(plan_dict, dict):
                logger.debug("Parsed TOON as YAML")
        except yaml.YAMLError:
            pass

        # Try JSON if YAML fails
        if not plan_dict:
            try:
                plan_dict = json.loads(cleaned)
                if isinstance(plan_dict, dict):
                    logger.debug("Parsed TOON as JSON")
            except json.JSONDecodeError:
                pass

        # If we have a dict, try to create TOONPlan
        if plan_dict and isinstance(plan_dict, dict):
            try:
                # Handle nested 'toon' key if present
                if 'toon' in plan_dict:
                    plan_dict = plan_dict['toon']

                plan = TOONPlan(**plan_dict)
                plan = plan.apply_guardrails()
                logger.info(f"Parsed TOON plan: route={plan.route.value}, entities={len(plan.entities)}")
                return plan
            except Exception as e:
                logger.warning(f"Failed to validate TOON plan: {e}")

        # Only try direct route detection for SHORT outputs (likely just route name)
        # This prevents false positives on full YAML that happens to contain route names
        if len(cleaned) < 100:
            route_direct = TOONParser._try_parse_direct_route(cleaned)
            if route_direct:
                logger.debug(f"Parsed TOON as direct route: {route_direct.value}")
                return TOONPlan(
                    route=route_direct,
                    confidence=0.8,
                    reasoning=f"Direct route detection: {cleaned[:50]}"
                )

        # Fallback: try to extract intent from raw text
        logger.warning(f"Using fallback parsing for TOON output")
        return TOONParser._create_fallback_plan(raw_output, fallback_route)

    @staticmethod
    def _clean_output(raw: str) -> str:
        """Clean SLM output for parsing."""
        # Extract content from code blocks first (handles ```yaml ... ``` format)
        code_block_match = re.search(r'```(?:yaml|json)?\s*([\s\S]*?)```', raw)
        if code_block_match:
            raw = code_block_match.group(1).strip()
        else:
            # Remove any stray code block markers
            raw = re.sub(r'```(?:yaml|json)?\s*', '', raw)
            raw = re.sub(r'```\s*', '', raw)

        # Remove leading/trailing whitespace
        raw = raw.strip()

        # Find the start of YAML/JSON content
        yaml_match = re.search(r'(toon:|version:|route:)', raw, re.IGNORECASE)
        json_match = re.search(r'\{', raw)

        if yaml_match:
            raw = raw[yaml_match.start():]
        elif json_match:
            raw = raw[json_match.start():]

        # Truncate at common end-of-YAML indicators (extra text from model)
        # Look for lines that don't look like YAML/JSON
        lines = raw.split('\n')
        clean_lines = []
        for line in lines:
            # Stop if we hit explanatory text (common model artifact)
            if re.match(r'^(Output|Note|Explanation|The|This|I|Please|Here)', line.strip()):
                break
            clean_lines.append(line)

        return '\n'.join(clean_lines).strip()

    @staticmethod
    def _try_parse_direct_route(cleaned: str) -> Optional[TOONRoute]:
        """
        Try to parse output as a direct route name.

        Small language models often output just the route name instead of
        full YAML structure. This handles that case.
        """
        cleaned_upper = cleaned.strip().upper()

        # Direct exact match
        for route in TOONRoute:
            if cleaned_upper == route.value:
                return route

        # Partial match with common variations
        route_mapping = {
            'GRAPH': TOONRoute.GRAPH_ONLY,
            'GRAPH ONLY': TOONRoute.GRAPH_ONLY,
            'GRAPH_ONLY': TOONRoute.GRAPH_ONLY,
            'GRAPHONLY': TOONRoute.GRAPH_ONLY,
            'VECTOR': TOONRoute.VECTOR_ONLY,
            'VECTOR ONLY': TOONRoute.VECTOR_ONLY,
            'VECTOR_ONLY': TOONRoute.VECTOR_ONLY,
            'VECTORONLY': TOONRoute.VECTOR_ONLY,
            'SEMANTIC': TOONRoute.VECTOR_ONLY,
            'HYBRID': TOONRoute.HYBRID,
            'BOTH': TOONRoute.HYBRID,
            'ASK': TOONRoute.ASK_CLARIFY,
            'CLARIFY': TOONRoute.ASK_CLARIFY,
            'ASK_CLARIFY': TOONRoute.ASK_CLARIFY,
            'ASKCLARIFY': TOONRoute.ASK_CLARIFY,
        }

        # Remove special characters and check
        cleaned_normalized = re.sub(r'[^A-Z_]', '', cleaned_upper)
        if cleaned_normalized in route_mapping:
            return route_mapping[cleaned_normalized]

        # Check if any route name is contained in the output (for short responses)
        for key, route in route_mapping.items():
            if key in cleaned_upper:
                return route

        return None

    @staticmethod
    def _create_fallback_plan(raw: str, fallback_route: TOONRoute) -> TOONPlan:
        """Create a fallback plan when parsing fails."""
        raw_lower = raw.lower()

        # Try to detect route from keywords
        route = fallback_route
        if any(word in raw_lower for word in ['count', 'cuántos', 'cuantos', 'how many', 'list']):
            route = TOONRoute.GRAPH_ONLY
        elif any(word in raw_lower for word in ['clarify', 'unclear', 'ambiguous']):
            route = TOONRoute.ASK_CLARIFY
        elif any(word in raw_lower for word in ['search', 'find', 'buscar', 'meaning', 'content']):
            route = TOONRoute.VECTOR_ONLY

        return TOONPlan(
            route=route,
            confidence=0.5,  # Low confidence for fallback
            reasoning="Fallback plan due to parsing failure",
        )


# =============================================================================
# TOON PLAN BUILDER (Fluent API)
# =============================================================================

class TOONPlanBuilder:
    """
    Builder pattern for creating TOON plans programmatically.

    Useful for testing and for creating plans from deterministic rules.
    """

    def __init__(self):
        self._route: TOONRoute = TOONRoute.VECTOR_ONLY
        self._confidence: float = 0.8
        self._entities: List[ExtractedEntity] = []
        self._graph = GraphQueryConfig()
        self._vector = VectorQueryConfig()
        self._clarify = ClarificationConfig()
        self._reasoning: str = ""
        self._original_query: str = ""
        self._tenant_id: str = ""
        self._session_id: str = ""

    def with_route(self, route: TOONRoute, confidence: float = 0.8) -> 'TOONPlanBuilder':
        """Set the routing decision."""
        self._route = route
        self._confidence = confidence
        return self

    def with_entity(
        self,
        name: str,
        entity_type: str,
        graph_label: Optional[str] = None,
        source: EntitySource = EntitySource.QUERY
    ) -> 'TOONPlanBuilder':
        """Add an extracted entity."""
        self._entities.append(ExtractedEntity(
            name=name,
            type=entity_type,
            graph_label=graph_label,
            source=source
        ))
        return self

    def with_graph_query(
        self,
        operation: GraphOperation,
        cypher_template: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        hops: int = 2
    ) -> 'TOONPlanBuilder':
        """Configure graph query."""
        self._graph = GraphQueryConfig(
            enabled=True,
            operation=operation,
            cypher_template=cypher_template,
            params=params or {},
            limit=limit,
            hops=hops
        )
        return self

    def with_vector_query(
        self,
        operation: VectorOperation = VectorOperation.SEMANTIC_SEARCH,
        top_k: int = 5,
        tenant_scope: bool = True,
        document_types: Optional[List[str]] = None,
        rerank: bool = False
    ) -> 'TOONPlanBuilder':
        """Configure vector query."""
        self._vector = VectorQueryConfig(
            enabled=True,
            operation=operation,
            top_k=top_k,
            filters=VectorFilters(
                tenant_scope=tenant_scope,
                document_types=document_types or []
            ),
            rerank=rerank
        )
        return self

    def with_clarification(
        self,
        question: str,
        options: Optional[List[str]] = None,
        missing_info: str = ""
    ) -> 'TOONPlanBuilder':
        """Configure clarification request."""
        self._clarify = ClarificationConfig(
            question=question,
            options=options or [],
            missing_info=missing_info
        )
        return self

    def with_context(
        self,
        original_query: str = "",
        tenant_id: str = "",
        session_id: str = "",
        reasoning: str = ""
    ) -> 'TOONPlanBuilder':
        """Add context metadata."""
        self._original_query = original_query
        self._tenant_id = tenant_id
        self._session_id = session_id
        self._reasoning = reasoning
        return self

    def build(self) -> TOONPlan:
        """Build and validate the TOON plan."""
        plan = TOONPlan(
            route=self._route,
            confidence=self._confidence,
            entities=self._entities,
            graph=self._graph,
            vector=self._vector,
            clarify=self._clarify,
            reasoning=self._reasoning,
            original_query=self._original_query,
            tenant_id=self._tenant_id,
            session_id=self._session_id
        )
        return plan.apply_guardrails()


# =============================================================================
# EXECUTION RESULT MODELS
# =============================================================================

class TOONExecutionResult(BaseModel):
    """
    Result of executing a TOON plan.

    Contains the results from graph and/or vector queries,
    ready to be passed to the main LLM for response generation.
    """
    plan: TOONPlan
    success: bool = True
    error: Optional[str] = None

    # Graph results
    graph_result: Optional[Dict[str, Any]] = None
    graph_row_count: int = 0
    graph_execution_time_ms: float = 0.0

    # Vector results
    vector_results: List[Dict[str, Any]] = Field(default_factory=list)
    vector_result_count: int = 0
    vector_execution_time_ms: float = 0.0

    # Clarification (if ASK_CLARIFY)
    clarification_question: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list)

    # Total execution time
    total_execution_time_ms: float = 0.0

    # Context for LLM
    context_for_llm: str = Field(
        default="",
        description="Formatted context string for the main LLM"
    )

    def format_context(self) -> str:
        """
        Format execution results as context for the LLM.

        Optimized for GRPO-trained models (horelvis/qwen-dw-grpo-rag) that
        understand graph structures and entity relationships better.

        Key improvements for GRPO:
        1. Entity section with types and graph labels (GRPO understands typed entities)
        2. Relationship context from graph queries (GRPO excels at multi-hop reasoning)
        3. Structured format that maps to knowledge graph patterns
        """
        parts = []

        if self.plan.route == TOONRoute.ASK_CLARIFY:
            return ""  # No context for clarification

        # === SECTION 1: Extracted Entities (GRPO-optimized) ===
        # GRPO models understand entity types and their graph labels
        if self.plan.entities:
            parts.append("## Entities Identified\n")
            entity_lines = []
            for entity in self.plan.entities:
                label_info = f" [{entity.graph_label}]" if entity.graph_label else ""
                confidence_info = f" ({entity.confidence:.0%})" if entity.confidence < 1.0 else ""
                entity_lines.append(f"- **{entity.name}** (type: {entity.type}){label_info}{confidence_info}")
            parts.append("\n".join(entity_lines))
            parts.append("")

        # === SECTION 2: Graph Structure Results (GRPO-optimized) ===
        # GRPO models excel at understanding hierarchical and relational data
        if self.graph_result:
            parts.append("## Knowledge Graph Results\n")

            # Add traversal depth info for multi-hop reasoning context
            if self.plan.graph.hops > 1:
                parts.append(f"*Traversal depth: {self.plan.graph.hops} hops*\n")

            if self.plan.graph.operation == GraphOperation.COUNT:
                count = self.graph_result.get('count', self.graph_row_count)
                # Include entity context for GRPO to understand what was counted
                if self.plan.entities:
                    primary_entity = self.plan.entities[0]
                    parts.append(f"**Count of {primary_entity.type}:** {count}")
                else:
                    parts.append(f"**Count:** {count}")

            elif self.plan.graph.operation == GraphOperation.EXISTS:
                exists = self.graph_result.get('exists', self.graph_row_count > 0)
                parts.append(f"**Exists:** {'Yes' if exists else 'No'}")

            elif self.plan.graph.operation == GraphOperation.LIST:
                parts.append(f"**Found:** {self.graph_row_count} items\n")
                if 'items' in self.graph_result:
                    # Format with relationship context for GRPO
                    for i, item in enumerate(self.graph_result['items'][:10], 1):
                        title = item.get('title', item.get('name', str(item)))
                        # Include relationship info if available (GRPO-optimized)
                        if 'relationship' in item:
                            parts.append(f"  {i}. {title} —[{item['relationship']}]→")
                        elif 'connected_to' in item:
                            parts.append(f"  {i}. {title} → {item['connected_to']}")
                        else:
                            parts.append(f"  {i}. {title}")
                        # Add properties if present (metadata helps GRPO reasoning)
                        if 'properties' in item and item['properties']:
                            props = ", ".join(f"{k}: {v}" for k, v in list(item['properties'].items())[:3])
                            parts.append(f"      Properties: {props}")

            elif self.plan.graph.operation == GraphOperation.AGGREGATE:
                parts.append("**Aggregation Results:**")
                parts.append(f"```json\n{json.dumps(self.graph_result, indent=2, default=str)}\n```")

            elif self.plan.graph.operation == GraphOperation.PATH:
                # Path queries are where GRPO really shines (multi-hop reasoning)
                parts.append("**Relationship Path:**")
                if 'path' in self.graph_result:
                    path = self.graph_result['path']
                    parts.append(f"  {' → '.join(str(node) for node in path)}")
                else:
                    parts.append(f"```json\n{json.dumps(self.graph_result, indent=2, default=str)}\n```")
            else:
                # Generic formatting with structure preserved
                parts.append(f"```json\n{json.dumps(self.graph_result, indent=2, default=str)}\n```")

        # === SECTION 3: Vector Search Results (Semantic content) ===
        if self.vector_results:
            parts.append("\n## Retrieved Documents\n")
            for i, doc in enumerate(self.vector_results[:5], 1):
                title = doc.get('title', doc.get('filename', 'Untitled'))
                score = doc.get('score', doc.get('distance', 'N/A'))
                doc_type = doc.get('document_type', doc.get('type', ''))

                # Include document type for GRPO entity understanding
                type_info = f" [{doc_type}]" if doc_type else ""
                parts.append(f"**{i}. {title}**{type_info} (relevance: {score})")

                if 'content' in doc:
                    content = doc['content'][:500] + "..." if len(doc.get('content', '')) > 500 else doc.get('content', '')
                    parts.append(f"   {content}")
                parts.append("")

        # === SECTION 4: Query Context (helps GRPO understand intent) ===
        if self.plan.route == TOONRoute.HYBRID and self.graph_result and self.vector_results:
            parts.append("\n## Combined Context")
            parts.append(f"Graph provided {self.graph_row_count} structural relationships.")
            parts.append(f"Vector search found {self.vector_result_count} relevant documents.")
            parts.append("Use both sources to form a complete answer.")

        self.context_for_llm = "\n".join(parts)
        return self.context_for_llm

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary for logging."""
        return {
            "route": self.plan.route.value,
            "success": self.success,
            "graph_rows": self.graph_row_count,
            "vector_results": self.vector_result_count,
            "total_time_ms": self.total_execution_time_ms,
        }
