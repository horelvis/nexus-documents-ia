"""Insight Evaluator — LLM-based context analysis for proactive insights.

Uses the configured LLM (via LLM Router with provider fallback) to evaluate
tenant context and generate actionable insights. The system prompt is fetched
from Langfuse (with YAML fallback), enabling dynamic insight type management
without code changes.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.schemas.heartbeat import (
    InsightUrgency,
    LLMEvaluationResult,
    LLMInsightCandidate,
    ProactiveInsightCreate,
    SuggestedAction,
    TenantContext,
)

logger = logging.getLogger(__name__)

URGENCY_MAP = {
    "critical": InsightUrgency.CRITICAL,
    "high": InsightUrgency.HIGH,
    "medium": InsightUrgency.MEDIUM,
    "low": InsightUrgency.LOW,
}


class InsightEvaluator:
    """Evaluates tenant context using LLM to generate proactive insights.

    The system prompt is fetched from Langfuse (prompt name:
    'emma_heartbeat_evaluator') with a YAML fallback from
    emma_prompts.yaml → heartbeat.evaluation_system.

    New insight types can be added by editing the prompt in Langfuse UI
    without modifying Python code or redeploying.
    """

    async def _get_system_prompt(self) -> str:
        """Fetch the evaluation system prompt from Langfuse (or YAML fallback)."""
        try:
            from app.services.langfuse_prompt_client import get_langfuse_prompt_client

            client = get_langfuse_prompt_client()
            cached = await client.get_prompt("emma_heartbeat_evaluator")
            if cached and cached.content:
                return cached.content
        except Exception as e:
            logger.warning(f"Failed to fetch Langfuse prompt: {e}")

        # Hardcoded fallback (matches emma_prompts.yaml heartbeat.evaluation_system)
        return self._fallback_system_prompt()

    def _fallback_system_prompt(self) -> str:
        """Fallback system prompt when Langfuse and YAML are both unavailable."""
        return """Eres Emma, un asistente de IA especializado en gestión documental legal.

Tu tarea es analizar el contexto de un tenant y generar insights proactivos que sean:
1. ACCIONABLES: El usuario debe poder tomar una acción concreta
2. RELEVANTES: Solo genera insights si hay algo importante que comunicar
3. PRIORIZADOS: Asigna urgencia basada en el impacto real

TIPOS DE INSIGHTS VÁLIDOS:
- contract_expiration: Contratos próximos a vencer
- compliance_alert: Gaps de cumplimiento normativo detectados
- risk_alert: Riesgos identificados en documentos
- anomaly_detected: Duplicados, fallos de indexación, patrones inusuales
- task_reminder: Análisis o firmas pendientes por mucho tiempo
- activity_summary: Resumen de actividad (solo si hay datos significativos)

NIVELES DE URGENCIA:
- critical: Requiere acción inmediata (vencimiento en <3 días, riesgo grave)
- high: Debe atenderse hoy (vencimiento en <7 días)
- medium: Atender esta semana
- low: Informativo

REGLAS:
- Si no hay nada relevante, devuelve {"no_action_needed": true}
- Máximo 3-4 insights por evaluación
- Prioriza calidad sobre cantidad
- Sé específico en títulos y resúmenes
- Incluye document IDs relacionados cuando aplique

FORMATO DE RESPUESTA (JSON):
{
  "insights": [
    {
      "insight_type": "contract_expiration",
      "title": "Contrato con Acme Corp vence en 5 días",
      "summary": "El contrato de servicios con Acme Corp (ID: doc-123) vence el 15/02/2026. Requiere renovación o finalización.",
      "urgency": "high",
      "confidence": 0.95,
      "related_document_ids": ["doc-123"],
      "suggested_actions": ["Revisar términos de renovación", "Contactar al proveedor"],
      "reasoning": "Contrato próximo a vencer sin acción registrada"
    }
  ],
  "overall_assessment": "Se detectó 1 contrato próximo a vencer que requiere atención.",
  "no_action_needed": false
}"""

    async def evaluate(
        self,
        context: TenantContext,
        enabled_types: Optional[List[str]] = None,
    ) -> LLMEvaluationResult:
        """Evaluate tenant context and generate insight candidates.

        Args:
            context: The gathered tenant context
            enabled_types: Which insight types are enabled (None = all)

        Returns:
            LLMEvaluationResult with insight candidates
        """
        # Build the evaluation prompt
        prompt = self._build_evaluation_prompt(context, enabled_types)
        system_prompt = await self._get_system_prompt()

        try:
            from app.agents.llm_router import get_llm_router

            router = await get_llm_router()
            response = await router.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )

            raw_response = response.content
            return self._parse_llm_response(raw_response)

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}", exc_info=True)
            return LLMEvaluationResult(
                insights=[],
                overall_assessment=f"Error during evaluation: {str(e)}",
                no_action_needed=True,
            )

    def _build_evaluation_prompt(
        self,
        context: TenantContext,
        enabled_types: Optional[List[str]] = None,
    ) -> str:
        """Build the evaluation prompt from context."""
        # Format enabled types
        if enabled_types:
            types_str = ", ".join(enabled_types)
        else:
            types_str = "todos los tipos"

        # Build context summary
        parts = [
            f"## Contexto del Tenant: {context.tenant_id}",
            f"Fecha de evaluación: {context.gathered_at.strftime('%Y-%m-%d %H:%M')}",
            f"Tipos de insight habilitados: {types_str}",
            "",
            "### Documentos",
            f"- Total de documentos: {context.total_documents}",
            f"- Indexados últimas 24h: {len(context.documents_indexed_24h)}",
            f"- Indexados últimos 7 días: {context.documents_indexed_7d}",
        ]

        if context.documents_by_collection:
            parts.append("- Por colección: " + ", ".join(
                f"{k}: {v}" for k, v in context.documents_by_collection.items()
            ))

        # Recent documents
        if context.documents_indexed_24h:
            parts.append("\nDocumentos recientes (24h):")
            for doc in context.documents_indexed_24h[:5]:
                parts.append(f"  - {doc.title} (ID: {doc.id}, colección: {doc.collection or 'N/A'})")

        # Expiring contracts
        parts.append("\n### Contratos por Vencer")
        if context.contracts_expiring_7d:
            parts.append(f"Vencen en 7 días ({len(context.contracts_expiring_7d)}):")
            for c in context.contracts_expiring_7d:
                parts.append(f"  - {c.title}: vence en {c.days_until_expiry} días (ID: {c.document_id})")
        else:
            parts.append("- No hay contratos venciendo en 7 días")

        if context.contracts_expiring_30d:
            parts.append(f"Vencen en 30 días ({len(context.contracts_expiring_30d)}):")
            for c in context.contracts_expiring_30d[:5]:
                parts.append(f"  - {c.title}: vence en {c.days_until_expiry} días")

        # User activity
        parts.append("\n### Actividad de Usuarios")
        parts.append(f"- Usuarios activos (24h): {context.user_activity.active_users_24h}")
        parts.append(f"- Consultas (24h): {context.user_activity.total_queries_24h}")
        if context.user_activity.top_queried_topics:
            parts.append(f"- Temas más consultados: {', '.join(context.user_activity.top_queried_topics[:5])}")

        # Pending items
        parts.append("\n### Items Pendientes")
        parts.append(f"- Análisis pendientes: {context.pending_analyses}")
        parts.append(f"- Análisis estancados (>7 días): {context.stale_analyses_7d}")
        parts.append(f"- Firmas pendientes: {context.pending_signatures}")

        # Anomalies
        if context.anomalies:
            parts.append("\n### Anomalías Detectadas")
            for a in context.anomalies[:5]:
                parts.append(f"- [{a.anomaly_type}] {a.description}")
        else:
            parts.append("\n### Anomalías: Ninguna detectada")

        # Delivery stats (for context)
        parts.append("\n### Historial de Notificaciones")
        parts.append(f"- Insights enviados hoy: {context.insights_delivered_today}")
        if context.last_insight_delivered_at:
            parts.append(f"- Último insight: {context.last_insight_delivered_at.strftime('%Y-%m-%d %H:%M')}")

        parts.append("\n---")
        parts.append("Analiza el contexto anterior y genera insights proactivos relevantes.")
        parts.append("Responde SOLO con JSON válido.")

        return "\n".join(parts)

    def _parse_llm_response(self, raw_response: str) -> LLMEvaluationResult:
        """Parse the LLM JSON response into structured result."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', raw_response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw_response)

            insights = []
            for item in data.get("insights", []):
                try:
                    insights.append(LLMInsightCandidate(
                        insight_type=item.get("insight_type", "activity_summary"),
                        title=item.get("title", "Sin título"),
                        summary=item.get("summary", ""),
                        urgency=item.get("urgency", "medium"),
                        confidence=float(item.get("confidence", 0.8)),
                        related_document_ids=item.get("related_document_ids", []),
                        suggested_actions=item.get("suggested_actions", []),
                        reasoning=item.get("reasoning", ""),
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse insight: {e}")
                    continue

            return LLMEvaluationResult(
                insights=insights,
                overall_assessment=data.get("overall_assessment", ""),
                no_action_needed=data.get("no_action_needed", len(insights) == 0),
                raw_response=raw_response,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return LLMEvaluationResult(
                insights=[],
                overall_assessment="Error parsing LLM response",
                no_action_needed=True,
                raw_response=raw_response,
            )

    def candidates_to_insights(
        self,
        candidates: List[LLMInsightCandidate],
        tenant_id: str,
    ) -> List[ProactiveInsightCreate]:
        """Convert LLM candidates to ProactiveInsightCreate objects.

        Insight types are passed through as strings directly — no enum
        mapping needed. This allows the LLM to generate any type defined
        in the Langfuse prompt without code changes.
        """
        insights = []

        for candidate in candidates:
            # Map urgency (still enum-based for validation)
            urgency = URGENCY_MAP.get(candidate.urgency, InsightUrgency.MEDIUM)

            # Build suggested actions
            actions = [
                SuggestedAction(action=a, priority=i + 1)
                for i, a in enumerate(candidate.suggested_actions[:5])
            ]

            insights.append(ProactiveInsightCreate(
                tenant_id=tenant_id,
                insight_type=candidate.insight_type,  # Pass string directly
                title=candidate.title[:255],
                summary=candidate.summary[:500] if candidate.summary else "",
                priority_score=0.0,  # Will be set by PriorityScorer
                urgency=urgency,
                confidence=candidate.confidence,
                related_documents=candidate.related_document_ids,
                suggested_actions=actions,
                reasoning=candidate.reasoning,
            ))

        return insights


# Global singleton
insight_evaluator = InsightEvaluator()
