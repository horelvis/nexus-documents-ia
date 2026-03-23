"""
Multi-Pipeline RAG Sectors

Sector-based configuration layer for domain-specific RAG pipelines.
Each sector (legal, medical, documental) configures:
- Which agents are active
- Hybrid search alpha and top_k
- Chunk strategy and sizes
- Entity extraction patterns
- Graph schema for FalkorDB knowledge graph
- System prompts

Usage:
    from app.agents.langgraph.sectors import get_active_sector_config

    sector_config = get_active_sector_config()
    if sector_config:
        # Sector-specific behavior
        alpha = sector_config.hybrid_alpha
    else:
        # Generic mode (no sector configured)
        alpha = 0.7
"""

from .config import Sector, SectorConfig
from .registry import get_active_sector_config, SECTOR_CONFIGS

__all__ = [
    "Sector",
    "SectorConfig",
    "get_active_sector_config",
    "SECTOR_CONFIGS",
]
