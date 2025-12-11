"""
Reciprocal Rank Fusion (RRF) Algorithm

Combines results from multiple retrieval methods (dense vector, sparse BM25)
into a single ranked list using the RRF formula:

    RRF_score(d) = Σ 1/(k + rank_i(d))

Where:
- k is a constant (typically 60) that prevents high-ranked items from dominating
- rank_i(d) is the rank of document d in ranking list i

Reference: "Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods"
by Cormack, Clarke, and Buettcher (2009)
"""

import logging
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass

from .models import RetrievedDocument

logger = logging.getLogger(__name__)


@dataclass
class RRFResult:
    """Result of RRF fusion with metadata"""
    documents: List[RetrievedDocument]
    fusion_scores: Dict[str, float]
    dense_contribution: Dict[str, float]
    sparse_contribution: Dict[str, float]


def reciprocal_rank_fusion(
    dense_results: List[RetrievedDocument],
    sparse_results: List[RetrievedDocument],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> List[RetrievedDocument]:
    """
    Combine dense (vector) and sparse (BM25) results using Reciprocal Rank Fusion.

    Args:
        dense_results: Results from vector/embedding search, ordered by relevance
        sparse_results: Results from BM25/keyword search, ordered by relevance
        k: RRF constant (default 60). Higher values give more weight to lower ranks.
        dense_weight: Weight multiplier for dense search scores (default 1.0)
        sparse_weight: Weight multiplier for sparse search scores (default 1.0)

    Returns:
        List of RetrievedDocument sorted by combined RRF score

    Example:
        If a document is rank 1 in dense and rank 3 in sparse:
        RRF_score = 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
    """
    if not dense_results and not sparse_results:
        return []

    rrf_scores: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, RetrievedDocument] = {}

    # Score from dense (vector) results
    for rank, doc in enumerate(dense_results, start=1):
        score = dense_weight * (1.0 / (k + rank))
        rrf_scores[doc.id] += score
        doc_map[doc.id] = doc

    # Score from sparse (BM25) results
    for rank, doc in enumerate(sparse_results, start=1):
        score = sparse_weight * (1.0 / (k + rank))
        rrf_scores[doc.id] += score
        if doc.id not in doc_map:
            doc_map[doc.id] = doc

    # Sort by combined RRF score (descending)
    sorted_ids = sorted(
        rrf_scores.keys(),
        key=lambda doc_id: rrf_scores[doc_id],
        reverse=True
    )

    # Build result list with updated scores
    results = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id]
        # Store RRF score in the document
        doc.rrf_score = rrf_scores[doc_id]
        # Update the main score to be the RRF score for downstream processing
        doc.score = rrf_scores[doc_id]
        results.append(doc)

    logger.debug(
        f"RRF fusion: {len(dense_results)} dense + {len(sparse_results)} sparse "
        f"→ {len(results)} unique documents"
    )

    return results


def reciprocal_rank_fusion_detailed(
    dense_results: List[RetrievedDocument],
    sparse_results: List[RetrievedDocument],
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> RRFResult:
    """
    RRF fusion with detailed contribution tracking.

    Same as reciprocal_rank_fusion but returns additional metadata about
    how each source contributed to the final scores.

    Useful for debugging and understanding retrieval behavior.
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    dense_contribution: Dict[str, float] = defaultdict(float)
    sparse_contribution: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, RetrievedDocument] = {}

    # Score from dense results
    for rank, doc in enumerate(dense_results, start=1):
        score = dense_weight * (1.0 / (k + rank))
        rrf_scores[doc.id] += score
        dense_contribution[doc.id] = score
        doc_map[doc.id] = doc

    # Score from sparse results
    for rank, doc in enumerate(sparse_results, start=1):
        score = sparse_weight * (1.0 / (k + rank))
        rrf_scores[doc.id] += score
        sparse_contribution[doc.id] = score
        if doc.id not in doc_map:
            doc_map[doc.id] = doc

    # Sort by combined score
    sorted_ids = sorted(
        rrf_scores.keys(),
        key=lambda doc_id: rrf_scores[doc_id],
        reverse=True
    )

    # Build results
    results = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id]
        doc.rrf_score = rrf_scores[doc_id]
        doc.score = rrf_scores[doc_id]
        results.append(doc)

    return RRFResult(
        documents=results,
        fusion_scores=dict(rrf_scores),
        dense_contribution=dict(dense_contribution),
        sparse_contribution=dict(sparse_contribution),
    )


def multi_list_rrf(
    result_lists: List[List[RetrievedDocument]],
    weights: Optional[List[float]] = None,
    k: int = 60,
) -> List[RetrievedDocument]:
    """
    Generalized RRF for multiple ranking lists.

    Args:
        result_lists: List of result lists, each ordered by relevance
        weights: Optional weights for each list (default: equal weights)
        k: RRF constant

    Returns:
        Fused results sorted by combined RRF score

    Example use case: Combining results from multiple query variations
    """
    if not result_lists:
        return []

    # Default to equal weights
    if weights is None:
        weights = [1.0] * len(result_lists)

    if len(weights) != len(result_lists):
        raise ValueError("Number of weights must match number of result lists")

    rrf_scores: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, RetrievedDocument] = {}

    # Process each result list
    for list_idx, results in enumerate(result_lists):
        weight = weights[list_idx]
        for rank, doc in enumerate(results, start=1):
            score = weight * (1.0 / (k + rank))
            rrf_scores[doc.id] += score
            if doc.id not in doc_map:
                doc_map[doc.id] = doc

    # Sort by combined score
    sorted_ids = sorted(
        rrf_scores.keys(),
        key=lambda doc_id: rrf_scores[doc_id],
        reverse=True
    )

    # Build results
    results = []
    for doc_id in sorted_ids:
        doc = doc_map[doc_id]
        doc.rrf_score = rrf_scores[doc_id]
        doc.score = rrf_scores[doc_id]
        results.append(doc)

    return results
