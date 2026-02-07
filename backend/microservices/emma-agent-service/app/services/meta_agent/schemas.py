"""
Meta Agent Data Models

Defines the core schemas for the ADAS-inspired meta agent system:
- StrategyCandidate: What the meta agent generates (forward() code)
- AgentResult: What forward() returns
- EvaluationMetrics: How strategies are scored
- ArchiveEntry: Strategy + metrics stored in Redis
- TestCase/TestSet: Curated evaluation data
- CaseResult/RunResult: Execution results from the runner
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# What forward() returns
# =============================================================================

@dataclass
class AgentResult:
    """Result from a generated forward() function.

    This is the interface between generated strategies and the rest of Emma.
    forward() MUST return an AgentResult.
    """
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# What the meta agent generates
# =============================================================================

class StrategyCandidate(BaseModel):
    """A generated strategy — Python source code for async def forward()."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(description="Human-readable name (LLM-generated)")
    code: str = Field(description="Python source of async def forward(query, ctx)")
    intent_target: str = Field(
        description="Target intent: document_query, legislation, analysis, "
                    "count_list, comparison, generation, general"
    )
    sector_target: Optional[str] = Field(
        default=None,
        description="Optional sector specialization (legal, medical, documental)"
    )
    description: str = Field(default="", description="LLM-generated explanation")
    parent_id: Optional[str] = Field(
        default=None,
        description="Strategy this was derived from (mutation/crossover)"
    )
    generation: int = Field(default=0, description="Search iteration number")
    code_hash: str = Field(default="", description="SHA-256 of code for dedup")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def model_post_init(self, __context: Any) -> None:
        if not self.code_hash and self.code:
            self.code_hash = hashlib.sha256(self.code.strip().encode()).hexdigest()


# =============================================================================
# How strategies are scored
# =============================================================================

# Weights for composite score calculation
METRIC_WEIGHTS = {
    "answer_quality": 0.30,
    "source_accuracy": 0.20,
    "instruction_following": 0.15,
    "efficiency": 0.15,
    "success_rate": 0.15,
    "novelty_bonus": 0.05,
}


class EvaluationMetrics(BaseModel):
    """Scores for a strategy (0.0-1.0 each)."""

    answer_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    source_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    instruction_following: float = Field(default=0.0, ge=0.0, le=1.0)
    efficiency: float = Field(default=0.0, ge=0.0, le=1.0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty_bonus: float = Field(default=0.0, ge=0.0, le=1.0)
    composite_score: float = Field(default=0.0, ge=0.0, le=1.0)

    # Diagnostic fields (not scored)
    total_llm_calls: int = 0
    total_tool_calls: int = 0
    avg_latency_s: float = 0.0
    judge_reasoning: str = ""

    def compute_composite(self) -> float:
        """Calculate weighted composite score from individual metrics."""
        score = sum(
            getattr(self, metric) * weight
            for metric, weight in METRIC_WEIGHTS.items()
        )
        self.composite_score = round(min(1.0, max(0.0, score)), 4)
        return self.composite_score


# =============================================================================
# Archive entry (strategy + metrics in Redis)
# =============================================================================

class ArchiveEntry(BaseModel):
    """A strategy stored in the archive with its evaluation metrics."""

    strategy: StrategyCandidate
    metrics: EvaluationMetrics
    test_set_id: str = ""
    sample_count: int = 0
    production_uses: int = 0
    production_thumbs_up: int = 0
    production_thumbs_down: int = 0
    production_avg_latency_s: float = 0.0
    is_active: bool = True
    is_default: bool = False
    promoted_at: Optional[str] = None


# =============================================================================
# Test cases for strategy evaluation
# =============================================================================

class TestCase(BaseModel):
    """A single test case for evaluating strategies."""

    query: str
    intent: str
    sector: Optional[str] = None
    expected_tools: Optional[List[str]] = None
    reference_answer: Optional[str] = None
    difficulty: str = "medium"


class TestSet(BaseModel):
    """Collection of test cases split into discovery and validation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    intent: str
    sector: Optional[str] = None
    discovery_cases: List[TestCase] = Field(default_factory=list)
    validation_cases: List[TestCase] = Field(default_factory=list)


# =============================================================================
# Execution results
# =============================================================================

@dataclass
class CaseResult:
    """Result of running a strategy against a single test case."""

    success: bool
    answer: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    latency_s: float = 0.0
    reasoning_steps: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RunResult:
    """Result of running a strategy against a full test set."""

    strategy_id: str
    case_results: List[CaseResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for c in self.case_results if c.success) / len(self.case_results)

    @property
    def avg_latency(self) -> float:
        successful = [c for c in self.case_results if c.success]
        if not successful:
            return 0.0
        return sum(c.latency_s for c in successful) / len(successful)

    @property
    def total_llm_calls(self) -> int:
        return sum(c.llm_calls for c in self.case_results if c.success)

    @property
    def total_tool_calls(self) -> int:
        return sum(c.tool_calls for c in self.case_results if c.success)


# =============================================================================
# Search loop tracking
# =============================================================================

class SearchIteration(BaseModel):
    """Record of a single search loop iteration."""

    iteration: int
    candidates_generated: int
    candidates_valid: int
    best_score: float
    best_strategy_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SearchJob(BaseModel):
    """A search loop job."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent_target: str
    sector_target: Optional[str] = None
    test_set_id: str
    max_iterations: int = 10
    candidates_per_iteration: int = 3
    status: str = "pending"  # pending, running, completed, failed
    iterations: List[SearchIteration] = Field(default_factory=list)
    best_strategy_id: Optional[str] = None
    best_score: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
