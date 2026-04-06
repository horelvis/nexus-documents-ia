"""
Unified RAG Configuration

Single configuration for all domains — the knowledge graph provides
dynamic per-query context. Static sector selection is no longer used.

Usage:
    from app.agents.langgraph.sectors import get_active_sector_config

    config = get_active_sector_config()  # Always returns unified config
    alpha = config.hybrid_alpha  # 0.6 (balanced)
"""

from .config import SectorConfig, UNIFIED_ENTITY_PATTERNS
from .registry import get_active_sector_config, SECTOR_CONFIGS

__all__ = [
    "SectorConfig",
    "UNIFIED_ENTITY_PATTERNS",
    "get_active_sector_config",
    "SECTOR_CONFIGS",
]
