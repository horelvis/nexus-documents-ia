"""Pydantic models for knowledge graph report assembly."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GraphFact(BaseModel):
    """A single fact from the knowledge graph."""
    subject: str
    predicate: str
    object: str
    object_type: str = "literal"
    confidence: Optional[float] = None
    consensus_count: Optional[int] = None
    source_chunk: Optional[str] = None


class GraphSection(BaseModel):
    """A thematic section of a report."""
    title: str
    facts: List[GraphFact] = Field(default_factory=list)
    confidence: float = 0.0


class KPIResult(BaseModel):
    """A computed KPI from graph data."""
    name: str
    description: str = ""
    value: Any = 0
    confidence: float = 0.0


class SourceRef(BaseModel):
    """A source document reference."""
    document_uri: str
    document_id: str = ""
    chunk_offset: int = 0
    confidence: Optional[float] = None


class TrustSummary(BaseModel):
    """Aggregated trust metrics."""
    avg_confidence: float = 0.0
    avg_authority: float = 0.0
    min_confidence: float = 0.0
    total_facts: int = 0
    total_sources: int = 0


class AssembledGraph(BaseModel):
    """Complete assembled graph data for report generation."""
    entity_uri: str
    entity_label: str = ""
    report_type: str
    sections: List[GraphSection] = Field(default_factory=list)
    kpis: List[KPIResult] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)
    trust_summary: TrustSummary = Field(default_factory=TrustSummary)


class AssembleRequest(BaseModel):
    """Request to assemble graph data for a report."""
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    entity_uri: str
    report_type: str = "entity_profile"
    collection: Optional[str] = None


class AssembleResponse(BaseModel):
    """Response from graph assembly."""
    assembled: AssembledGraph
    elapsed_ms: int = 0
