#!/usr/bin/env python3
"""
Benchmark Script for Soft Selection RAG Pipeline

Measures and compares:
- Latency (p50, p90, p99)
- Diversity score (1 - avg pairwise similarity)
- Coverage score (% clusters represented)
- Redundancy (avg pairwise similarity between selected docs)
- Document count and distribution

Usage:
    python benchmark_soft_selection.py --tenant-id <tenant> [--queries-file queries.txt]
    python benchmark_soft_selection.py --tenant-id <tenant> --baseline  # Compare with soft selection OFF
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from statistics import mean

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rag.rag_pipeline import RAGPipeline
from app.services.rag.multi_stage_retriever import MultiStageRetriever
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Default test queries (Spanish, legal/document domain)
DEFAULT_QUERIES = [
    "¿Cuáles son las cláusulas de confidencialidad en los contratos?",
    "¿Qué dice la normativa sobre protección de datos personales?",
    "Explica las obligaciones del arrendatario según el contrato",
    "¿Cuáles son los plazos de prescripción según la ley?",
    "Resume las condiciones de terminación anticipada del contrato",
    "¿Qué documentos se requieren para la constitución de una sociedad?",
    "Analiza las cláusulas de indemnización en el acuerdo",
    "¿Cuáles son los requisitos para la firma electrónica válida?",
    "Lista las obligaciones fiscales de las empresas",
    "¿Qué establece el RGPD sobre el consentimiento del usuario?",
]


@dataclass
class QueryResult:
    """Result of a single query benchmark."""
    query: str
    latency_ms: float
    num_docs: int
    diversity_score: float
    coverage_score: float
    avg_score: float
    top_score: float
    context_tokens: int = 0
    context_max_tokens: int = 0
    context_truncated: bool = False
    soft_weights: Dict[str, float] = field(default_factory=dict)
    cluster_distribution: Dict[int, int] = field(default_factory=dict)
    confidence: float = 0.0
    error: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Aggregated benchmark results."""
    name: str
    num_queries: int
    # Latency
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p99_ms: float
    latency_avg_ms: float
    # Quality
    avg_diversity: float
    avg_coverage: float
    avg_redundancy: float  # 1 - diversity
    avg_docs_per_query: float
    avg_confidence: float
    # Context assembly
    avg_context_tokens: float
    avg_context_utilization: float
    truncation_rate: float
    # Scores
    avg_top_score: float
    avg_mean_score: float
    # Errors
    error_count: int
    # Raw results
    query_results: List[QueryResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "num_queries": self.num_queries,
            "latency": {
                "p50_ms": round(self.latency_p50_ms, 1),
                "p90_ms": round(self.latency_p90_ms, 1),
                "p99_ms": round(self.latency_p99_ms, 1),
                "avg_ms": round(self.latency_avg_ms, 1),
            },
            "quality": {
                "diversity": round(self.avg_diversity, 3),
                "coverage": round(self.avg_coverage, 3),
                "redundancy": round(self.avg_redundancy, 3),
                "avg_docs": round(self.avg_docs_per_query, 1),
                "confidence": round(self.avg_confidence, 3),
            },
            "context": {
                "avg_tokens": round(self.avg_context_tokens, 1),
                "avg_utilization": round(self.avg_context_utilization, 3),
                "truncation_rate": round(self.truncation_rate, 3),
            },
            "scores": {
                "avg_top": round(self.avg_top_score, 3),
                "avg_mean": round(self.avg_mean_score, 3),
            },
            "errors": self.error_count,
        }


class RAGBenchmark:
    """Benchmark runner for RAG pipeline with soft selection."""

    def __init__(
        self,
        tenant_id: str,
        soft_selection_enabled: bool = True,
    ):
        self.tenant_id = tenant_id
        self.soft_selection_enabled = soft_selection_enabled
        self.pipeline = RAGPipeline(
            retriever=MultiStageRetriever(soft_selection_enabled=soft_selection_enabled),
        )

    async def initialize(self):
        """Initialize the RAG pipeline."""
        await self.pipeline.initialize()
        logger.info(f"Pipeline initialized (soft_selection={self.soft_selection_enabled})")

    async def run_query(self, query: str) -> QueryResult:
        """Run a single query and collect metrics."""
        start_time = time.perf_counter()

        try:
            response = await self.pipeline.process_query(
                query=query,
                tenant_id=self.tenant_id,
                top_k=15,  # Request more to see filtering effect
                validate_claims=False,  # Skip for speed
                use_cache=False,  # Don't use cache for benchmarking
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract metrics from response
            sources = response.sources
            context_info = response.context_info

            # Calculate diversity and coverage from context_info
            selection_metadata = context_info.get("selection_metadata", {})
            diversity_raw = selection_metadata.get("diversity_score", 0.0)
            coverage_raw = selection_metadata.get("coverage_score", 0.0)
            diversity = float(diversity_raw) if diversity_raw is not None else 0.0
            coverage = float(coverage_raw) if coverage_raw is not None else 0.0

            # Context assembly metrics
            context_tokens = int(context_info.get("total_tokens") or 0)
            context_max_tokens = int(context_info.get("max_tokens") or 0)
            context_truncated = bool(context_info.get("truncated") or False)

            # Extract soft weights and cluster distribution
            soft_weights = {}
            cluster_dist = {}
            for doc in sources:
                if doc.soft_weight is not None:
                    soft_weights[doc.id] = doc.soft_weight
                if doc.cluster_id is not None:
                    cluster_dist[doc.cluster_id] = cluster_dist.get(doc.cluster_id, 0) + 1

            # Calculate scores
            scores = [d.score for d in sources] if sources else []

            return QueryResult(
                query=query,
                latency_ms=latency_ms,
                num_docs=len(sources),
                diversity_score=diversity,
                coverage_score=coverage,
                avg_score=mean(scores) if scores else 0.0,
                top_score=max(scores) if scores else 0.0,
                context_tokens=context_tokens,
                context_max_tokens=context_max_tokens,
                context_truncated=context_truncated,
                soft_weights=soft_weights,
                cluster_distribution=cluster_dist,
                confidence=response.confidence_score,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("Query failed")
            return QueryResult(
                query=query,
                latency_ms=latency_ms,
                num_docs=0,
                diversity_score=0.0,
                coverage_score=0.0,
                avg_score=0.0,
                top_score=0.0,
                confidence=0.0,
                error=str(e),
            )

    @staticmethod
    def _percentile(sorted_values: List[float], p: float) -> float:
        """
        Compute percentile using linear interpolation.

        Args:
            sorted_values: Values sorted ascending.
            p: Percentile in [0, 100].
        """
        if not sorted_values:
            return 0.0
        if p <= 0:
            return sorted_values[0]
        if p >= 100:
            return sorted_values[-1]

        pos = (len(sorted_values) - 1) * (p / 100.0)
        lower = int(pos)
        upper = min(lower + 1, len(sorted_values) - 1)
        if lower == upper:
            return sorted_values[lower]
        weight = pos - lower
        return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight

    async def run_benchmark(
        self,
        queries: List[str],
        name: str = "benchmark",
    ) -> BenchmarkResult:
        """Run benchmark on a list of queries."""
        logger.info(f"Starting benchmark '{name}' with {len(queries)} queries...")

        results: List[QueryResult] = []

        for i, query in enumerate(queries):
            logger.info(f"  [{i+1}/{len(queries)}] {query[:50]}...")
            result = await self.run_query(query)
            results.append(result)

            # Small delay between queries to avoid overwhelming the system
            await asyncio.sleep(0.5)

        # Aggregate results
        latencies = [r.latency_ms for r in results if r.error is None]
        diversities = [r.diversity_score for r in results if r.error is None]
        coverages = [r.coverage_score for r in results if r.error is None]
        doc_counts = [r.num_docs for r in results if r.error is None]
        confidences = [r.confidence for r in results if r.error is None]
        top_scores = [r.top_score for r in results if r.error is None]
        avg_scores = [r.avg_score for r in results if r.error is None]
        context_tokens = [r.context_tokens for r in results if r.error is None]
        context_utils = [
            (r.context_tokens / r.context_max_tokens)
            for r in results
            if r.error is None and r.context_max_tokens
        ]
        truncations = [r.context_truncated for r in results if r.error is None]
        errors = [r for r in results if r.error is not None]

        # Calculate percentiles
        if latencies:
            sorted_latencies = sorted(latencies)
            p50 = self._percentile(sorted_latencies, 50)
            p90 = self._percentile(sorted_latencies, 90)
            p99 = self._percentile(sorted_latencies, 99)
        else:
            p50 = p90 = p99 = 0.0

        return BenchmarkResult(
            name=name,
            num_queries=len(queries),
            latency_p50_ms=p50,
            latency_p90_ms=p90,
            latency_p99_ms=p99,
            latency_avg_ms=mean(latencies) if latencies else 0.0,
            avg_diversity=mean(diversities) if diversities else 0.0,
            avg_coverage=mean(coverages) if coverages else 0.0,
            avg_redundancy=1.0 - mean(diversities) if diversities else 1.0,
            avg_docs_per_query=mean(doc_counts) if doc_counts else 0.0,
            avg_confidence=mean(confidences) if confidences else 0.0,
            avg_context_tokens=mean(context_tokens) if context_tokens else 0.0,
            avg_context_utilization=mean(context_utils) if context_utils else 0.0,
            truncation_rate=(sum(1 for t in truncations if t) / len(truncations)) if truncations else 0.0,
            avg_top_score=mean(top_scores) if top_scores else 0.0,
            avg_mean_score=mean(avg_scores) if avg_scores else 0.0,
            error_count=len(errors),
            query_results=results,
        )


def print_comparison(baseline: BenchmarkResult, soft_selection: BenchmarkResult):
    """Print side-by-side comparison of results."""
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON: Baseline vs Soft Selection")
    print("=" * 70)

    def fmt_change(baseline_val: float, new_val: float, higher_is_better: bool = True) -> str:
        if baseline_val == 0:
            return "N/A"
        change = ((new_val - baseline_val) / baseline_val) * 100
        arrow = "↑" if change > 0 else "↓" if change < 0 else "="
        is_good = (change > 0 and higher_is_better) or (change < 0 and not higher_is_better)
        color = "\033[92m" if is_good else "\033[91m" if not is_good else "\033[0m"
        return f"{color}{arrow} {abs(change):.1f}%\033[0m"

    print(f"\n{'Metric':<25} {'Baseline':>12} {'Soft Select':>12} {'Change':>12}")
    print("-" * 70)

    # Latency (lower is better)
    print(f"{'Latency p50 (ms)':<25} {baseline.latency_p50_ms:>12.1f} {soft_selection.latency_p50_ms:>12.1f} {fmt_change(baseline.latency_p50_ms, soft_selection.latency_p50_ms, False):>12}")
    print(f"{'Latency p90 (ms)':<25} {baseline.latency_p90_ms:>12.1f} {soft_selection.latency_p90_ms:>12.1f} {fmt_change(baseline.latency_p90_ms, soft_selection.latency_p90_ms, False):>12}")

    print("-" * 70)

    # Quality (higher is better)
    print(f"{'Diversity':<25} {baseline.avg_diversity:>12.3f} {soft_selection.avg_diversity:>12.3f} {fmt_change(baseline.avg_diversity, soft_selection.avg_diversity, True):>12}")
    print(f"{'Coverage':<25} {baseline.avg_coverage:>12.3f} {soft_selection.avg_coverage:>12.3f} {fmt_change(baseline.avg_coverage, soft_selection.avg_coverage, True):>12}")
    print(f"{'Redundancy':<25} {baseline.avg_redundancy:>12.3f} {soft_selection.avg_redundancy:>12.3f} {fmt_change(baseline.avg_redundancy, soft_selection.avg_redundancy, False):>12}")

    print("-" * 70)

    # Scores
    print(f"{'Avg Top Score':<25} {baseline.avg_top_score:>12.3f} {soft_selection.avg_top_score:>12.3f} {fmt_change(baseline.avg_top_score, soft_selection.avg_top_score, True):>12}")
    print(f"{'Avg Confidence':<25} {baseline.avg_confidence:>12.3f} {soft_selection.avg_confidence:>12.3f} {fmt_change(baseline.avg_confidence, soft_selection.avg_confidence, True):>12}")
    print(f"{'Avg Docs/Query':<25} {baseline.avg_docs_per_query:>12.1f} {soft_selection.avg_docs_per_query:>12.1f} {fmt_change(baseline.avg_docs_per_query, soft_selection.avg_docs_per_query, True):>12}")

    print("-" * 70)

    # Context
    print(f"{'Ctx Tokens (avg)':<25} {baseline.avg_context_tokens:>12.1f} {soft_selection.avg_context_tokens:>12.1f} {fmt_change(baseline.avg_context_tokens, soft_selection.avg_context_tokens, True):>12}")
    print(f"{'Ctx Utilization':<25} {baseline.avg_context_utilization:>12.3f} {soft_selection.avg_context_utilization:>12.3f} {fmt_change(baseline.avg_context_utilization, soft_selection.avg_context_utilization, True):>12}")
    print(f"{'Ctx Truncation Rate':<25} {baseline.truncation_rate:>12.3f} {soft_selection.truncation_rate:>12.3f} {fmt_change(baseline.truncation_rate, soft_selection.truncation_rate, False):>12}")

    print("-" * 70)
    print(f"{'Errors':<25} {baseline.error_count:>12d} {soft_selection.error_count:>12d}")
    print("=" * 70)


def print_single_result(result: BenchmarkResult):
    """Print results for a single benchmark run."""
    print("\n" + "=" * 50)
    print(f"BENCHMARK RESULTS: {result.name}")
    print("=" * 50)

    print(f"\nQueries: {result.num_queries}")
    print(f"Errors: {result.error_count}")

    print("\n--- Latency ---")
    print(f"  p50: {result.latency_p50_ms:.1f} ms")
    print(f"  p90: {result.latency_p90_ms:.1f} ms")
    print(f"  p99: {result.latency_p99_ms:.1f} ms")
    print(f"  avg: {result.latency_avg_ms:.1f} ms")

    print("\n--- Quality ---")
    print(f"  Diversity:  {result.avg_diversity:.3f}")
    print(f"  Coverage:   {result.avg_coverage:.3f}")
    print(f"  Redundancy: {result.avg_redundancy:.3f}")

    print("\n--- Scores ---")
    print(f"  Avg Top Score: {result.avg_top_score:.3f}")
    print(f"  Avg Mean Score: {result.avg_mean_score:.3f}")
    print(f"  Avg Confidence: {result.avg_confidence:.3f}")
    print(f"  Avg Docs/Query: {result.avg_docs_per_query:.1f}")

    print("\n--- Context ---")
    print(f"  Avg Tokens: {result.avg_context_tokens:.1f}")
    print(f"  Avg Utilization: {result.avg_context_utilization:.3f}")
    print(f"  Truncation Rate: {result.truncation_rate:.3f}")

    print("=" * 50)


async def main():
    parser = argparse.ArgumentParser(description="Benchmark RAG Soft Selection")
    parser.add_argument("--tenant-id", required=True, help="Tenant ID for queries")
    parser.add_argument("--queries-file", help="File with queries (one per line)")
    parser.add_argument("--baseline", action="store_true", help="Run comparison with soft selection OFF")
    parser.add_argument("--output", help="Output JSON file for results")
    parser.add_argument("--num-queries", type=int, default=10, help="Number of queries to run")

    args = parser.parse_args()

    # Load queries
    if args.queries_file and os.path.exists(args.queries_file):
        with open(args.queries_file, 'r', encoding="utf-8") as f:
            queries = [line.strip() for line in f if line.strip()]
    else:
        queries = DEFAULT_QUERIES[:args.num_queries]

    logger.info(f"Running benchmark with {len(queries)} queries for tenant {args.tenant_id}")

    if args.baseline:
        # Run comparison: baseline vs soft selection

        # First, run with soft selection OFF
        logger.info("\n=== Running BASELINE (soft selection OFF) ===")

        baseline_benchmark = RAGBenchmark(
            tenant_id=args.tenant_id,
            soft_selection_enabled=False,
        )
        await baseline_benchmark.initialize()
        baseline_result = await baseline_benchmark.run_benchmark(
            queries=queries,
            name="baseline",
        )

        # Then, run with soft selection ON
        logger.info("\n=== Running SOFT SELECTION (ON) ===")

        soft_benchmark = RAGBenchmark(
            tenant_id=args.tenant_id,
            soft_selection_enabled=True,
        )
        await soft_benchmark.initialize()
        soft_result = await soft_benchmark.run_benchmark(
            queries=queries,
            name="soft_selection",
        )

        # Print comparison
        print_comparison(baseline_result, soft_result)

        # Save results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump({
                    "baseline": baseline_result.to_dict(),
                    "soft_selection": soft_result.to_dict(),
                }, f, indent=2)
            logger.info(f"Results saved to {args.output}")

    else:
        # Single run with current configuration
        benchmark = RAGBenchmark(
            tenant_id=args.tenant_id,
            soft_selection_enabled=settings.rag_soft_selection_enabled,
        )
        await benchmark.initialize()
        result = await benchmark.run_benchmark(
            queries=queries,
            name="soft_selection" if settings.rag_soft_selection_enabled else "baseline",
        )

        print_single_result(result)

        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
            logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
