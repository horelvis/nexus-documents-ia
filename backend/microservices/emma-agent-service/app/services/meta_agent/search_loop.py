"""
Meta Agent Search Loop — Iterative strategy discovery.

The core ADAS loop:
    for iteration in range(max_iterations):
        1. GENERATE: N candidates (seed on iter 0, mutate+crossover+guided after)
        2. VALIDATE: AST-check each (reject invalid code)
        3. EXECUTE:  Run against discovery test set
        4. EVALUATE: Score via LLM-as-judge
        5. ARCHIVE:  Store results, deduplicate by code_hash
        6. CONVERGE: Stop if no improvement for 3 iterations

Before promoting best → validate against held-out test set.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from app.core.config import settings
from .archive import StrategyArchive, get_strategy_archive
from .evaluator import StrategyEvaluator
from .generator import StrategyGenerator
from .runner import StrategyRunner
from .schemas import (
    ArchiveEntry,
    SearchIteration,
    SearchJob,
    StrategyCandidate,
    TestSet,
)

logger = logging.getLogger(__name__)


class MetaAgentSearchLoop:
    """Iterative search for novel agent strategies."""

    def __init__(
        self,
        archive: Optional[StrategyArchive] = None,
        generator: Optional[StrategyGenerator] = None,
        runner: Optional[StrategyRunner] = None,
        evaluator: Optional[StrategyEvaluator] = None,
    ):
        self._archive = archive or get_strategy_archive()
        self._generator = generator or StrategyGenerator()
        self._runner = runner or StrategyRunner()
        self._evaluator = evaluator or StrategyEvaluator()

    async def run(
        self,
        test_set: TestSet,
        intent_target: str,
        sector_target: Optional[str] = None,
        max_iterations: Optional[int] = None,
        candidates_per_iteration: Optional[int] = None,
        job_id: Optional[str] = None,
    ) -> SearchJob:
        """Run the search loop.

        Args:
            test_set: Test set with discovery + validation cases
            intent_target: Intent to optimize for
            sector_target: Optional sector
            max_iterations: Override settings max
            candidates_per_iteration: Override settings count

        Returns:
            SearchJob with final status and best strategy
        """
        max_iter = max_iterations or settings.meta_agent_max_search_iterations
        n_candidates = candidates_per_iteration or settings.meta_agent_candidates_per_iteration

        # Get available tools for generation context
        available_tools = self._get_available_tools(sector_target)

        job_kwargs = dict(
            intent_target=intent_target,
            sector_target=sector_target,
            test_set_id=test_set.id,
            max_iterations=max_iter,
            candidates_per_iteration=n_candidates,
            status="running",
            started_at=datetime.utcnow().isoformat(),
        )
        if job_id:
            job_kwargs["job_id"] = job_id
        job = SearchJob(**job_kwargs)
        await self._archive.store_search_job(job)

        best_score = 0.0
        no_improvement_count = 0

        try:
            for iteration in range(max_iter):
                logger.info(
                    f"Search iteration {iteration}/{max_iter} "
                    f"for {intent_target}/{sector_target or 'generic'}"
                )

                # 1. GENERATE candidates
                candidates = await self._generate_candidates(
                    iteration, n_candidates, intent_target, sector_target, available_tools
                )

                if not candidates:
                    logger.warning(f"No valid candidates generated in iteration {iteration}")
                    iter_record = SearchIteration(
                        iteration=iteration,
                        candidates_generated=0,
                        candidates_valid=0,
                        best_score=best_score,
                    )
                    job.iterations.append(iter_record)
                    no_improvement_count += 1
                    if no_improvement_count >= 3:
                        logger.info("Converged: no improvement for 3 iterations")
                        break
                    continue

                # 2-4. RUN + EVALUATE each candidate
                iter_best_score = 0.0
                iter_best_id = None

                for candidate in candidates:
                    # Execute against discovery set
                    run_result = await self._runner.run_test_set(
                        candidate, test_set.discovery_cases
                    )

                    # Evaluate
                    archive_top = await self._archive.get_top_strategies(
                        intent_target, sector_target, limit=5
                    )
                    metrics = await self._evaluator.evaluate(
                        candidate, run_result, test_set.discovery_cases, archive_top
                    )

                    # 5. ARCHIVE
                    entry = ArchiveEntry(
                        strategy=candidate,
                        metrics=metrics,
                        test_set_id=test_set.id,
                        sample_count=len(test_set.discovery_cases),
                    )
                    await self._archive.add_entry(entry)

                    if metrics.composite_score > iter_best_score:
                        iter_best_score = metrics.composite_score
                        iter_best_id = candidate.id

                # Track iteration
                iter_record = SearchIteration(
                    iteration=iteration,
                    candidates_generated=len(candidates),
                    candidates_valid=len(candidates),
                    best_score=iter_best_score,
                    best_strategy_id=iter_best_id,
                )
                job.iterations.append(iter_record)

                # 6. CONVERGENCE check
                if iter_best_score > best_score:
                    best_score = iter_best_score
                    job.best_score = best_score
                    job.best_strategy_id = iter_best_id
                    no_improvement_count = 0
                else:
                    no_improvement_count += 1

                if no_improvement_count >= 3:
                    logger.info(f"Converged after {iteration + 1} iterations")
                    break

                # Update job in Redis
                await self._archive.store_search_job(job)

            # Final: validate best strategy
            if job.best_strategy_id and test_set.validation_cases:
                await self._validate_and_promote(
                    job.best_strategy_id, test_set
                )

            job.status = "completed"
            job.completed_at = datetime.utcnow().isoformat()

        except Exception as e:
            logger.error(f"Search loop failed: {e}", exc_info=True)
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow().isoformat()

        await self._archive.store_search_job(job)
        return job

    # ─── Internal ────────────────────────────────────────────────────────────

    async def _generate_candidates(
        self,
        iteration: int,
        n_candidates: int,
        intent_target: str,
        sector_target: Optional[str],
        available_tools: List[str],
    ) -> List[StrategyCandidate]:
        """Generate N candidates using appropriate mode for iteration."""
        candidates: List[StrategyCandidate] = []

        if iteration == 0:
            # Seed: generate baselines
            seeds = await self._generator.generate_seeds(
                intent_target, sector_target, available_tools
            )
            candidates.extend(seeds[:n_candidates])

        else:
            top_strategies = await self._archive.get_top_strategies(
                intent_target, sector_target, limit=5
            )

            for i in range(n_candidates):
                if not top_strategies:
                    # Guided generation from scratch
                    candidate = await self._generator.guided_generation(
                        intent_target, sector_target,
                        available_tools=available_tools,
                    )
                    if candidate:
                        candidate.generation = iteration
                        candidates.append(candidate)

                elif i == 0 and len(top_strategies) >= 1:
                    # Mutate best
                    candidate = await self._generator.mutate(
                        top_strategies[0], available_tools
                    )
                    if candidate:
                        candidate.generation = iteration
                        candidates.append(candidate)

                elif i == 1 and len(top_strategies) >= 2:
                    # Crossover top two
                    candidate = await self._generator.crossover(
                        top_strategies[0], top_strategies[1], available_tools
                    )
                    if candidate:
                        candidate.generation = iteration
                        candidates.append(candidate)

                else:
                    # LLM-guided with context
                    archive_context = self._format_archive_context(top_strategies)
                    candidate = await self._generator.guided_generation(
                        intent_target, sector_target,
                        archive_context=archive_context,
                        available_tools=available_tools,
                    )
                    if candidate:
                        candidate.generation = iteration
                        candidates.append(candidate)

        return candidates

    async def _validate_and_promote(
        self,
        strategy_id: str,
        test_set: TestSet,
    ) -> None:
        """Validate best strategy against held-out set and optionally promote."""
        entry = await self._archive.get_entry(strategy_id)
        if not entry or not test_set.validation_cases:
            return

        logger.info(f"Validating strategy {strategy_id[:8]}... against held-out set")

        run_result = await self._runner.run_test_set(
            entry.strategy, test_set.validation_cases
        )

        metrics = await self._evaluator.evaluate(
            entry.strategy, run_result, test_set.validation_cases
        )

        validation_score = metrics.composite_score
        discovery_score = entry.metrics.composite_score

        logger.info(
            f"Validation: discovery={discovery_score:.4f}, "
            f"validation={validation_score:.4f}"
        )

        await self._archive.promote_to_default(
            strategy_id, validation_score=validation_score
        )

    def _format_archive_context(self, entries: List[ArchiveEntry]) -> str:
        """Format top archive entries for LLM context."""
        lines = []
        for i, entry in enumerate(entries[:3]):
            lines.append(
                f"#{i+1} {entry.strategy.name} "
                f"(score={entry.metrics.composite_score:.3f}): "
                f"{entry.strategy.description}"
            )
        return "\n".join(lines)

    def _get_available_tools(self, sector: Optional[str] = None) -> List[str]:
        """Get available tool names for generation context."""
        try:
            from app.agents.langgraph.tools.registry import get_tool_registry
            registry = get_tool_registry()
            tools = registry.get_tools_for_context(
                settings.meta_agent_test_tenant_id, sector
            )
            return [t.name for t in tools]
        except Exception:
            return [
                "search_documents", "search_legislation", "get_document_content",
                "structural_query", "analyze_domain", "list_sources", "terminate",
            ]
