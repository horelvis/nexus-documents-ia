"""
Tests for Soft Selection Module

Covers:
- Softmax temperature effect on weight sharpness
- Minimum weight filtering
- K-means clustering
- MMR with stratified cluster quota
- Diversity and coverage metrics
- Proportional token budget allocation
"""

import pytest
import numpy as np
from typing import List, Dict

# Add parent directory to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.rag.soft_selection import (
    SoftSelector,
    SoftSelectionConfig,
    SoftSelectionResult,
    allocate_token_budget,
)
from app.services.rag.models import RetrievedDocument


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_doc(
    doc_id: str,
    score: float,
    title: str = "Test Doc",
) -> RetrievedDocument:
    """Create a test document with given parameters."""
    return RetrievedDocument(
        id=doc_id,
        title=title,
        content=f"Content for {doc_id}",
        score=score,
        document_type="test",
        tenant_id="test-tenant",
    )


def create_test_docs_with_scores(scores: List[float]) -> List[RetrievedDocument]:
    """Create list of test documents with given scores."""
    return [
        create_test_doc(f"doc_{i}", score)
        for i, score in enumerate(scores)
    ]


def create_test_embeddings(
    doc_ids: List[str],
    dim: int = 10,
    seed: int = 42,
) -> Dict[str, List[float]]:
    """Create random embeddings for given document IDs."""
    np.random.seed(seed)
    return {
        doc_id: np.random.randn(dim).tolist()
        for doc_id in doc_ids
    }


def create_similar_embeddings(
    doc_ids: List[str],
    dim: int = 10,
    similarity: float = 0.9,
) -> Dict[str, List[float]]:
    """Create embeddings that are similar to each other."""
    base = np.random.randn(dim)
    base = base / np.linalg.norm(base)  # Normalize

    embeddings = {}
    for i, doc_id in enumerate(doc_ids):
        # Add small noise to base vector
        noise = np.random.randn(dim) * (1 - similarity)
        vec = base + noise
        vec = vec / np.linalg.norm(vec)
        embeddings[doc_id] = vec.tolist()

    return embeddings


def create_clustered_embeddings(
    doc_ids: List[str],
    n_clusters: int = 3,
    dim: int = 10,
) -> Dict[str, List[float]]:
    """Create embeddings that form distinct clusters."""
    np.random.seed(42)

    # Create cluster centroids (orthogonal directions)
    centroids = []
    for i in range(n_clusters):
        centroid = np.zeros(dim)
        centroid[i % dim] = 1.0
        centroids.append(centroid)

    # Assign docs to clusters and add small noise
    embeddings = {}
    for i, doc_id in enumerate(doc_ids):
        cluster_idx = i % n_clusters
        noise = np.random.randn(dim) * 0.1
        vec = centroids[cluster_idx] + noise
        vec = vec / np.linalg.norm(vec)
        embeddings[doc_id] = vec.tolist()

    return embeddings


# ============================================================================
# Test: Softmax Weights
# ============================================================================


class TestSoftmaxWeights:
    """Tests for _compute_soft_weights method."""

    def test_weights_sum_to_one(self):
        """Softmax weights should sum to 1.0."""
        config = SoftSelectionConfig(temperature=0.5)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7, 0.6, 0.5])
        weights = selector._compute_soft_weights(docs)

        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, expected 1.0"

    def test_higher_score_gets_higher_weight(self):
        """Documents with higher scores should get higher weights."""
        config = SoftSelectionConfig(temperature=0.5)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.5, 0.2])
        weights = selector._compute_soft_weights(docs)

        assert weights["doc_0"] > weights["doc_1"] > weights["doc_2"], \
            f"Weights not in descending order: {weights}"

    def test_low_temperature_sharpens_distribution(self):
        """Lower temperature should make distribution more peaked."""
        docs = create_test_docs_with_scores([0.9, 0.7, 0.5])

        # Low temperature (sharper)
        low_temp_selector = SoftSelector(SoftSelectionConfig(temperature=0.1))
        low_temp_weights = low_temp_selector._compute_soft_weights(docs)

        # High temperature (more uniform)
        high_temp_selector = SoftSelector(SoftSelectionConfig(temperature=2.0))
        high_temp_weights = high_temp_selector._compute_soft_weights(docs)

        # With low T, top doc should get most weight
        low_temp_top_ratio = low_temp_weights["doc_0"] / low_temp_weights["doc_2"]
        high_temp_top_ratio = high_temp_weights["doc_0"] / high_temp_weights["doc_2"]

        assert low_temp_top_ratio > high_temp_top_ratio, \
            f"Low T ratio {low_temp_top_ratio:.2f} should be > high T ratio {high_temp_top_ratio:.2f}"

    def test_equal_scores_gives_uniform_weights(self):
        """When all scores are equal, weights should be uniform."""
        config = SoftSelectionConfig(temperature=0.5)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.8, 0.8, 0.8, 0.8])
        weights = selector._compute_soft_weights(docs)

        expected = 1.0 / 4
        for doc_id, weight in weights.items():
            assert abs(weight - expected) < 1e-6, \
                f"Expected uniform weight {expected}, got {weight}"

    def test_empty_docs_returns_empty_weights(self):
        """Empty document list should return empty weights."""
        selector = SoftSelector()
        weights = selector._compute_soft_weights([])

        assert weights == {}


# ============================================================================
# Test: Minimum Weight Filtering
# ============================================================================


class TestMinWeightFiltering:
    """Tests for _filter_by_min_weight method."""

    def test_filters_below_threshold(self):
        """Documents with weight below min_weight should be filtered out."""
        config = SoftSelectionConfig(min_weight=0.1)
        selector = SoftSelector(config)

        # Create docs with known weights (via scores)
        # High score doc gets weight ~0.9, low score ~0.1
        docs = create_test_docs_with_scores([0.95, 0.3])
        weights = selector._compute_soft_weights(docs)

        filtered, dropped = selector._filter_by_min_weight(docs, weights)

        # Should have filtered at least one doc
        assert len(filtered) < len(docs) or all(weights[d.id] >= 0.1 for d in filtered)

    def test_counts_dropped_correctly(self):
        """Should correctly count number of dropped documents."""
        config = SoftSelectionConfig(min_weight=0.5)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.99, 0.1, 0.05, 0.01])
        weights = {
            "doc_0": 0.8,
            "doc_1": 0.15,
            "doc_2": 0.04,
            "doc_3": 0.01,
        }

        filtered, dropped = selector._filter_by_min_weight(docs, weights)

        # doc_2 and doc_3 should be dropped (below 0.5)
        assert dropped == 3, f"Expected 3 dropped, got {dropped}"
        assert len(filtered) == 1

    def test_keeps_all_above_threshold(self):
        """Documents above threshold should be kept."""
        config = SoftSelectionConfig(min_weight=0.01)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        weights = selector._compute_soft_weights(docs)

        filtered, dropped = selector._filter_by_min_weight(docs, weights)

        assert len(filtered) == 3
        assert dropped == 0


# ============================================================================
# Test: Clustering
# ============================================================================


class TestClustering:
    """Tests for _cluster_documents method."""

    def test_assigns_valid_cluster_ids(self):
        """All cluster IDs should be in valid range [0, n_clusters)."""
        config = SoftSelectionConfig(num_clusters=3)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7, 0.6, 0.5, 0.4])
        embeddings = create_test_embeddings([d.id for d in docs])

        clusters = selector._cluster_documents(docs, embeddings)

        for doc_id, cluster_id in clusters.items():
            assert 0 <= cluster_id < config.num_clusters, \
                f"Invalid cluster ID {cluster_id} for doc {doc_id}"

    def test_all_docs_get_cluster(self):
        """All documents should be assigned to a cluster."""
        config = SoftSelectionConfig(num_clusters=3)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7, 0.6])
        embeddings = create_test_embeddings([d.id for d in docs])

        clusters = selector._cluster_documents(docs, embeddings)

        for doc in docs:
            assert doc.id in clusters, f"Doc {doc.id} not assigned to cluster"

    def test_fewer_docs_than_clusters(self):
        """When fewer docs than clusters, should handle gracefully."""
        config = SoftSelectionConfig(num_clusters=5)
        selector = SoftSelector(config)

        # Only 3 docs, but config says 5 clusters
        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        embeddings = create_test_embeddings([d.id for d in docs])

        # Should not raise, should assign to single cluster
        clusters = selector._cluster_documents(docs, embeddings)

        assert len(clusters) == 3
        # With too few docs, all go to cluster 0
        assert all(c == 0 for c in clusters.values())


# ============================================================================
# Test: MMR Selection
# ============================================================================


class TestMMRSelection:
    """Tests for _mmr_select_with_quota method."""

    def test_respects_top_k(self):
        """Should not select more than top_k documents."""
        config = SoftSelectionConfig(num_clusters=3, mmr_lambda=0.7)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.85, 0.8, 0.75, 0.7, 0.65])
        embeddings = create_clustered_embeddings([d.id for d in docs], n_clusters=3)
        query_emb = np.random.randn(10).tolist()
        weights = selector._compute_soft_weights(docs)
        clusters = selector._cluster_documents(docs, embeddings)

        top_k = 4
        selected = selector._mmr_select_with_quota(
            documents=docs,
            embeddings=embeddings,
            query_embedding=query_emb,
            soft_weights=weights,
            cluster_assignments=clusters,
            top_k=top_k,
        )

        assert len(selected) <= top_k, f"Selected {len(selected)}, expected <= {top_k}"

    def test_stratified_selection_covers_clusters(self):
        """Round-robin phase should guarantee cluster coverage."""
        config = SoftSelectionConfig(num_clusters=3, mmr_lambda=0.7)
        selector = SoftSelector(config)

        # Create 6 docs, 2 per cluster
        docs = create_test_docs_with_scores([0.9, 0.85, 0.8, 0.75, 0.7, 0.65])
        embeddings = create_clustered_embeddings([d.id for d in docs], n_clusters=3)
        query_emb = np.random.randn(10).tolist()
        weights = selector._compute_soft_weights(docs)
        clusters = selector._cluster_documents(docs, embeddings)

        # Select 3 docs - should get 1 from each cluster
        selected = selector._mmr_select_with_quota(
            documents=docs,
            embeddings=embeddings,
            query_embedding=query_emb,
            soft_weights=weights,
            cluster_assignments=clusters,
            top_k=3,
        )

        selected_clusters = {clusters[d.id] for d in selected}

        # Should cover all 3 clusters
        assert len(selected_clusters) >= 3, \
            f"Expected 3 clusters covered, got {len(selected_clusters)}: {selected_clusters}"

    def test_mmr_reduces_redundancy(self):
        """MMR should prefer diverse documents over redundant ones."""
        # Create 4 docs: 2 very similar (cluster A), 2 different (clusters B, C)
        config = SoftSelectionConfig(num_clusters=3, mmr_lambda=0.5)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.88, 0.85, 0.82])

        # Make doc_0 and doc_1 very similar, doc_2 and doc_3 different
        embeddings = {
            "doc_0": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "doc_1": [0.99, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Very similar to doc_0
            "doc_2": [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Different
            "doc_3": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # Different
        }

        query_emb = [0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        weights = selector._compute_soft_weights(docs)
        clusters = {"doc_0": 0, "doc_1": 0, "doc_2": 1, "doc_3": 2}

        selected = selector._mmr_select_with_quota(
            documents=docs,
            embeddings=embeddings,
            query_embedding=query_emb,
            soft_weights=weights,
            cluster_assignments=clusters,
            top_k=3,
        )

        selected_ids = {d.id for d in selected}

        # Should NOT select both doc_0 and doc_1 (too similar)
        # Due to stratified selection, should get doc_0/doc_1, doc_2, and doc_3
        assert "doc_2" in selected_ids or "doc_3" in selected_ids, \
            f"MMR should select diverse docs, got: {selected_ids}"


# ============================================================================
# Test: Diversity Score
# ============================================================================


class TestDiversityScore:
    """Tests for _calculate_diversity_score method."""

    def test_single_doc_max_diversity(self):
        """Single document should have max diversity (1.0)."""
        selector = SoftSelector()

        docs = create_test_docs_with_scores([0.9])
        embeddings = create_test_embeddings([d.id for d in docs])

        diversity = selector._calculate_diversity_score(docs, embeddings)

        assert diversity == 1.0

    def test_similar_docs_low_diversity(self):
        """Very similar documents should have low diversity."""
        selector = SoftSelector()

        docs = create_test_docs_with_scores([0.9, 0.85, 0.8])
        embeddings = create_similar_embeddings([d.id for d in docs], similarity=0.95)

        diversity = selector._calculate_diversity_score(docs, embeddings)

        # Should be low (< 0.3 for very similar)
        assert diversity < 0.3, f"Expected low diversity, got {diversity}"

    def test_diverse_docs_high_diversity(self):
        """Diverse documents should have high diversity score."""
        selector = SoftSelector()

        docs = create_test_docs_with_scores([0.9, 0.85, 0.8])

        # Create orthogonal embeddings (max diversity)
        embeddings = {
            "doc_0": [1.0, 0.0, 0.0, 0.0, 0.0],
            "doc_1": [0.0, 1.0, 0.0, 0.0, 0.0],
            "doc_2": [0.0, 0.0, 1.0, 0.0, 0.0],
        }

        diversity = selector._calculate_diversity_score(docs, embeddings)

        # Should be high (close to 1.0 for orthogonal)
        assert diversity > 0.9, f"Expected high diversity, got {diversity}"


# ============================================================================
# Test: Coverage Score
# ============================================================================


class TestCoverageScore:
    """Tests for _calculate_coverage_score method."""

    def test_full_coverage(self):
        """All clusters covered should give score 1.0."""
        selector = SoftSelector()

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        clusters = {"doc_0": 0, "doc_1": 1, "doc_2": 2}

        coverage = selector._calculate_coverage_score(docs, clusters)

        assert coverage == 1.0

    def test_partial_coverage(self):
        """Partial cluster coverage should give proportional score."""
        selector = SoftSelector()

        # Only 2 docs covering 2 of 3 clusters
        docs = create_test_docs_with_scores([0.9, 0.8])
        clusters = {"doc_0": 0, "doc_1": 1, "doc_2": 2}  # 3 clusters total

        coverage = selector._calculate_coverage_score(docs, clusters)

        # 2 of 3 clusters covered
        expected = 2 / 3
        assert abs(coverage - expected) < 0.01, f"Expected {expected}, got {coverage}"

    def test_no_clusters_full_coverage(self):
        """When no clustering is applied, should return 1.0."""
        selector = SoftSelector()

        docs = create_test_docs_with_scores([0.9, 0.8])

        coverage = selector._calculate_coverage_score(docs, {})

        assert coverage == 1.0


# ============================================================================
# Test: Token Budget Allocation
# ============================================================================


class TestTokenBudgetAllocation:
    """Tests for allocate_token_budget function."""

    def test_allocation_does_not_exceed_budget(self):
        """Total allocation should not exceed total budget."""
        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        weights = {"doc_0": 0.5, "doc_1": 0.3, "doc_2": 0.2}

        total_budget = 1000
        allocations = allocate_token_budget(
            documents=docs,
            soft_weights=weights,
            total_budget=total_budget,
            min_tokens_per_doc=100,
        )

        total_allocated = sum(allocations.values())

        assert total_allocated <= total_budget, \
            f"Allocated {total_allocated} exceeds budget {total_budget}"

    def test_proportional_to_weights(self):
        """Allocation should be roughly proportional to weights."""
        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        weights = {"doc_0": 0.6, "doc_1": 0.3, "doc_2": 0.1}

        allocations = allocate_token_budget(
            documents=docs,
            soft_weights=weights,
            total_budget=1000,
            min_tokens_per_doc=100,
        )

        # doc_0 should get significantly more than doc_2
        if allocations["doc_0"] > 0 and allocations["doc_2"] > 0:
            ratio = allocations["doc_0"] / allocations["doc_2"]
            # Weight ratio is 6:1, allocation ratio should be somewhat close
            assert ratio > 2.0, f"Expected doc_0 to get much more, ratio is {ratio}"

    def test_minimum_tokens_enforced(self):
        """Each allocated doc should have at least min_tokens."""
        docs = create_test_docs_with_scores([0.9, 0.8, 0.7])
        weights = {"doc_0": 0.5, "doc_1": 0.3, "doc_2": 0.2}

        min_tokens = 200
        allocations = allocate_token_budget(
            documents=docs,
            soft_weights=weights,
            total_budget=1000,
            min_tokens_per_doc=min_tokens,
        )

        for doc_id, tokens in allocations.items():
            assert tokens == 0 or tokens >= min_tokens, \
                f"Doc {doc_id} got {tokens} tokens, expected 0 or >= {min_tokens}"

    def test_drops_docs_below_minimum(self):
        """Documents that can't fit minimum should be dropped (0 tokens)."""
        docs = create_test_docs_with_scores([0.9, 0.8, 0.7, 0.6, 0.5])
        weights = {"doc_0": 0.4, "doc_1": 0.3, "doc_2": 0.15, "doc_3": 0.1, "doc_4": 0.05}

        # Very tight budget - can't fit all with min 200
        allocations = allocate_token_budget(
            documents=docs,
            soft_weights=weights,
            total_budget=600,
            min_tokens_per_doc=200,
        )

        # Some docs should be dropped
        dropped = sum(1 for t in allocations.values() if t == 0)
        assert dropped > 0, "Expected some docs to be dropped due to tight budget"

    def test_empty_docs_returns_empty(self):
        """Empty document list should return empty allocations."""
        allocations = allocate_token_budget(
            documents=[],
            soft_weights={},
            total_budget=1000,
        )

        assert allocations == {}


# ============================================================================
# Test: Full Selection Pipeline
# ============================================================================


class TestFullSelectionPipeline:
    """Integration tests for complete soft selection pipeline."""

    def test_end_to_end_selection(self):
        """Test complete selection pipeline."""
        config = SoftSelectionConfig(
            temperature=0.5,
            mmr_lambda=0.7,
            num_clusters=3,
            max_docs=5,
            min_weight=0.02,
        )
        selector = SoftSelector(config)

        # Create test data
        docs = create_test_docs_with_scores([0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65])
        embeddings = create_clustered_embeddings([d.id for d in docs], n_clusters=3)
        query_emb = np.random.randn(10).tolist()

        result = selector.select(
            documents=docs,
            embeddings=embeddings,
            top_k=5,
            query_embedding=query_emb,
        )

        # Validate result structure
        assert isinstance(result, SoftSelectionResult)
        assert len(result.documents) <= config.max_docs
        assert 0.0 <= result.diversity_score <= 1.0
        assert 0.0 <= result.coverage_score <= 1.0
        assert sum(result.soft_weights.values()) <= 1.0 + 1e-6

    def test_selection_without_embeddings(self):
        """Selection should work without embeddings (fallback mode)."""
        config = SoftSelectionConfig(max_docs=3)
        selector = SoftSelector(config)

        docs = create_test_docs_with_scores([0.9, 0.8, 0.7, 0.6])

        result = selector.select(
            documents=docs,
            embeddings=None,  # No embeddings
            top_k=3,
            query_embedding=None,
        )

        # Should still select documents
        assert len(result.documents) == 3
        assert result.diversity_score == 1.0  # Default when no embeddings

    def test_empty_documents_returns_empty_result(self):
        """Empty input should return empty result."""
        selector = SoftSelector()

        result = selector.select(
            documents=[],
            embeddings={},
            top_k=10,
        )

        assert result.documents == []
        assert result.soft_weights == {}
        assert result.diversity_score == 0.0
        assert result.coverage_score == 0.0


# ============================================================================
# Test: Cosine Similarity
# ============================================================================


class TestCosineSimilarity:
    """Tests for _cosine_similarity static method."""

    def test_identical_vectors_similarity_one(self):
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 2.0, 3.0]
        similarity = SoftSelector._cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 1e-6

    def test_orthogonal_vectors_similarity_zero(self):
        """Orthogonal vectors should have similarity 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        similarity = SoftSelector._cosine_similarity(vec_a, vec_b)

        assert abs(similarity) < 1e-6

    def test_opposite_vectors_similarity_negative(self):
        """Opposite vectors should have similarity -1.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        similarity = SoftSelector._cosine_similarity(vec_a, vec_b)

        assert abs(similarity + 1.0) < 1e-6

    def test_empty_vectors_return_zero(self):
        """Empty vectors should return 0.0."""
        similarity = SoftSelector._cosine_similarity([], [])
        assert similarity == 0.0

    def test_mismatched_lengths_return_zero(self):
        """Vectors of different lengths should return 0.0."""
        vec_a = [1.0, 2.0]
        vec_b = [1.0, 2.0, 3.0]
        similarity = SoftSelector._cosine_similarity(vec_a, vec_b)

        assert similarity == 0.0


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
