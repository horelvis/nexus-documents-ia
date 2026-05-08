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

    async def _resolve_labels(
        self,
        uris: set,
    ) -> dict:
        """Batch-resolve Node URIs to human-readable labels via core/label lookup.

        Returns dict mapping URI -> label. URIs without a label triple get
        a fallback: uri.split('/')[-1].replace('-', ' ').title()
        """
        if not uris:
            return {}

        label_map = {}
        try:
            query = """
                UNWIND $uris AS target_uri
                MATCH (n:Node {uri: target_uri})
                      -[:Rel {uri: 'nouxcube://predicate/core/label'}]->(l:Literal)
                RETURN n.uri AS uri, l.value AS label
            """
            rows = await self._client.execute_cypher(query, params={
                "uris": list(uris),
            })
            for row in rows:
                label_map[row["uri"]] = row["label"]
        except Exception as exc:
            logger.warning("Label resolution failed, using URI slugs: %s", exc)

        # Fallback for URIs not resolved
        for uri in uris:
            if uri not in label_map:
                label_map[uri] = uri.split("/")[-1].replace("-", " ").title()

        return label_map

    async def assemble(
        self,
        entity_uri: str,
        report_type: str,
        collection: Optional[str] = None,
    ) -> AssembledGraph:
        """Assemble graph data for a report.

        Args:
            entity_uri: Main entity URI for the report.
            report_type: Template name (entity_profile, compliance_report, contract_summary).
            collection: Optional collection scope.

        Returns:
            AssembledGraph with sections, KPIs, sources, and trust summary.
        """
        templates = _load_report_templates()

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

        # Resolve node + document labels in bulk (single FalkorDB round-trip)
        node_uris = {
            f.object for f in all_facts
            if f.object_type == "node" and f.object.startswith("nouxcube://")
        }
        all_uris_to_resolve = node_uris | all_sources
        label_map = await self._resolve_labels(all_uris_to_resolve)
        for fact in all_facts:
            if fact.object_type == "node" and fact.object in label_map:
                fact.object = label_map[fact.object]

        # Compute KPIs
        kpis: List[KPIResult] = []
        for kpi_def in kpi_defs:
            kpi_name = kpi_def.get("name", "")
            aggregation = kpi_def.get("aggregation", "count")
            filter_pred = kpi_def.get("filter_predicate", "")

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

        # Build sources list with resolved document titles
        sources: List[SourceRef] = []
        for doc_uri in all_sources:
            doc_title = label_map.get(doc_uri)
            if not doc_title:
                doc_title = doc_uri.rsplit("/", 1)[-1] if "/" in doc_uri else doc_uri
            sources.append(SourceRef(
                document_uri=doc_uri,
                document_id=doc_title,
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
