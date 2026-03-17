"""
VerifiedGenState — Dedicated state for the verified generation sub-graph.

Mirrors the fields from StopAndGoState that verified generation actually uses,
without the generic "mode" indirection. Compiled with checkpointer=False
(no multi-turn memory — runs as a single tool invocation).

Key reducers:
- pending_events: merge_lists — each node appends SSE events
- metadata: merge_dicts — observability data accumulated across nodes
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.agents.langgraph.state import merge_dicts, merge_lists


class VerifiedGenState(TypedDict, total=False):
    # === Session ===
    session_id: str
    tenant_id: str
    user_id: Optional[str]

    # === Input ===
    query: str                          # User query / document topic
    source_context: str                 # Hydrated source text (from uploads)
    uploaded_texts: List[Dict]          # Raw uploaded documents [{filename, text, id}]
    collections: List[str]              # Weaviate collections to search
    context_document_ids: List[str]     # Specific doc IDs for context
    source_document_ids: List[str]      # Doc IDs used to build source_context
    source_filenames: List[str]         # Original filenames for report header

    # === Configuration ===
    max_claims: int                     # Maximum claims to generate
    confidence_threshold: float         # Min confidence to accept a claim
    auto_correct: bool                  # Auto-correct low-confidence claims
    mode_config: Dict[str, Any]         # fidelity_cap, max_evidence, document_type, sector

    # === Loop State ===
    current_step: int                   # Current iteration
    items_extracted: int                # Total claims attempted
    items_accepted: int                 # Claims that passed verification
    items_rejected: int                 # Claims that failed verification
    items_corrected: int                # Claims auto-corrected
    duplicate_streak: int               # Consecutive duplicates (triggers section advance)
    is_complete: bool                   # Should we stop?

    # === Section-Windowed Generation ===
    source_sections: List[str]          # Source document split into sections
    current_section_index: int          # Index of current section being processed
    section_claims_count: List[int]     # Claims generated per section

    # === Evidence (cached per session) ===
    jurisprudence_evidence: List[Dict]  # CENDOJ results (legal sector only)
    source_doi_validations: List[Dict]  # DOIs extracted from uploads + validation

    # === Items ===
    all_extracted_items: List[Dict]     # ALL claims for dedup context
    current_item: Optional[Dict]        # Claim being verified

    # === SSE Events Queue (reducer: append) ===
    pending_events: Annotated[List[Dict[str, Any]], merge_lists]

    # === Output ===
    result: Optional[Dict[str, Any]]    # Final synthesized document
    execution_time_ms: int
    sources_map: Dict[str, Dict]        # Collected evidence references

    # === Observability ===
    metadata: Annotated[Dict[str, Any], merge_dicts]


def create_verified_gen_state(
    *,
    session_id: Optional[str] = None,
    tenant_id: str,
    user_id: Optional[str] = None,
    query: str,
    max_claims: int = 20,
    confidence_threshold: float = 0.7,
    auto_correct: bool = True,
    uploaded_texts: Optional[List[Dict]] = None,
    collections: Optional[List[str]] = None,
    context_document_ids: Optional[List[str]] = None,
    mode_config: Optional[Dict[str, Any]] = None,
) -> VerifiedGenState:
    """Create initial state for a verified generation sub-graph execution."""
    return VerifiedGenState(
        session_id=session_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        query=query,
        source_context="",
        uploaded_texts=uploaded_texts or [],
        collections=collections or [],
        context_document_ids=context_document_ids or [],
        source_document_ids=[],
        source_filenames=[],
        max_claims=max_claims,
        confidence_threshold=confidence_threshold,
        auto_correct=auto_correct,
        mode_config=mode_config or {},
        current_step=0,
        items_extracted=0,
        items_accepted=0,
        items_rejected=0,
        items_corrected=0,
        duplicate_streak=0,
        is_complete=False,
        source_sections=[],
        current_section_index=0,
        section_claims_count=[],
        jurisprudence_evidence=[],
        source_doi_validations=[],
        all_extracted_items=[],
        current_item=None,
        pending_events=[],
        result=None,
        execution_time_ms=0,
        sources_map={},
        metadata={},
    )
