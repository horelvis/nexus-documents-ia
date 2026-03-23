"""REMOVED: Few-shot retrieval has been eliminated from the stack.

pgvector was the only backend for few-shot examples and has been removed.
This stub is kept so stale imports do not crash at import time.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class FewShotExample:
    """Stub — kept for type compatibility with prompt_composer."""
    id: UUID
    question: str
    answer: str
    category: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[List[str]] = None
    quality_score: float = 1.0
    similarity_score: float = 0.0


class FewShotRetriever:
    """No-op retriever. All methods return empty results."""

    async def search(self, query: str, **kwargs) -> List[FewShotExample]:
        return []

    async def add_example(self, question: str, answer: str, **kwargs) -> Optional[UUID]:
        return None

    async def update_usage(self, example_id: UUID) -> None:
        pass

    async def submit_feedback(self, example_id: UUID, is_positive: bool) -> None:
        pass

    def format_for_prompt(self, examples: List[FewShotExample], format_type: str = "qa") -> str:
        return ""

    async def close(self) -> None:
        pass


_retriever: Optional[FewShotRetriever] = None


def get_few_shot_retriever() -> FewShotRetriever:
    """Get the singleton FewShotRetriever instance (no-op stub)."""
    global _retriever
    if _retriever is None:
        _retriever = FewShotRetriever()
    return _retriever
