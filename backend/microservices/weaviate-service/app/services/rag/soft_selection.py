"""
Soft Selection Module for RAG Pipeline

Implements heuristic-based document selection with diversity:
1. Softmax re-weighting (NOT differentiable top-k)
2. MMR (Maximal Marginal Relevance) for redundancy penalization
3. K-means clustering with stratified quota for guaranteed diversity
4. Proportional token budget allocation

Formula definitions:
- Softmax: w_i = exp(score_i / T) / Σ exp(score_j / T)
- MMR: score = λ * relevance - (1-λ) * max_redundancy
  (NOT: score = rel - λ*redundancy which kills recall at high λ)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
import numpy as np
import logging

from .models import RetrievedDocument

logger = logging.getLogger(__name__)


@dataclass
class SoftSelectionConfig:
    """Configuration for soft selection algorithms"""

    # Re-weighting (softmax temperature)
    # Lower = sharper (more selective), Higher = more uniform
    temperature: float = 0.5

    # MMR parameters
    # Formula: λ * relevance - (1-λ) * redundancy
    # λ = 1.0 → pure relevance, λ = 0.0 → pure diversity
    mmr_lambda: float = 0.7

    # Clustering with stratified quota
    num_clusters: int = 5
    min_docs_per_cluster: int = 1  # Guaranteed minimum per cluster

    # Safety caps to avoid noise
    max_docs: int = 12  # Hard cap on documents
    min_weight: float = 0.02  # Drop docs with weight < 2%

    # Token allocation
    min_tokens_per_doc: int = 200  # If can't fit minimum, drop doc


@dataclass
class SoftSelectionResult:
    """Result of soft selection with metadata for debugging/metrics"""
    documents: List[RetrievedDocument]
    soft_weights: Dict[str, float]  # doc_id -> normalized weight
    cluster_assignments: Dict[str, int]  # doc_id -> cluster_id
    diversity_score: float  # 1 - avg_similarity (higher = more diverse)
    coverage_score: float  # % of clusters with ≥1 doc selected
    dropped_by_weight: int  # Count of docs dropped due to min_weight
    dropped_by_cap: int  # Count of docs dropped due to max_docs


class SoftSelector:
    """
    Heuristic-based document selection with diversity guarantees.

    Replaces hard top-k cutoff with:
    - Softmax weights based on relevance scores
    - MMR for redundancy penalization in embedding space
    - Stratified selection ensuring cluster coverage
    - Safety caps to prevent noise
    """

    def __init__(self, config: Optional[SoftSelectionConfig] = None):
        self.config = config or SoftSelectionConfig()

    def select(
        self,
        documents: List[RetrievedDocument],
        embeddings: Optional[Dict[str, List[float]]] = None,
        top_k: int = 10,
        query_embedding: Optional[List[float]] = None,
    ) -> SoftSelectionResult:
        """
        Select documents using soft selection with diversity.

        Args:
            documents: Candidate documents (already reranked by cross-encoder)
            embeddings: Document embeddings keyed by doc_id (for MMR/clustering)
            top_k: Target number of documents (subject to max_docs cap)
            query_embedding: Query embedding for relevance calculation in MMR

        Returns:
            SoftSelectionResult with selected documents and metrics
        """
        if not documents:
            return SoftSelectionResult(
                documents=[],
                soft_weights={},
                cluster_assignments={},
                diversity_score=0.0,
                coverage_score=0.0,
                dropped_by_weight=0,
                dropped_by_cap=0,
            )

        # Apply max_docs cap
        effective_top_k = min(top_k, self.config.max_docs)

        # Step 1: Compute soft weights via temperature-scaled softmax
        soft_weights = self._compute_soft_weights(documents)

        # Step 2: Filter by min_weight threshold
        filtered_docs, dropped_by_weight = self._filter_by_min_weight(
            documents, soft_weights
        )

        if not filtered_docs:
            logger.warning("All documents dropped by min_weight filter")
            return SoftSelectionResult(
                documents=[],
                soft_weights=soft_weights,
                cluster_assignments={},
                diversity_score=0.0,
                coverage_score=0.0,
                dropped_by_weight=dropped_by_weight,
                dropped_by_cap=0,
            )

        # Step 3: Cluster documents if embeddings available
        cluster_assignments = {}
        if embeddings and len(filtered_docs) >= self.config.num_clusters:
            cluster_assignments = self._cluster_documents(filtered_docs, embeddings)

        # Step 4: Select using MMR with stratified cluster quota
        if embeddings and query_embedding:
            selected = self._mmr_select_with_quota(
                documents=filtered_docs,
                embeddings=embeddings,
                query_embedding=query_embedding,
                soft_weights=soft_weights,
                cluster_assignments=cluster_assignments,
                top_k=effective_top_k,
            )
        else:
            # Fallback: weighted selection without embeddings
            selected = self._weighted_select(filtered_docs, soft_weights, effective_top_k)

        # Calculate how many were dropped by cap
        dropped_by_cap = max(0, len(filtered_docs) - len(selected))

        # Step 5: Calculate diversity and coverage metrics
        diversity_score = self._calculate_diversity_score(selected, embeddings)
        coverage_score = self._calculate_coverage_score(selected, cluster_assignments)

        logger.info(
            f"Soft selection: {len(documents)} candidates → {len(selected)} selected "
            f"(dropped: {dropped_by_weight} by weight, {dropped_by_cap} by cap) "
            f"diversity={diversity_score:.3f}, coverage={coverage_score:.3f}"
        )

        return SoftSelectionResult(
            documents=selected,
            soft_weights={d.id: soft_weights.get(d.id, 0.0) for d in selected},
            cluster_assignments={
                d.id: cluster_assignments.get(d.id, -1) for d in selected
            },
            diversity_score=diversity_score,
            coverage_score=coverage_score,
            dropped_by_weight=dropped_by_weight,
            dropped_by_cap=dropped_by_cap,
        )

    def _compute_soft_weights(
        self,
        documents: List[RetrievedDocument],
    ) -> Dict[str, float]:
        """
        Compute softmax weights with temperature scaling.

        Formula: w_i = exp(score_i / T) / Σ exp(score_j / T)

        Lower temperature (T→0): sharper distribution, winner-take-all
        Higher temperature (T→∞): more uniform distribution
        """
        if not documents:
            return {}

        scores = np.array([d.score for d in documents])

        # Handle edge case: all same score
        if np.std(scores) < 1e-8:
            uniform_weight = 1.0 / len(documents)
            return {doc.id: uniform_weight for doc in documents}

        # Temperature-scaled softmax with numerical stability
        scaled_scores = scores / self.config.temperature
        # Subtract max for numerical stability
        scaled_scores = scaled_scores - np.max(scaled_scores)
        exp_scores = np.exp(scaled_scores)
        softmax_weights = exp_scores / np.sum(exp_scores)

        return {
            doc.id: float(weight)
            for doc, weight in zip(documents, softmax_weights)
        }

    def _filter_by_min_weight(
        self,
        documents: List[RetrievedDocument],
        soft_weights: Dict[str, float],
    ) -> Tuple[List[RetrievedDocument], int]:
        """
        Filter documents below minimum weight threshold.

        Returns:
            Tuple of (filtered_documents, count_dropped)
        """
        filtered = []
        dropped = 0

        for doc in documents:
            weight = soft_weights.get(doc.id, 0.0)
            if weight >= self.config.min_weight:
                filtered.append(doc)
            else:
                dropped += 1
                logger.debug(f"Dropped doc {doc.id} with weight {weight:.4f} < {self.config.min_weight}")

        return filtered, dropped

    def _cluster_documents(
        self,
        documents: List[RetrievedDocument],
        embeddings: Dict[str, List[float]],
    ) -> Dict[str, int]:
        """
        Cluster documents in embedding space using k-means.

        This enables stratified selection to guarantee topic diversity.
        """
        # Get embeddings for documents that have them
        doc_ids = []
        embedding_matrix = []

        for doc in documents:
            if doc.id in embeddings:
                doc_ids.append(doc.id)
                embedding_matrix.append(embeddings[doc.id])

        if len(embedding_matrix) < self.config.num_clusters:
            # Not enough documents for meaningful clustering
            # Assign all to single cluster
            return {doc_id: 0 for doc_id in doc_ids}

        # Import here to avoid loading sklearn if not needed
        from sklearn.cluster import KMeans

        # Perform k-means clustering
        n_clusters = min(self.config.num_clusters, len(embedding_matrix))
        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10,
            max_iter=100,
        )

        try:
            cluster_labels = kmeans.fit_predict(np.array(embedding_matrix))
            return {
                doc_id: int(label)
                for doc_id, label in zip(doc_ids, cluster_labels)
            }
        except Exception as e:
            logger.warning(f"Clustering failed: {e}, using single cluster")
            return {doc_id: 0 for doc_id in doc_ids}

    def _mmr_select_with_quota(
        self,
        documents: List[RetrievedDocument],
        embeddings: Dict[str, List[float]],
        query_embedding: List[float],
        soft_weights: Dict[str, float],
        cluster_assignments: Dict[str, int],
        top_k: int,
    ) -> List[RetrievedDocument]:
        """
        MMR selection with stratified cluster quota.

        Phase 1: Round-robin selection (1 doc per cluster) to guarantee coverage
        Phase 2: MMR-based selection for remaining slots

        MMR Formula: score = λ * relevance - (1-λ) * max_redundancy
        """
        selected: List[RetrievedDocument] = []
        selected_ids: set = set()
        remaining = list(documents)

        # Group documents by cluster
        cluster_docs: Dict[int, List[RetrievedDocument]] = defaultdict(list)
        for doc in documents:
            cluster_id = cluster_assignments.get(doc.id, -1)
            cluster_docs[cluster_id].append(doc)

        # Sort each cluster by score (descending)
        for cluster_id in cluster_docs:
            cluster_docs[cluster_id].sort(key=lambda d: d.score, reverse=True)

        # Phase 1: Stratified selection (round-robin by cluster)
        # Guarantees diversity by selecting best doc from each cluster
        clusters_to_cover = sorted(cluster_docs.keys())

        for cluster_id in clusters_to_cover:
            if len(selected) >= top_k:
                break

            docs_in_cluster = cluster_docs[cluster_id]
            for doc in docs_in_cluster:
                if doc.id not in selected_ids:
                    selected.append(doc)
                    selected_ids.add(doc.id)
                    remaining.remove(doc)
                    break  # One per cluster in phase 1

        # Phase 2: MMR-based selection for remaining slots
        while len(selected) < top_k and remaining:
            best_doc = None
            best_score = float('-inf')

            for doc in remaining:
                if doc.id in selected_ids:
                    continue

                # Calculate relevance (similarity to query)
                if doc.id in embeddings:
                    relevance = self._cosine_similarity(
                        embeddings[doc.id],
                        query_embedding
                    )
                else:
                    # Fallback: use normalized rerank score as relevance proxy
                    relevance = doc.score

                # Calculate redundancy (max similarity to already selected docs)
                redundancy = 0.0
                if selected and doc.id in embeddings:
                    for sel_doc in selected:
                        if sel_doc.id in embeddings:
                            sim = self._cosine_similarity(
                                embeddings[doc.id],
                                embeddings[sel_doc.id]
                            )
                            redundancy = max(redundancy, sim)

                # MMR score: λ * relevance - (1-λ) * redundancy
                mmr_score = (
                    self.config.mmr_lambda * relevance -
                    (1 - self.config.mmr_lambda) * redundancy
                )

                # Weight by soft weight (boost high-relevance docs)
                weight = soft_weights.get(doc.id, 0.5)
                final_score = mmr_score * (0.5 + weight)  # weight in [0,1] -> multiplier in [0.5, 1.5]

                if final_score > best_score:
                    best_score = final_score
                    best_doc = doc

            if best_doc:
                selected.append(best_doc)
                selected_ids.add(best_doc.id)
                remaining.remove(best_doc)
            else:
                break

        return selected

    def _weighted_select(
        self,
        documents: List[RetrievedDocument],
        soft_weights: Dict[str, float],
        top_k: int,
    ) -> List[RetrievedDocument]:
        """
        Fallback selection when embeddings are not available.
        Selects documents by combined score * soft_weight.
        """
        # Sort by weighted score
        weighted_docs = sorted(
            documents,
            key=lambda d: d.score * soft_weights.get(d.id, 0.5),
            reverse=True,
        )
        return weighted_docs[:top_k]

    def _calculate_diversity_score(
        self,
        documents: List[RetrievedDocument],
        embeddings: Optional[Dict[str, List[float]]],
    ) -> float:
        """
        Calculate diversity score as 1 - average pairwise similarity.

        Higher score = more diverse selection.
        Range: [0, 1] where 1 means completely dissimilar documents.
        """
        if not embeddings or len(documents) < 2:
            return 1.0  # Single doc or no embeddings = max diversity by default

        similarities = []
        for i, doc1 in enumerate(documents):
            for doc2 in documents[i+1:]:
                if doc1.id in embeddings and doc2.id in embeddings:
                    sim = self._cosine_similarity(
                        embeddings[doc1.id],
                        embeddings[doc2.id]
                    )
                    similarities.append(sim)

        if not similarities:
            return 1.0

        avg_similarity = np.mean(similarities)
        return float(1.0 - avg_similarity)

    def _calculate_coverage_score(
        self,
        documents: List[RetrievedDocument],
        cluster_assignments: Dict[str, int],
    ) -> float:
        """
        Calculate cluster coverage score.

        Score = (# clusters with ≥1 selected doc) / (total # clusters)
        Range: [0, 1] where 1 means all clusters are represented.
        """
        if not cluster_assignments:
            return 1.0  # No clustering = full coverage by default

        total_clusters = len(set(cluster_assignments.values()))
        if total_clusters == 0:
            return 1.0

        covered_clusters = set()
        for doc in documents:
            if doc.id in cluster_assignments:
                covered_clusters.add(cluster_assignments[doc.id])

        return len(covered_clusters) / total_clusters

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0

        a_np = np.array(a)
        b_np = np.array(b)

        dot_product = np.dot(a_np, b_np)
        norm_a = np.linalg.norm(a_np)
        norm_b = np.linalg.norm(b_np)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))


def allocate_token_budget(
    documents: List[RetrievedDocument],
    soft_weights: Dict[str, float],
    total_budget: int,
    min_tokens_per_doc: int = 200,
) -> Dict[str, int]:
    """
    Allocate tokens proportionally based on soft weights.

    Formula: tokens_i = max(min_tokens, floor(total_budget * w_i / Σw))

    If a document can't fit minimum tokens, it's dropped (returns 0 tokens).

    Args:
        documents: Selected documents
        soft_weights: Soft selection weights (normalized)
        total_budget: Total token budget for context
        min_tokens_per_doc: Minimum tokens per document (drop if can't fit)

    Returns:
        Dict mapping doc_id to allocated tokens (0 means dropped)
    """
    if not documents:
        return {}

    # Normalize weights for selected documents
    selected_weights = {}
    for doc in documents:
        selected_weights[doc.id] = soft_weights.get(doc.id, 1.0 / len(documents))

    total_weight = sum(selected_weights.values())
    if total_weight == 0:
        total_weight = 1.0  # Avoid division by zero

    # First pass: proportional allocation
    allocations = {}
    for doc in documents:
        weight = selected_weights[doc.id] / total_weight
        tokens = int(total_budget * weight)

        # Enforce minimum or drop
        if tokens < min_tokens_per_doc:
            # Check if we can afford minimum
            if min_tokens_per_doc <= total_budget / len(documents):
                tokens = min_tokens_per_doc
            else:
                tokens = 0  # Drop this document

        allocations[doc.id] = tokens

    # Second pass: redistribute if over budget
    total_allocated = sum(allocations.values())

    if total_allocated > total_budget:
        # Scale down proportionally
        scale = total_budget / total_allocated
        for doc_id in allocations:
            if allocations[doc_id] > 0:
                new_tokens = int(allocations[doc_id] * scale)
                if new_tokens < min_tokens_per_doc:
                    allocations[doc_id] = 0  # Drop if below minimum after scaling
                else:
                    allocations[doc_id] = new_tokens

    # Third pass: redistribute freed budget from dropped docs
    active_docs = [d for d in documents if allocations[d.id] > 0]
    dropped_budget = sum(
        allocations[d.id] for d in documents if allocations[d.id] == 0
    )

    if dropped_budget > 0 and active_docs:
        # Distribute freed budget to active docs by weight
        active_weight = sum(selected_weights[d.id] for d in active_docs)
        if active_weight > 0:
            for doc in active_docs:
                weight = selected_weights[doc.id] / active_weight
                allocations[doc.id] += int(dropped_budget * weight)

    return allocations


# Global instance with default config
soft_selector = SoftSelector()


def get_soft_selector(config: Optional[SoftSelectionConfig] = None) -> SoftSelector:
    """Get a SoftSelector instance with custom config."""
    if config:
        return SoftSelector(config)
    return soft_selector
