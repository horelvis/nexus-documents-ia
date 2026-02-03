"""Insight Evaluator — LLM-based context analysis for proactive insights.

Uses the configured LLM (vLLM/Qwen) to evaluate tenant context and
generate actionable insights. The LLM receives structured context
and returns JSON-formatted insight candidates.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.heartbeat import (
    InsightType,
    InsightUrgency,
    LLMEvaluationResult,
    LLMInsightCandidate,
    ProactiveInsight,
    ProactiveInsightCreate,
    SuggestedAction,
    TenantContext,
)

logger = logging.getLogger(__name__)

# Mapping from string to enum
INSIGHT_TYPE_MAP = {
    "contract_expiration": InsightType.CONTRACT_EXPIRATION,
    "compliance_alert": InsightType.COMPLIANCE_ALERT,
    "risk_alert": InsightType.RISK_ALERT,
    "anomaly_detected": InsightType.ANOMALY_DETECTED,
    "task_reminder": InsightType.TASK_REMINDER,
    "activity_summary": InsightType.ACTIVITY_SUMMARY,
    "document_update": InsightType.DOCUMENT_UPDATE,
    "deadline_approaching": InsightType.DEADLINE_APPROACHING,
}

URGENCY_MAP = {
    "critical": InsightUrgency.CRITICAL,
    "high": InsightUrgency.HIGH,
    "medium": InsightUrgency.MEDIUM,
    "low": InsightUrgency.LOW,
}


class InsightEvaluator:
    """Evaluates tenant context using LLM to generate proactive insights."""

    def __init__(self):
        self._llm_client = None

    async def _get_llm_client(self):
        """Get or create async OpenAI client for vLLM."""
        if self._llm_client is None:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key="not-needed",
                base_url=settings.vllm_base_url,
            )
        return self._llm_client

    async def evaluate(
        self,
        context: TenantContext,
        enabled_types: Optional[List[InsightType]] = None,
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

        try:
            client = await self._get_llm_client()

            response = await client.chat.completions.create(
                model=settings.vllm_model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )

            raw_response = response.choices[0].message.content
            return self._parse_llm_response(raw_response)

        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}", exc_info=True)
            return LLMEvaluationResult(
                insights=[],
                overall_assessment=f"Error during evaluation: {str(e)}",
                no_action_needed=True,
            )

    def _get_system_prompt(self) -> str:
        """System prompt for the insight evaluator."""
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

    def _build_evaluation_prompt(
        self,
        context: TenantContext,
        enabled_types: Optional[List[InsightType]] = None,
    ) -> str:
        """Build the evaluation prompt from context."""
        # Format enabled types
        if enabled_types:
            types_str = ", ".join([t.value for t in enabled_types])
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
        """Convert LLM candidates to ProactiveInsightCreate objects."""
        insights = []

        for candidate in candidates:
            # Map insight type
            insight_type = INSIGHT_TYPE_MAP.get(
                candidate.insight_type,
                InsightType.ACTIVITY_SUMMARY,
            )

            # Map urgency
            urgency = URGENCY_MAP.get(candidate.urgency, InsightUrgency.MEDIUM)

            # Build suggested actions
            actions = [
                SuggestedAction(action=a, priority=i + 1)
                for i, a in enumerate(candidate.suggested_actions[:5])
            ]

            insights.append(ProactiveInsightCreate(
                tenant_id=tenant_id,
                insight_type=insight_type,
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
