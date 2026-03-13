"""
StopAndGoStrategy — Protocol + registry for mode-specific behavior.

The graph nodes are generic — they delegate mode-specific logic to
the strategy. Each mode (predictive / verified) registers a strategy
at import time.

Usage:
    from .strategy import get_strategy, register_strategy

    register_strategy("predictive", PredictiveStrategy())

    # Inside a node:
    strategy = get_strategy(state["mode"])
    item = await strategy.extract_item(state, state["source_context"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import StopAndGoState


@runtime_checkable
class StopAndGoStrategy(Protocol):
    """Protocol that defines mode-specific behavior for the stop-and-go graph."""

    @property
    def mode(self) -> str:
        """'predictive' or 'verified'"""
        ...

    async def initialize(self, state: "StopAndGoState") -> None:
        """Initialize any lazy resources (cache connections, agents)."""
        ...

    async def extract_item(
        self,
        state: "StopAndGoState",
        source_context: str,
    ) -> Dict[str, Any]:
        """
        Extract next item (factor or claim).

        Returns item dict with at least 'id', 'text', 'type'.
        May include 'event_data' for SSE emission.
        """
        ...

    async def evaluate_item(
        self,
        item: Dict[str, Any],
        evidence: Any,
        state: "StopAndGoState",
    ) -> Dict[str, Any]:
        """
        Evaluate item against evidence.

        Args:
            evidence: Either Dict[str, List[Dict]] with "source" and "external"
                      tiers (verified mode), or a flat List[Dict] (legacy).
                      Strategies that don't need tiers should flatten internally.

        Returns dict with:
            'status': 'accepted' | 'rejected' | 'corrected'
            'confidence': float
            plus mode-specific data
        """
        ...

    def is_duplicate(self, item: Dict[str, Any], state: "StopAndGoState") -> bool:
        """Check if item duplicates a previous one."""
        ...

    async def check_completion(
        self,
        state: "StopAndGoState",
        source_context: str,
    ) -> bool:
        """LLM-based check: are we done extracting?"""
        ...

    async def on_accepted(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: "StopAndGoState",
    ) -> Dict[str, Any]:
        """Handle accepted item — cache to Redis, return SSE event dict."""
        ...

    async def on_rejected(
        self,
        item: Dict[str, Any],
        evaluation: Dict[str, Any],
        state: "StopAndGoState",
    ) -> Dict[str, Any]:
        """Handle rejected item — return SSE event dict."""
        ...

    async def synthesize(self, state: "StopAndGoState") -> Dict[str, Any]:
        """Final synthesis — probability or document assembly. Returns result dict."""
        ...


# =============================================================================
# Strategy Registry
# =============================================================================

_strategies: Dict[str, StopAndGoStrategy] = {}


def register_strategy(mode: str, strategy: StopAndGoStrategy) -> None:
    """Register a strategy for a mode."""
    _strategies[mode] = strategy


def get_strategy(mode: str) -> StopAndGoStrategy:
    """Get the registered strategy for a mode."""
    if mode not in _strategies:
        raise ValueError(
            f"Unknown stop-and-go mode: {mode!r}. "
            f"Available: {list(_strategies.keys())}"
        )
    return _strategies[mode]
