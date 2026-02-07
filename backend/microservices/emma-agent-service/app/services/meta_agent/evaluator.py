"""
Meta Agent Evaluator — LLM-as-judge + metric scoring.

Follows the InsightEvaluator pattern: Langfuse prompt → LLM Router → JSON parsing.

Three scoring dimensions from LLM judge:
- answer_quality (0-1): Correctness, completeness, structure
- source_accuracy (0-1): Are cited sources real and relevant?
- instruction_following (0-1): Did it address the intent?

Three computed dimensions:
- efficiency: Inverse of (total_calls * latency)
- success_rate: Fraction of cases that completed without error
- novelty_bonus: Structural code diversity vs archive
"""

from __future__ import annotations

import ast
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from app.core.config import settings
from .schemas import (
    ArchiveEntry,
    CaseResult,
    EvaluationMetrics,
    RunResult,
    StrategyCandidate,
    TestCase,
)

logger = logging.getLogger(__name__)

# Max chars of answer to send to the judge (avoid huge prompts)
MAX_ANSWER_FOR_JUDGE = 2000
MAX_REFERENCE_FOR_JUDGE = 1000


class StrategyEvaluator:
    """Evaluates strategy quality via LLM judge + computed metrics."""

    async def evaluate(
        self,
        strategy: StrategyCandidate,
        run_result: RunResult,
        test_cases: List[TestCase],
        archive_top: Optional[List[ArchiveEntry]] = None,
    ) -> EvaluationMetrics:
        """Score a strategy based on its run results.

        Args:
            strategy: The strategy being evaluated
            run_result: Execution results from the runner
            test_cases: The test cases used (for reference answers)
            archive_top: Top strategies in archive (for novelty comparison)

        Returns:
            Complete EvaluationMetrics with composite score
        """
        metrics = EvaluationMetrics()

        # ─── LLM-judged metrics ──────────────────────────────────────────
        judge_scores = await self._llm_judge(strategy, run_result, test_cases)
        metrics.answer_quality = judge_scores.get("answer_quality", 0.5)
        metrics.source_accuracy = judge_scores.get("source_accuracy", 0.5)
        metrics.instruction_following = judge_scores.get("instruction_following", 0.5)
        metrics.judge_reasoning = judge_scores.get("reasoning", "")

        # ─── Computed metrics ────────────────────────────────────────────
        metrics.success_rate = run_result.success_rate
        metrics.efficiency = self._compute_efficiency(run_result)
        metrics.novelty_bonus = self._compute_novelty(strategy, archive_top)

        # ─── Diagnostics ────────────────────────────────────────────────
        metrics.total_llm_calls = run_result.total_llm_calls
        metrics.total_tool_calls = run_result.total_tool_calls
        metrics.avg_latency_s = run_result.avg_latency

        # ─── Composite ──────────────────────────────────────────────────
        metrics.compute_composite()

        logger.info(
            f"Evaluated strategy {strategy.id[:8]}... "
            f"composite={metrics.composite_score:.4f} "
            f"quality={metrics.answer_quality:.2f} "
            f"efficiency={metrics.efficiency:.2f} "
            f"success={metrics.success_rate:.2f}"
        )

        return metrics

    # ─── LLM Judge ───────────────────────────────────────────────────────────

    async def _llm_judge(
        self,
        strategy: StrategyCandidate,
        run_result: RunResult,
        test_cases: List[TestCase],
    ) -> Dict[str, Any]:
        """Use strong LLM to judge answer quality."""
        # Build examples from successful cases
        examples = []
        for i, case_result in enumerate(run_result.case_results):
            if not case_result.success or i >= len(test_cases):
                continue
            tc = test_cases[i]
            sources = case_result.sources if isinstance(case_result.sources, list) else []
            examples.append({
                "query": tc.query,
                "answer": case_result.answer[:MAX_ANSWER_FOR_JUDGE],
                "sources_count": len(sources),
                "reference": (tc.reference_answer or "")[:MAX_REFERENCE_FOR_JUDGE],
            })

        if not examples:
            return {"answer_quality": 0.0, "source_accuracy": 0.0,
                    "instruction_following": 0.0, "reasoning": "No successful cases"}

        # Get judge prompt (Langfuse with YAML fallback)
        system_prompt = await self._get_judge_prompt()

        examples_text = "\n\n".join(
            f"--- Caso {i+1} ---\n"
            f"Consulta: {ex['query']}\n"
            f"Respuesta: {ex['answer']}\n"
            f"Fuentes citadas: {ex['sources_count']}\n"
            f"Referencia: {ex.get('reference', 'N/A')}"
            for i, ex in enumerate(examples[:5])
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"Estrategia: {strategy.name}\n"
                f"Intención objetivo: {strategy.intent_target}\n\n"
                f"Casos evaluados:\n{examples_text}\n\n"
                f"Responde SOLO con JSON."
            )},
        ]

        try:
            from app.agents.llm_router import get_llm_router
            router = await get_llm_router()

            # Retry up to 2 times on empty responses
            text = ""
            for attempt in range(2):
                response = await router.chat(
                    messages=messages,
                    provider_override="openrouter",
                    temperature=0.1,
                    max_tokens=512,
                )

                # Try content first, then thinking (Qwen3 sometimes puts
                # analytical responses entirely in <think> tags)
                text = response.content
                if not text and hasattr(response, "thinking") and response.thinking:
                    text = response.thinking

                if text:
                    break
                logger.debug(f"Empty judge response (attempt {attempt+1}/2), retrying...")

            scores = self._extract_json(text)
            if scores is None:
                logger.warning(
                    f"LLM judge returned non-JSON. "
                    f"Content: {response.content[:100]} | "
                    f"Thinking: {(getattr(response, 'thinking', '') or '')[:100]}"
                )
                raise ValueError("Could not extract JSON from judge response")

            return {
                "answer_quality": float(scores.get("answer_quality", 0.5)),
                "source_accuracy": float(scores.get("source_accuracy", 0.5)),
                "instruction_following": float(scores.get("instruction_following", 0.5)),
                "reasoning": str(scores.get("reasoning", "")),
            }

        except Exception as e:
            logger.warning(f"LLM judge failed, using defaults: {e}")
            return {"answer_quality": 0.5, "source_accuracy": 0.5,
                    "instruction_following": 0.5, "reasoning": f"Judge error: {e}"}

    async def _get_judge_prompt(self) -> str:
        """Get judge system prompt from Langfuse (with YAML fallback)."""
        try:
            from app.services.langfuse_prompt_client import get_langfuse_prompt_client
            client = get_langfuse_prompt_client()
            prompt = await client.get_prompt("emma_meta_judge")
            if prompt:
                return prompt.content
        except Exception as e:
            logger.debug(f"Langfuse prompt fetch failed: {e}")

        return (
            "Evalúa la respuesta del agente Emma a la consulta del usuario.\n"
            "Puntúa cada dimensión de 0.0 a 1.0:\n\n"
            "1. answer_quality: ¿La respuesta es correcta, completa y bien estructurada?\n"
            "2. source_accuracy: ¿Las fuentes citadas son reales y relevantes?\n"
            "3. instruction_following: ¿Responde exactamente a lo que se preguntó?\n\n"
            "Responde SOLO con JSON: "
            '{"answer_quality": 0.X, "source_accuracy": 0.X, '
            '"instruction_following": 0.X, "reasoning": "..."}'
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response, handling various formats.

        Handles:
        - <think>...</think> prefixed content (Qwen3 thinking mode)
        - Markdown ```json blocks
        - Raw JSON
        - JSON embedded in explanatory text
        """
        # Strip Qwen3 thinking tags
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Try markdown code blocks
        md_match = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find JSON object directly
        json_match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try the full cleaned content
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        return None

    # ─── Computed Metrics ────────────────────────────────────────────────────

    def _compute_efficiency(self, run_result: RunResult) -> float:
        """Compute efficiency score based on resource usage.

        Formula: 1.0 - min(1.0, (total_calls * avg_latency) / budget)
        Where budget = 30 calls * 60 seconds = 1800
        """
        successful = [c for c in run_result.case_results if c.success]
        if not successful:
            return 0.0

        total_calls = sum(c.llm_calls + c.tool_calls for c in successful)
        avg_latency = sum(c.latency_s for c in successful) / len(successful)

        budget = 30 * 60  # 30 calls * 60 seconds
        usage = total_calls * avg_latency
        return round(1.0 - min(1.0, usage / budget), 4)

    def _compute_novelty(
        self,
        strategy: StrategyCandidate,
        archive_top: Optional[List[ArchiveEntry]] = None,
    ) -> float:
        """Compute novelty bonus based on structural code diversity.

        Compares the set of tool names used and AST structure depth
        against top-5 archive entries.
        """
        if not archive_top:
            return 0.5  # No archive → neutral novelty

        try:
            candidate_features = self._extract_code_features(strategy.code)
        except Exception:
            return 0.3

        similarities = []
        for entry in archive_top[:5]:
            try:
                archive_features = self._extract_code_features(entry.strategy.code)
                sim = self._feature_similarity(candidate_features, archive_features)
                similarities.append(sim)
            except Exception:
                continue

        if not similarities:
            return 0.5

        avg_similarity = sum(similarities) / len(similarities)
        # Novelty = inverse of average similarity
        return round(max(0.0, min(1.0, 1.0 - avg_similarity)), 4)

    def _extract_code_features(self, code: str) -> Dict[str, Any]:
        """Extract structural features from code for novelty comparison."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"tools": set(), "depth": 0, "calls": 0}

        tools: Set[str] = set()
        max_depth = 0
        call_count = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_count += 1
                # Detect ctx.tools.execute("tool_name", ...) calls
                if (isinstance(node.func, ast.Attribute)
                        and node.func.attr == "execute"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    tools.add(str(node.args[0].value))

        # Approximate depth via nested control flow
        def _depth(n: ast.AST, d: int = 0) -> int:
            md = d
            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.For, ast.While, ast.If, ast.AsyncFor)):
                    md = max(md, _depth(child, d + 1))
                else:
                    md = max(md, _depth(child, d))
            return md

        max_depth = _depth(tree)

        return {"tools": tools, "depth": max_depth, "calls": call_count}

    def _feature_similarity(
        self, a: Dict[str, Any], b: Dict[str, Any]
    ) -> float:
        """Compute similarity between two code feature sets (0-1)."""
        # Jaccard similarity of tool sets
        tools_a = a.get("tools", set())
        tools_b = b.get("tools", set())
        if tools_a or tools_b:
            jaccard = len(tools_a & tools_b) / len(tools_a | tools_b)
        else:
            jaccard = 1.0

        # Depth similarity
        da = a.get("depth", 0)
        db = b.get("depth", 0)
        depth_sim = 1.0 - abs(da - db) / max(da, db, 1)

        # Call count similarity
        ca = a.get("calls", 0)
        cb = b.get("calls", 0)
        call_sim = 1.0 - abs(ca - cb) / max(ca, cb, 1)

        return (jaccard * 0.5 + depth_sim * 0.25 + call_sim * 0.25)
