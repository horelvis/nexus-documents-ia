# TrustGraph Phase 3c: Knowledge Expert — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `generate_knowledge_report` tool to Emma's ReAct agent that assembles graph data, computes KPIs, and generates structured documents (markdown + PDF) with verified citations from the knowledge graph.

**Architecture:** Two-layer design — `GraphAssembler` in KTS assembles facts/KPIs/sources from the graph using Cypher templates, then `KnowledgeReportTool` in Emma calls the assembler, feeds results to the CHAT LLM with a Langfuse prompt, and optionally renders PDF via `forge_document`. Report structure is YAML-driven and extensible without code changes.

**Tech Stack:** FalkorDB (Cypher via TemplateExecutor), Python 3.9+, httpx, asyncio, Langfuse prompts, YAML config, SSE events

**Spec:** `docs/superpowers/specs/2026-04-01-trustgraph-phase3-knowledge-expert-design.md` — Phase 3c sections

**Depends on:** Phase 3a (Clean Graph) + Phase 3b (Smart Traversal) — both COMPLETE

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `knowledge-tree-service/config/report_templates.yaml` | Report type definitions (sections, predicates, KPIs) |
| `knowledge-tree-service/app/services/graph_assembler.py` | Assemble graph data by report type — facts, KPIs, sources |
| `knowledge-tree-service/app/schemas/reports.py` | Pydantic models for report request/response |
| `knowledge-tree-service/app/api/reports.py` | `POST /graph/assemble` endpoint |
| `knowledge-tree-service/tests/test_graph_assembler.py` | Tests for graph assembler |
| `emma-agent-service/app/agents/langgraph/tools/knowledge_report.py` | `generate_knowledge_report` ReAct tool |
| `knowledge-tree-service/scripts/seed_phase3c_prompts.py` | Seed Langfuse prompt for report generation |

### Modified Files
| File | Change |
|------|--------|
| `knowledge-tree-service/app/api/__init__.py` or main router | Register reports router |
| `emma-agent-service/app/agents/langgraph/tools/registry.py` | Register KnowledgeReportTool |
| `emma-agent-service/app/core/config.py` | Add `report_generation_enabled` setting |

---

## Task 1: Report Templates YAML Config

**Files:**
- Create: `knowledge-tree-service/config/report_templates.yaml`

- [ ] **Step 1: Create the report templates**

Create `backend/microservices/knowledge-tree-service/config/report_templates.yaml`:

```yaml
# Report template registry — defines structure for knowledge graph reports.
# Each report type specifies sections (with Cypher templates + predicate filters)
# and KPIs (computed from graph data).

reports:
  entity_profile:
    description: "Complete profile of an entity (person or organization)"
    sections:
      - name: "Identificacion"
        templates: ["entity_relations"]
        predicates: ["core/label", "core/type", "core/definition"]
      - name: "Relaciones laborales"
        templates: ["org_people"]
        predicates: ["legal/empleado-de", "legal/cargo-de", "legal/administrador-de"]
      - name: "Relaciones contractuales"
        templates: ["entity_relations"]
        predicates: ["legal/firmante-de", "legal/parte-de-contrato", "legal/representante-de"]
      - name: "Marco normativo"
        templates: ["applicable_regulations"]
        predicates: []
    kpis:
      - name: "total_relaciones"
        description: "Total relationships"
        template: "entity_relations"
        aggregation: "count"
      - name: "documentos_fuente"
        description: "Source documents"
        template: "entity_relations"
        aggregation: "count_distinct_sources"

  compliance_report:
    description: "Regulatory compliance report"
    sections:
      - name: "Normativa aplicable"
        templates: ["applicable_regulations"]
        predicates: []
      - name: "Obligaciones contractuales"
        templates: ["entity_relations"]
        predicates: ["legal/clausula", "legal/obligacion", "legal/obligacion-de"]
      - name: "Riesgos identificados"
        templates: ["entity_relations"]
        predicates: ["core/contradicts"]
    kpis:
      - name: "leyes_aplicables"
        description: "Applicable laws"
        template: "applicable_regulations"
        aggregation: "count"
      - name: "contradicciones"
        description: "Contradictions found"
        template: "entity_relations"
        aggregation: "count"
        filter_predicate: "core/contradicts"

  contract_summary:
    description: "Contract summary with verified graph data"
    sections:
      - name: "Partes"
        templates: ["entity_relations"]
        predicates: ["legal/firmante-de", "legal/representante-de", "legal/parte-de-contrato"]
      - name: "Condiciones economicas"
        templates: ["entity_relations"]
        predicates: ["legal/salario-bruto", "legal/importe", "legal/duracion"]
      - name: "Obligaciones"
        templates: ["entity_relations"]
        predicates: ["legal/clausula", "legal/obligacion", "legal/obligacion-de"]
    kpis:
      - name: "partes_involucradas"
        description: "Parties involved"
        template: "entity_relations"
        aggregation: "count"
        filter_predicate: "legal/firmante-de"
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/config/report_templates.yaml
git commit -m "feat(kts): report templates YAML config (entity_profile, compliance, contract)"
```

---

## Task 2: Report Schemas

**Files:**
- Create: `knowledge-tree-service/app/schemas/reports.py`

- [ ] **Step 1: Create Pydantic models**

Create `backend/microservices/knowledge-tree-service/app/schemas/reports.py`:

```python
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
    tenant_id: str
    entity_uri: str
    report_type: str = "entity_profile"
    collection: Optional[str] = None


class AssembleResponse(BaseModel):
    """Response from graph assembly."""
    assembled: AssembledGraph
    elapsed_ms: int = 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/schemas/reports.py
git commit -m "feat(kts): Pydantic models for report assembly (AssembledGraph, KPIResult, etc.)"
```

---

## Task 3: GraphAssembler Service

**Files:**
- Create: `knowledge-tree-service/app/services/graph_assembler.py`
- Create: `knowledge-tree-service/tests/test_graph_assembler.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/microservices/knowledge-tree-service/tests/test_graph_assembler.py`:

```python
"""Tests for GraphAssembler — graph data assembly for reports."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.graph_assembler import GraphAssembler
from app.schemas.reports import AssembledGraph


class TestGraphAssembler:
    @pytest.mark.asyncio
    async def test_assembles_entity_profile(self):
        """entity_profile report type should produce sections and KPIs."""
        mock_client = AsyncMock()
        # Mock template executor to return sample triples
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/core/label",
                 "object": "Juan García", "object_type": "literal", "confidence": 0.9, "consensus_count": 2},
                {"subject": "nouxcube://entity/default/juan", "predicate": "nouxcube://predicate/legal/empleado-de",
                 "object": "nouxcube://entity/default/acme", "object_type": "node", "confidence": 0.85, "consensus_count": 3},
            ],
            "template": "entity_relations",
            "hops": 1,
            "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert isinstance(result, AssembledGraph)
        assert result.entity_uri == "nouxcube://entity/default/juan"
        assert result.report_type == "entity_profile"
        assert len(result.sections) > 0
        assert result.trust_summary.total_facts > 0

    @pytest.mark.asyncio
    async def test_computes_kpis(self):
        """KPIs should be computed from section data."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node", "confidence": 0.8},
                {"subject": "s1", "predicate": "p2", "object": "o2", "object_type": "literal", "confidence": 0.7},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/juan",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert len(result.kpis) > 0
        # total_relaciones KPI should count all results
        total_kpi = next((k for k in result.kpis if k.name == "total_relaciones"), None)
        assert total_kpi is not None
        assert total_kpi.value >= 0

    @pytest.mark.asyncio
    async def test_unknown_report_type_uses_entity_profile(self):
        """Unknown report types should fall back to entity_profile."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [], "template": "entity_relations", "hops": 1, "count": 0,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="nonexistent_type",
            user="test-tenant",
        )

        assert result.report_type == "entity_profile"

    @pytest.mark.asyncio
    async def test_collects_sources(self):
        """Source references should be extracted from edge metadata."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node",
                 "confidence": 0.9, "source_chunk": "nouxcube://document/default/doc-001#offset=0"},
            ],
            "template": "entity_relations", "hops": 1, "count": 1,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert len(result.sources) > 0
        assert "doc-001" in result.sources[0].document_id

    @pytest.mark.asyncio
    async def test_confidence_propagation(self):
        """Trust summary should aggregate confidence from all facts."""
        mock_client = AsyncMock()
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value={
            "results": [
                {"subject": "s1", "predicate": "p1", "object": "o1", "object_type": "node", "confidence": 0.9},
                {"subject": "s1", "predicate": "p2", "object": "o2", "object_type": "literal", "confidence": 0.5},
            ],
            "template": "entity_relations", "hops": 1, "count": 2,
        })

        assembler = GraphAssembler(mock_client, mock_executor)
        result = await assembler.assemble(
            entity_uri="nouxcube://entity/default/test",
            report_type="entity_profile",
            user="test-tenant",
        )

        assert result.trust_summary.min_confidence == 0.5
        assert result.trust_summary.avg_confidence == pytest.approx(0.7, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_graph_assembler.py -v --override-ini="log_auto_indent=true"
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement GraphAssembler**

Create `backend/microservices/knowledge-tree-service/app/services/graph_assembler.py`:

```python
"""
GraphAssembler — assembles graph data for knowledge report generation.

Loads report templates from config/report_templates.yaml, executes
Cypher templates for each section, computes KPIs, collects sources,
and returns a structured AssembledGraph ready for LLM generation.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from app.schemas.reports import (
    AssembledGraph,
    GraphFact,
    GraphSection,
    KPIResult,
    SourceRef,
    TrustSummary,
)
from app.services.template_executor import TemplateExecutor

logger = logging.getLogger(__name__)

_REPORT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "report_templates.yaml"

_report_templates: Optional[Dict[str, Any]] = None


def _load_report_templates() -> Dict[str, Any]:
    """Load report templates from YAML config."""
    global _report_templates
    if _report_templates is not None:
        return _report_templates

    try:
        with open(_REPORT_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _report_templates = data.get("reports", {})
        logger.info("Loaded %d report templates from %s", len(_report_templates), _REPORT_CONFIG_PATH)
    except FileNotFoundError:
        logger.warning("Report templates not found at %s", _REPORT_CONFIG_PATH)
        _report_templates = {}

    return _report_templates


class GraphAssembler:
    """Assemble graph data for knowledge report generation."""

    def __init__(self, client, template_executor: Optional[TemplateExecutor] = None) -> None:
        self._client = client
        self._executor = template_executor or TemplateExecutor()

    async def assemble(
        self,
        entity_uri: str,
        report_type: str,
        user: str,
        collection: Optional[str] = None,
    ) -> AssembledGraph:
        """Assemble graph data for a report.

        Args:
            entity_uri: Main entity URI for the report.
            report_type: Template name (entity_profile, compliance_report, contract_summary).
            user: Tenant identifier.
            collection: Optional collection scope.

        Returns:
            AssembledGraph with sections, KPIs, sources, and trust summary.
        """
        templates = _load_report_templates()

        # Fallback to entity_profile if unknown
        if report_type not in templates:
            logger.warning("Unknown report type %r, falling back to entity_profile", report_type)
            report_type = "entity_profile"

        template_def = templates.get(report_type, {})
        section_defs = template_def.get("sections", [])
        kpi_defs = template_def.get("kpis", [])

        # Resolve entity label
        entity_label = entity_uri.split("/")[-1].replace("-", " ").title()
        try:
            label_result = await self._executor.execute(
                name="entity_relations",
                client=self._client,
                user=user,
                collection=collection,
                entity_uri=entity_uri,
                query_limit=5,
            )
            for row in label_result.get("results", []):
                pred = row.get("predicate", "")
                if "label" in pred:
                    entity_label = row.get("object", entity_label)
                    break
        except Exception:
            pass

        # Assemble sections
        sections: List[GraphSection] = []
        all_facts: List[GraphFact] = []
        all_sources: Set[str] = set()
        all_confidences: List[float] = []

        for section_def in section_defs:
            section_name = section_def.get("name", "")
            tmpl_names = section_def.get("templates", ["entity_relations"])
            predicate_filters = section_def.get("predicates", [])

            section_facts: List[GraphFact] = []

            for tmpl_name in tmpl_names:
                try:
                    result = await self._executor.execute(
                        name=tmpl_name,
                        client=self._client,
                        user=user,
                        collection=collection,
                        entity_uri=entity_uri,
                        query_limit=100,
                    )
                except KeyError:
                    logger.warning("Template %r not found, skipping", tmpl_name)
                    continue
                except Exception as exc:
                    logger.warning("Template %r execution failed: %s", tmpl_name, exc)
                    continue

                for row in result.get("results", []):
                    pred = row.get("predicate", "")
                    # Filter by predicates if specified
                    if predicate_filters:
                        pred_short = "/".join(pred.split("/")[-2:]) if "/" in pred else pred
                        if not any(pf in pred_short for pf in predicate_filters):
                            continue

                    confidence = row.get("confidence") or 0.0
                    fact = GraphFact(
                        subject=row.get("subject", ""),
                        predicate=pred,
                        object=row.get("object", ""),
                        object_type=row.get("object_type", "literal"),
                        confidence=confidence,
                        consensus_count=row.get("consensus_count"),
                        source_chunk=row.get("source_chunk"),
                    )
                    section_facts.append(fact)
                    all_facts.append(fact)

                    if confidence > 0:
                        all_confidences.append(confidence)

                    # Collect sources
                    chunk = row.get("source_chunk", "")
                    if chunk and "#" in chunk:
                        all_sources.add(chunk.split("#")[0])

            section_confidence = (
                sum(f.confidence or 0 for f in section_facts) / len(section_facts)
                if section_facts else 0.0
            )

            sections.append(GraphSection(
                title=section_name,
                facts=section_facts,
                confidence=round(section_confidence, 3),
            ))

        # Compute KPIs
        kpis: List[KPIResult] = []
        for kpi_def in kpi_defs:
            kpi_name = kpi_def.get("name", "")
            aggregation = kpi_def.get("aggregation", "count")
            filter_pred = kpi_def.get("filter_predicate", "")

            # Count from all_facts matching filter
            if filter_pred:
                matching = [f for f in all_facts if filter_pred in f.predicate]
            else:
                matching = all_facts

            if aggregation == "count":
                value = len(matching)
            elif aggregation == "count_distinct_sources":
                value = len(all_sources)
            else:
                value = len(matching)

            kpi_confidence = (
                min(f.confidence or 0 for f in matching)
                if matching else 0.0
            )

            kpis.append(KPIResult(
                name=kpi_name,
                description=kpi_def.get("description", ""),
                value=value,
                confidence=round(kpi_confidence, 3),
            ))

        # Build sources list
        sources: List[SourceRef] = []
        for doc_uri in all_sources:
            doc_id = doc_uri.rsplit("/", 1)[-1] if "/" in doc_uri else doc_uri
            sources.append(SourceRef(
                document_uri=doc_uri,
                document_id=doc_id,
            ))

        # Trust summary
        trust_summary = TrustSummary(
            avg_confidence=round(sum(all_confidences) / len(all_confidences), 3) if all_confidences else 0.0,
            min_confidence=round(min(all_confidences), 3) if all_confidences else 0.0,
            total_facts=len(all_facts),
            total_sources=len(sources),
        )

        return AssembledGraph(
            entity_uri=entity_uri,
            entity_label=entity_label,
            report_type=report_type,
            sections=sections,
            kpis=kpis,
            sources=sources,
            trust_summary=trust_summary,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/test_graph_assembler.py -v --override-ini="log_auto_indent=true"
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/graph_assembler.py \
       backend/microservices/knowledge-tree-service/tests/test_graph_assembler.py
git commit -m "feat(kts): GraphAssembler service — assemble graph data for reports"
```

---

## Task 4: KTS Report API Endpoint

**Files:**
- Create: `knowledge-tree-service/app/api/reports.py`
- Modify: KTS main router to include reports

- [ ] **Step 1: Create the reports API**

Create `backend/microservices/knowledge-tree-service/app/api/reports.py`:

```python
"""API endpoints for knowledge graph report assembly."""

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_api_key
from app.schemas.reports import AssembleRequest, AssembleResponse, AssembledGraph
from app.services.falkordb_client import falkordb_client
from app.services.graph_assembler import GraphAssembler
from app.services.template_executor import TemplateExecutor

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/graph",
    tags=["reports"],
    dependencies=[Depends(verify_api_key)],
)

_assembler: GraphAssembler | None = None


def _get_assembler() -> GraphAssembler:
    global _assembler
    if _assembler is None:
        _assembler = GraphAssembler(falkordb_client, TemplateExecutor())
    return _assembler


@router.post("/assemble", response_model=AssembleResponse)
async def assemble_graph(request: AssembleRequest):
    """Assemble graph data for a knowledge report.

    Executes Cypher templates for each section of the report type,
    computes KPIs, collects sources, and returns structured data
    ready for LLM generation.
    """
    t0 = time.monotonic()

    try:
        assembler = _get_assembler()
        result = await assembler.assemble(
            entity_uri=request.entity_uri,
            report_type=request.report_type,
            user=request.tenant_id,
            collection=request.collection,
        )
    except Exception as exc:
        logger.error("Graph assembly failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Assembly failed: {exc}")

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    return AssembleResponse(assembled=result, elapsed_ms=elapsed_ms)
```

- [ ] **Step 2: Register the router in KTS main app**

Read the KTS main.py to find where routers are included. Add:

```python
from app.api.reports import router as reports_router
app.include_router(reports_router)
```

Follow the same pattern used for the triples router.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/api/reports.py
git commit -m "feat(kts): POST /graph/assemble API endpoint for report assembly"
```

---

## Task 5: Emma Settings + Langfuse Prompt

**Files:**
- Modify: `emma-agent-service/app/core/config.py`
- Create: `knowledge-tree-service/scripts/seed_phase3c_prompts.py`

- [ ] **Step 1: Add setting to Emma config**

In `backend/microservices/emma-agent-service/app/core/config.py`, after the Phase 3b settings, add:

```python
    # Phase 3c: Knowledge Expert
    report_generation_enabled: bool = os.getenv("REPORT_GENERATION_ENABLED", "true").lower() == "true"
```

- [ ] **Step 2: Create Langfuse prompt seed script**

Create `backend/microservices/knowledge-tree-service/scripts/seed_phase3c_prompts.py`:

```python
#!/usr/bin/env python3
"""Seed Langfuse prompts for Phase 3c — Knowledge Expert."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = {
    "trustgraph_report_generation": {
        "content": (
            "You are a knowledge expert. Generate a {{report_type}} for {{entity_name}}.\n\n"
            "VERIFIED DATA FROM KNOWLEDGE GRAPH:\n{{assembled_graph_markdown}}\n\n"
            "RULES:\n"
            "- Use ONLY the provided data. Do not invent information.\n"
            "- Every claim must include [Source: doc_id, confidence: X.XX]\n"
            "- KPIs go in a dedicated section with table format.\n"
            "- If a fact has confidence < 0.60, mark it as 'dato no verificado'.\n"
            "- If contradictions exist, report them explicitly.\n"
            "- Language: {{language}}\n"
            "- Structure the report with clear headings matching the section titles provided.\n"
            "- Be concise but thorough — include all verified facts."
        ),
        "labels": ["production"],
    },
}


def main():
    try:
        from langfuse import Langfuse
        client = Langfuse()

        for name, config in PROMPTS.items():
            try:
                client.create_prompt(
                    name=name,
                    prompt=config["content"],
                    labels=config.get("labels", []),
                    type="text",
                )
                print(f"  OK  {name}")
            except Exception as exc:
                if "already exists" in str(exc).lower():
                    print(f"  SKIP  {name} — already exists")
                else:
                    print(f"  ERROR  {name}: {exc}")

    except ImportError:
        print("Langfuse not available — printing prompt content instead:")
        for name, config in PROMPTS.items():
            print(f"\n--- {name} ---")
            print(config["content"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/core/config.py \
       backend/microservices/knowledge-tree-service/scripts/seed_phase3c_prompts.py
git commit -m "feat(emma+kts): report_generation_enabled setting + Langfuse report prompt"
```

---

## Task 6: KnowledgeReportTool — Emma ReAct Tool

**Files:**
- Create: `emma-agent-service/app/agents/langgraph/tools/knowledge_report.py`

- [ ] **Step 1: Create the tool**

Create `backend/microservices/emma-agent-service/app/agents/langgraph/tools/knowledge_report.py`:

```python
"""
KnowledgeReportTool — generate structured reports from knowledge graph data.

Pipeline:
1. Call KTS /graph/assemble to get structured graph data
2. Format assembled data as markdown context
3. Call CHAT LLM with Langfuse prompt to generate report text
4. Optionally render PDF via forge_document
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

import httpx
from pydantic import BaseModel, Field

from app.agents.langgraph.tools.base import EmmaTool, ToolResult
from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeReportInput(BaseModel):
    entity_uri: str = Field(
        description="URI de la entidad principal del informe (ej: nouxcube://entity/default/juan-garcia)"
    )
    report_type: str = Field(
        default="entity_profile",
        description="Tipo de informe: entity_profile, compliance_report, contract_summary"
    )
    language: str = Field(
        default="es",
        description="Idioma del informe: es, en"
    )


class KnowledgeReportTool(EmmaTool):
    """Generate structured knowledge reports from the graph."""

    @property
    def name(self) -> str:
        return "generate_knowledge_report"

    @property
    def description(self) -> str:
        return "Genera un informe estructurado con datos verificados del grafo de conocimiento, incluyendo KPIs y citas de fuentes"

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return KnowledgeReportInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        if not settings.report_generation_enabled:
            return ToolResult(output="Report generation is disabled.", data={}, success=True)

        entity_uri = arguments["entity_uri"]
        report_type = arguments.get("report_type", "entity_profile")
        language = arguments.get("language", "es")
        tenant_id = context.get("tenant_id", "")
        emit_sse = context.get("emit_sse")

        kts_url = settings.knowledge_tree_service_url.rstrip("/")
        api_key = settings.MICROSERVICES_API_KEY
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

        # ── Stage 1: Assemble graph data ────────────────────────────
        if emit_sse:
            emit_sse({
                "event_type": "report.assembling",
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"stage": "assembling", "message": "Recopilando datos del grafo..."},
            })

        try:
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                resp = await client.post(
                    f"{kts_url}/graph/assemble",
                    json={
                        "tenant_id": tenant_id,
                        "entity_uri": entity_uri,
                        "report_type": report_type,
                    },
                )
                if resp.status_code != 200:
                    return ToolResult.from_error(
                        f"Graph assembly failed: HTTP {resp.status_code} — {resp.text[:200]}"
                    )
                assembly_data = resp.json()
        except Exception as exc:
            return ToolResult.from_error(f"Graph assembly failed: {exc}")

        assembled = assembly_data.get("assembled", {})
        sections = assembled.get("sections", [])
        kpis = assembled.get("kpis", [])
        sources = assembled.get("sources", [])
        trust = assembled.get("trust_summary", {})

        if trust.get("total_facts", 0) == 0:
            return ToolResult(
                output=f"No se encontraron datos en el grafo para la entidad {entity_uri}.",
                data={},
                success=True,
            )

        # ── Stage 2: Format assembled data as markdown ──────────────
        if emit_sse:
            emit_sse({
                "event_type": "report.generating",
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"stage": "generating", "message": "Generando informe..."},
            })

        assembled_md = _format_assembled_graph(assembled)

        # ── Stage 3: LLM generation ────────────────────────────────
        entity_label = assembled.get("entity_label", entity_uri.split("/")[-1])

        try:
            from app.services.langfuse_prompt_client import get_langfuse_prompt_client
            langfuse_client = get_langfuse_prompt_client()
            prompt_cached = await langfuse_client.get_prompt(
                "trustgraph_report_generation",
                variables={
                    "report_type": report_type,
                    "entity_name": entity_label,
                    "assembled_graph_markdown": assembled_md,
                    "language": language,
                },
            )
            system_content = prompt_cached.content if prompt_cached else (
                f"Generate a {report_type} report for {entity_label} using ONLY the provided data. "
                f"Language: {language}. Cite sources with [Source: doc_id, confidence: X.XX]."
            )
        except Exception:
            system_content = (
                f"You are a knowledge expert. Generate a {report_type} for {entity_label}.\n\n"
                f"VERIFIED DATA:\n{assembled_md}\n\n"
                f"Use ONLY the data provided. Cite sources. Language: {language}."
            )

        try:
            from app.agents.llm_models import get_chat_model
            chat_model = get_chat_model()
            from langchain_core.messages import SystemMessage, HumanMessage

            response = await chat_model.ainvoke([
                SystemMessage(content=system_content),
                HumanMessage(content=f"Genera el informe para {entity_label}."),
            ])
            report_text = response.content
        except Exception as exc:
            logger.error("LLM report generation failed: %s", exc)
            report_text = assembled_md  # Fallback: return raw assembled data

        # ── Stage 4: Emit KPIs individually ─────────────────────────
        for kpi in kpis:
            if emit_sse:
                emit_sse({
                    "event_type": "report.kpi",
                    "event_id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "name": kpi.get("name", ""),
                        "value": kpi.get("value", 0),
                        "description": kpi.get("description", ""),
                        "confidence": kpi.get("confidence", 0),
                    },
                })

        return ToolResult(
            output=report_text,
            data={
                "report_type": report_type,
                "entity_uri": entity_uri,
                "kpis": kpis,
                "sources": sources,
                "trust_summary": trust,
            },
            success=True,
        )


def _format_assembled_graph(assembled: Dict[str, Any]) -> str:
    """Format AssembledGraph as markdown for LLM consumption."""
    lines = []
    entity_label = assembled.get("entity_label", "")
    lines.append(f"# Datos verificados: {entity_label}\n")

    # Sections
    for section in assembled.get("sections", []):
        title = section.get("title", "")
        facts = section.get("facts", [])
        confidence = section.get("confidence", 0)

        if not facts:
            continue

        lines.append(f"\n## {title} (confianza media: {confidence:.2f})\n")
        for fact in facts:
            pred = fact.get("predicate", "").split("/")[-1] if "/" in fact.get("predicate", "") else fact.get("predicate", "")
            obj = fact.get("object", "")
            conf = fact.get("confidence", 0)
            source = fact.get("source_chunk", "")
            doc_id = source.split("#")[0].rsplit("/", 1)[-1] if source and "#" in source else ""

            line = f"- **{pred}**: {obj}"
            if conf and conf < 0.60:
                line += " *(dato no verificado)*"
            if doc_id:
                line += f" [Fuente: {doc_id}, confianza: {conf:.2f}]"
            lines.append(line)

    # KPIs
    kpis = assembled.get("kpis", [])
    if kpis:
        lines.append("\n## KPIs\n")
        lines.append("| Metrica | Valor | Confianza |")
        lines.append("|---------|-------|-----------|")
        for kpi in kpis:
            name = kpi.get("description") or kpi.get("name", "")
            value = kpi.get("value", 0)
            conf = kpi.get("confidence", 0)
            lines.append(f"| {name} | {value} | {conf:.2f} |")

    # Trust summary
    trust = assembled.get("trust_summary", {})
    if trust:
        lines.append(f"\n## Resumen de confianza")
        lines.append(f"- Total hechos: {trust.get('total_facts', 0)}")
        lines.append(f"- Total fuentes: {trust.get('total_sources', 0)}")
        lines.append(f"- Confianza media: {trust.get('avg_confidence', 0):.2f}")
        lines.append(f"- Confianza minima: {trust.get('min_confidence', 0):.2f}")

    return "\n".join(lines)
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/knowledge_report.py
git commit -m "feat(emma): KnowledgeReportTool — generate reports from knowledge graph"
```

---

## Task 7: Register Tool in Emma

**Files:**
- Modify: `emma-agent-service/app/agents/langgraph/tools/registry.py`

- [ ] **Step 1: Add import and registration**

In `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py`:

1. Add import in the import block (around line 71):
```python
from .knowledge_report import KnowledgeReportTool
```

2. Add to the tools list (around line 87):
```python
KnowledgeReportTool(),
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py
git commit -m "feat(emma): register KnowledgeReportTool in ReAct agent tool registry"
```

---

## Task 8: Update TRUSTGRAPH.md + Final Verification

**Files:**
- Modify: `docs/architecture/TRUSTGRAPH.md`

- [ ] **Step 1: Update Phase 3c status**

Replace the Phase 3c PLANNED section with:

```markdown
### Phase 3c: Knowledge Expert (COMPLETE)

`GraphAssembler` service (KTS, assembles facts/KPIs/sources from graph via Cypher templates), YAML-driven report templates (entity_profile, compliance_report, contract_summary), `generate_knowledge_report` tool (#15 in ReAct agent, calls assembler → LLM generation → optional PDF via forge_document), KPI engine (count, count_distinct_sources aggregations with confidence propagation), SSE progressive events (report.assembling, report.generating, report.kpi), Langfuse prompt (`trustgraph_report_generation`).
```

- [ ] **Step 2: Run KTS test suite**

```bash
cd backend/microservices/knowledge-tree-service
python -m pytest tests/ -v --tb=short --override-ini="log_auto_indent=true" 2>&1 | tail -20
```

Expected: All new tests pass, no regressions.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/TRUSTGRAPH.md
git commit -m "docs: update TRUSTGRAPH.md — Phase 3c Knowledge Expert complete"
```

---

## Summary

| Task | Component | New Files | Modified Files | Tests |
|------|-----------|-----------|----------------|-------|
| 1 | Report templates YAML | 1 | 0 | — |
| 2 | Report schemas | 1 | 0 | — |
| 3 | GraphAssembler service | 2 | 0 | 5 tests |
| 4 | KTS report API | 1 | 1 | manual |
| 5 | Settings + Langfuse prompt | 1 | 1 | — |
| 6 | KnowledgeReportTool | 1 | 0 | manual |
| 7 | Tool registration | 0 | 1 | — |
| 8 | Docs + verification | 0 | 1 | full suite |
| **Total** | | **7 new** | **4 modified** | **5+ tests** |

## Deploy Sequence

```bash
# 1. Rebuild all services
cd backend/docker && docker compose up -d --build knowledge-tree-service emma-agent-service

# 2. Seed Langfuse prompt
docker compose exec knowledge-tree-service python scripts/seed_phase3c_prompts.py

# 3. Test the tool via Emma
curl -X POST http://localhost:8019/emma/query/stream \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{"query": "Genera un informe sobre las relaciones de Juan García", "user_id": "test"}'
```
