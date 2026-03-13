"""
StopAndGoState — Shared state for the stop-and-go LangGraph.

Both predictive analysis and verified generation share this state.
Mode-specific data is stored in `mode_config` (opaque to graph nodes)
and handled by the strategy implementation.

Key design: `pending_events` uses the `merge_lists` reducer so each
node can append SSE events without overwriting previous ones. The
runner drains new events from state snapshots.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.agents.langgraph.state import merge_dicts, merge_lists


class StopAndGoState(TypedDict, total=False):
    # === Session ===
    session_id: str
    tenant_id: str
    user_id: Optional[str]

    # === Input ===
    query: str                          # case_description (predictive) or query (verified)
    source_context: str                 # Hydrated source text
    uploaded_texts: List[Dict]          # Raw uploaded documents
    collections: List[str]              # Weaviate collections
    context_document_ids: List[str]     # Specific doc IDs for context
    source_document_ids: List[str]      # Doc IDs used to build source_context (for exclusion in verification)
    source_filenames: List[str]          # Original filenames of uploaded documents

    # === Configuration ===
    max_items: int                      # max_factors or max_claims
    confidence_threshold: float         # Min confidence to accept
    mode: str                           # "predictive" or "verified"

    # === Mode-specific config (opaque to graph) ===
    mode_config: Dict[str, Any]

    # === Loop State ===
    current_step: int                   # Current iteration
    items_extracted: int                # Total items attempted
    items_accepted: int                 # Items that passed evaluation
    items_rejected: int                 # Items that failed evaluation
    items_corrected: int                # Items corrected (verified mode)
    duplicate_streak: int               # Consecutive duplicates
    is_complete: bool                   # Should we stop?

    # === Section-Windowed Generation ===
    source_sections: List[str]          # Source document split into sections
    current_section_index: int          # Index of current section being processed
    section_claims_count: List[int]     # Claims generated per section

    # === Jurisprudence (legal sector, ephemeral) ===
    jurisprudence_evidence: List[Dict]  # CENDOJ results cached for session

    # === DOI validation (from source document, cached for session) ===
    source_doi_validations: List[Dict]  # DOIs extracted from uploaded docs + validation results

    # === Items ===
    all_extracted_items: List[Dict]     # ALL items for dedup context
    current_item: Optional[Dict]        # Item being processed

    # === SSE Events Queue (reducer: append) ===
    pending_events: Annotated[List[Dict[str, Any]], merge_lists]

    # === HITL (Human-in-the-Loop) ===
    hitl_enabled: bool                        # Whether HITL review is active for this session
    review_payload: Optional[Dict[str, Any]]  # Claims sent for human review (set by review node)
    review_response: Optional[Dict[str, Any]] # Human decisions (set by Command(resume=...))

    # === Output ===
    result: Optional[Dict[str, Any]]    # Final synthesis result
    execution_time_ms: int
    sources_map: Dict[str, Dict]        # Collected source references

    # === Observability ===
    metadata: Annotated[Dict[str, Any], merge_dicts]


def create_initial_state(
    *,
    session_id: Optional[str] = None,
    tenant_id: str,
    user_id: Optional[str] = None,
    query: str,
    mode: str,
    max_items: int,
    confidence_threshold: float = 0.7,
    uploaded_texts: Optional[List[Dict]] = None,
    collections: Optional[List[str]] = None,
    context_document_ids: Optional[List[str]] = None,
    mode_config: Optional[Dict[str, Any]] = None,
    hitl_enabled: bool = False,
) -> StopAndGoState:
    """Create initial state for a stop-and-go graph execution."""
    return StopAndGoState(
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
        max_items=max_items,
        confidence_threshold=confidence_threshold,
        mode=mode,
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
        hitl_enabled=hitl_enabled,
        review_payload=None,
        review_response=None,
        pending_events=[],
        result=None,
        execution_time_ms=0,
        sources_map={},
        metadata={},
    )
