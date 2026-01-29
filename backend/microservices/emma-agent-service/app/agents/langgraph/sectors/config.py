"""
Sector Configuration Dataclass and Enum

Defines the structure of a sector configuration, which controls
how the RAG pipeline behaves for a specific domain deployment.

A sector is set once via ACTIVE_SECTOR env var before data ingestion.
Changing sectors requires clearing all data (Weaviate + AGE graph).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Sector(str, Enum):
    """Available deployment sectors."""
    LEGAL = "legal"
    MEDICAL = "medical"
    DOCUMENTAL = "documental"


@dataclass(frozen=True)
class SectorConfig:
    """
    Configuration for a specific deployment sector.

    Controls RAG pipeline parameters, agent selection, entity extraction,
    and graph schema for the active sector.

    Attributes:
        name: Human-readable sector name
        sector: Sector enum value
        agents: List of agent names active in this sector
        default_agent: Fallback agent when plan is empty
        hybrid_alpha: Weaviate hybrid search alpha (0=keyword, 1=semantic)
        top_k: Number of documents to retrieve
        rerank_enabled: Whether to apply cross-encoder reranking
        chunk_strategy: Chunking strategy (semantic, legal_sections, paragraph)
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        entity_patterns: Regex patterns for entity extraction by type
        graph_name: Apache AGE graph name
        graph_schema: Path to Cypher schema file
        system_prompt_key: Key in emma_prompts.yaml for sector system prompt
        collection_suffix: Optional suffix for Weaviate collection names
        men_domain: MEN service domain mapping
    """
    name: str
    sector: Sector
    agents: List[str]
    default_agent: str
    hybrid_alpha: float
    top_k: int
    rerank_enabled: bool
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    entity_patterns: Dict[str, List[str]]
    graph_name: str
    graph_schema: str
    system_prompt_key: str
    collection_suffix: Optional[str] = None
    men_domain: str = "general"
