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
            report_text = assembled_md

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

    trust = assembled.get("trust_summary", {})
    if trust:
        lines.append(f"\n## Resumen de confianza")
        lines.append(f"- Total hechos: {trust.get('total_facts', 0)}")
        lines.append(f"- Total fuentes: {trust.get('total_sources', 0)}")
        lines.append(f"- Confianza media: {trust.get('avg_confidence', 0):.2f}")
        lines.append(f"- Confianza minima: {trust.get('min_confidence', 0):.2f}")

    return "\n".join(lines)
