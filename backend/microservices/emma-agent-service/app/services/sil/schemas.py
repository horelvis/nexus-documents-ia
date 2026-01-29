"""
SIL Schemas for Emma Agent Service.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class ReasoningType(str, Enum):
    """Types of reasoning in SIL"""
    GRAPH_ONLY = "graph_only"
    VECTOR_ONLY = "vector_only"
    HYBRID = "hybrid"
    DIRECT = "direct"
    ERROR = "error"


@dataclass
class SILResult:
    """Result from SIL processing"""
    reasoning_type: ReasoningType
    context: str
    data: Dict[str, Any]
    confidence: float
    metadata: Dict[str, Any]

    @property
    def is_structural(self) -> bool:
        """Check if result is from structural query"""
        return self.reasoning_type == ReasoningType.GRAPH_ONLY

    @property
    def is_content(self) -> bool:
        """Check if result requires content retrieval"""
        return self.reasoning_type in (ReasoningType.VECTOR_ONLY, ReasoningType.HYBRID)
