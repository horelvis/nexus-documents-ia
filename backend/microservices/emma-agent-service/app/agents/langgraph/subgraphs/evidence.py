"""
Shared evidence search and DOI validation — used by both verified_gen and predictive sub-graphs.

Extracted from stop_and_go/nodes/search_and_evaluate.py (733 lines) and
stop_and_go/nodes/initialize.py (DOI pre-validation, CENDOJ search).

This module contains NO state management or strategy dispatch — only
pure evidence retrieval functions that both sub-graphs call.
"""

# Re-export everything from the current stop_and_go modules.
# When stop_and_go is deleted (Task 12), these functions will be
# moved here inline. For now, this avoids duplicating 700+ lines
# while keeping the sub-graphs functional.

from app.agents.langgraph.stop_and_go.nodes.search_and_evaluate import (
    DOI_PATTERN,
    _search_evidence as search_evidence,
    _validate_single_doi as validate_single_doi,
    _extract_and_validate_dois as extract_and_validate_dois,
    _cross_reference_source_dois as cross_reference_source_dois,
    _search_crossref_citation as search_crossref_citation,
)

from app.agents.langgraph.stop_and_go.nodes.initialize import (
    _get_source_context as get_source_context,
    _chunk_source_into_sections as chunk_source_into_sections,
    _validate_source_dois as validate_source_dois,
    _search_cendoj_jurisprudence as search_cendoj_jurisprudence,
    _is_cendoj_enabled as is_cendoj_enabled,
    NO_CHUNK_THRESHOLD,
)

__all__ = [
    "DOI_PATTERN",
    "search_evidence",
    "validate_single_doi",
    "extract_and_validate_dois",
    "cross_reference_source_dois",
    "search_crossref_citation",
    "get_source_context",
    "chunk_source_into_sections",
    "validate_source_dois",
    "search_cendoj_jurisprudence",
    "is_cendoj_enabled",
    "NO_CHUNK_THRESHOLD",
]
