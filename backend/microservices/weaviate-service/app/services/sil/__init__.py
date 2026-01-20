"""
Structural Intelligence Layer (SIL)

A paradigm shift in RAG architecture:
- BEFORE: Learn CONTENT of documents → embed text → search → send to LLM
- AFTER: Learn STRUCTURE of documents → reason structurally → invoke RAG only when needed

The SIL enables:
1. Structural Metadata Extraction - Extract WHERE, HOW, WHAT TYPE (not content)
2. Structural Graph (Apache AGE) - Graph of STRUCTURE, not content
3. Structural Embeddings - Embeddings of structural DESCRIPTIONS
4. Pre-LLM Reasoning Engine - Answer structural questions WITHOUT LLM
5. Focused RAG - When content IS needed, narrow the search scope

Key Benefits:
- 70-90% reduction in tokens sent to LLM
- Sub-500ms response for structural queries
- Higher precision through structural context
- Temporal awareness (what changed, when, how evolved)
- Multi-hop reasoning (traverse relationships)

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STRUCTURAL INTELLIGENCE LAYER (SIL)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 1: Structural Metadata Extraction                                    │
│           → Extracts location, type, relationships (NOT content)            │
│                                                                              │
│  Layer 2: Structural Graph (Apache AGE)                                     │
│           → Folders, Sites, Documents as structural nodes                   │
│           → contains, version_of, relates_to edges                          │
│                                                                              │
│  Layer 3: Structural Embeddings (Weaviate)                                  │
│           → Embed structural descriptions for semantic search               │
│                                                                              │
│  Layer 4: Pre-LLM Reasoning Engine                                          │
│           → Cypher queries for structural questions                         │
│           → Temporal reasoning, multi-hop traversal                         │
│                                                                              │
│  Layer 5: LLM as Interpreter                                                │
│           → LLM receives structural_context, NOT full documents             │
│           → Invokes focused RAG only when content IS needed                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Usage:
    from app.services.sil import (
        sil_engine,  # Main entry point
        StructuralExtractor,
        PreLLMReasoningEngine,
        IntentType,
        ReasoningType,
    )

    # Process a query with structural intelligence
    result = await sil_engine.process_query(
        query="How many contracts does ACME have?",
        tenant_id="tenant-123",
    )

    if result.reasoning_type == ReasoningType.STRUCTURAL:
        # Answered purely from graph - no RAG needed
        print(f"Answer: {result.structural_context}")
    elif result.reasoning_type == ReasoningType.FOCUSED_RAG:
        # Need content, but from specific documents only
        print(f"Target documents: {result.target_document_ids}")
"""

from .schemas import (
    # Core data models
    StructuralMetadata,
    StructuralContext,
    StructuralEntities,
    FolderSemantics,
    DocumentRelationship,
    # Intent and reasoning types
    IntentType,
    ReasoningType,
    Intent,
    ReasoningResult,
    # Query types
    TemporalMarkers,
    MultiHopQuery,
    QueryPlan,
    # Results
    StructuralQueryResult,
    CypherQueryResult,
    TemporalResult,
    MultiHopResult,
)

from .structural_extractor import StructuralExtractor, structural_extractor
from .structural_embedder import StructuralEmbedder, structural_embedder
from .intent_detector import IntentDetector, intent_detector
from .cypher_builder import CypherBuilder, cypher_builder
from .pre_llm_reasoning import PreLLMReasoningEngine, pre_llm_engine
from .temporal_reasoning import TemporalReasoningEngine, temporal_engine
from .multihop_planner import MultiHopQueryPlanner, multihop_planner
from .multihop_executor import MultiHopExecutor, multihop_executor
from .sil_engine import SILEngine, sil_engine
from .structural_collection import (
    StructuralCollectionService,
    structural_collection,
    STRUCTURAL_DOCUMENTS_COLLECTION,
)
from .structural_graph import (
    StructuralGraphService,
    structural_graph,
    StructuralNode,
    StructuralEdge,
)
from .rag_integration import (
    SILRAGIntegration,
    sil_rag_integration,
    SILResult,
    RAGMode,
)

__all__ = [
    # Main engine
    "SILEngine",
    "sil_engine",
    # Core services
    "StructuralExtractor",
    "structural_extractor",
    "StructuralEmbedder",
    "structural_embedder",
    "IntentDetector",
    "intent_detector",
    "CypherBuilder",
    "cypher_builder",
    "PreLLMReasoningEngine",
    "pre_llm_engine",
    "TemporalReasoningEngine",
    "temporal_engine",
    "MultiHopQueryPlanner",
    "multihop_planner",
    "MultiHopExecutor",
    "multihop_executor",
    # Data models
    "StructuralMetadata",
    "StructuralContext",
    "StructuralEntities",
    "FolderSemantics",
    "DocumentRelationship",
    "IntentType",
    "ReasoningType",
    "Intent",
    "ReasoningResult",
    "TemporalMarkers",
    "MultiHopQuery",
    "QueryPlan",
    "StructuralQueryResult",
    "CypherQueryResult",
    "TemporalResult",
    "MultiHopResult",
    # Weaviate collection
    "StructuralCollectionService",
    "structural_collection",
    "STRUCTURAL_DOCUMENTS_COLLECTION",
    # Apache AGE graph
    "StructuralGraphService",
    "structural_graph",
    "StructuralNode",
    "StructuralEdge",
    # RAG integration
    "SILRAGIntegration",
    "sil_rag_integration",
    "SILResult",
    "RAGMode",
]
