"""
PredictiveState — Dedicated state for the predictive analysis sub-graph.

Mirrors StopAndGoState fields used by predictive analysis.
Compiled with checkpointer=False.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.agents.langgraph.state import merge_dicts, merge_lists


class PredictiveState(TypedDict, total=False):
    # === Session ===
    session_id: str
    tenant_id: str
    user_id: Optional[str]

    # === Input ===
    query: str                          # Case description
    source_context: str                 # Hydrated source text
    uploaded_texts: List[Dict]          # Raw uploaded documents
    collections: List[str]              # Weaviate collections
    context_document_ids: List[str]     # Specific doc IDs
    source_document_ids: List[str]      # Source doc IDs
    source_filenames: List[str]         # Original filenames

    # === Configuration ===
    max_factors: int                    # Maximum factors to extract
    confidence_threshold: float         # Min confidence to accept
    mode_config: Dict[str, Any]         # sector_override, outcome_labels, weights

    # === Loop State ===
    current_step: int
    items_extracted: int
    items_accepted: int
    items_rejected: int
    duplicate_streak: int
    is_complete: bool

    # === Evidence (cached per session) ===
    jurisprudence_evidence: List[Dict]  # CENDOJ (legal sector)

    # === Items ===
    all_extracted_items: List[Dict]     # ALL factors for dedup context
    current_item: Optional[Dict]        # Factor being evaluated

    # === SSE Events Queue ===
    pending_events: Annotated[List[Dict[str, Any]], merge_lists]

    # === Output ===
    result: Optional[Dict[str, Any]]
    execution_time_ms: int
    sources_map: Dict[str, Dict]

    # === Observability ===
    metadata: Annotated[Dict[str, Any], merge_dicts]


def create_predictive_state(
    *,
    session_id: Optional[str] = None,
    tenant_id: str,
    user_id: Optional[str] = None,
    query: str,
    max_factors: int = 10,
    confidence_threshold: float = 0.7,
    uploaded_texts: Optional[List[Dict]] = None,
    collections: Optional[List[str]] = None,
    context_document_ids: Optional[List[str]] = None,
    mode_config: Optional[Dict[str, Any]] = None,
) -> PredictiveState:
    """Create initial state for a predictive analysis sub-graph execution."""
    return PredictiveState(
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
        max_factors=max_factors,
        confidence_threshold=confidence_threshold,
        mode_config=mode_config or {},
        current_step=0,
        items_extracted=0,
        items_accepted=0,
        items_rejected=0,
        duplicate_streak=0,
        is_complete=False,
        jurisprudence_evidence=[],
        all_extracted_items=[],
        current_item=None,
        pending_events=[],
        result=None,
        execution_time_ms=0,
        sources_map={},
        metadata={},
    )
