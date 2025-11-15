"""
AI Workflow Catalog
Defines curated AI agent workflows (forms + template mapping) exposed to the frontend.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Union


AI_WORKFLOW_TEMPLATES: List[Dict] = [
    {
        "id": "ai-legal-advisory",
        "name": "Asesoría Legal Inteligente",
        "description": "Análisis legal multi-agente con recomendaciones priorizadas.",
        "template_id": "ai-legal-advisory-template",
        "tags": ["legal", "asesoría", "ai"],
        "estimated_duration": "15-30 min",
        "complexity": "advanced",
        "fields": [
            {
                "name": "client_name",
                "label": "Nombre del Cliente",
                "type": "text",
                "required": True,
                "placeholder": "Ej: María García"
            },
            {
                "name": "case_type",
                "label": "Tipo de Caso",
                "type": "select",
                "required": True,
                "options": [
                    {"label": "Laboral", "value": "Laboral"},
                    {"label": "Civil", "value": "Civil"},
                    {"label": "Penal", "value": "Penal"},
                    {"label": "Comercial", "value": "Comercial"},
                    {"label": "Familiar", "value": "Familiar"},
                ],
                "default_value": "Laboral"
            },
            {
                "name": "priority",
                "label": "Prioridad",
                "type": "select",
                "required": True,
                "options": [
                    {"label": "Baja", "value": "low"},
                    {"label": "Media", "value": "medium"},
                    {"label": "Alta", "value": "high"},
                    {"label": "Urgente", "value": "urgent"},
                ],
                "default_value": "medium"
            },
            {
                "name": "description",
                "label": "Descripción del Caso",
                "type": "textarea",
                "required": True,
                "placeholder": "Describe el contexto legal y los objetivos..."
            },
            {
                "name": "documents",
                "label": "Documentos (opcional)",
                "type": "textarea",
                "required": False,
                "helper_text": "Lista documentos relevantes o URLs accesibles."
            },
        ],
    },
    {
        "id": "ai-document-processing",
        "name": "Procesamiento Inteligente de Documentos",
        "description": "Analiza contratos y documentos con agentes especializados.",
        "template_id": "ai-document-processing-template",
        "tags": ["documentos", "contratos", "ai"],
        "estimated_duration": "10-20 min",
        "complexity": "intermediate",
        "fields": [
            {
                "name": "document_type",
                "label": "Tipo de Documento",
                "type": "select",
                "required": True,
                "options": [
                    {"label": "Contrato", "value": "contract"},
                    {"label": "Documento Legal", "value": "legal_brief"},
                    {"label": "Informe", "value": "report"},
                    {"label": "Correspondencia", "value": "correspondence"},
                    {"label": "Otro", "value": "other"},
                ],
                "default_value": "contract"
            },
            {
                "name": "analysis_depth",
                "label": "Profundidad del Análisis",
                "type": "select",
                "required": True,
                "options": [
                    {"label": "Básico", "value": "basic"},
                    {"label": "Estándar", "value": "standard"},
                    {"label": "Profundo", "value": "deep"},
                ],
                "default_value": "standard"
            },
            {
                "name": "document_content",
                "label": "Contenido del Documento",
                "type": "textarea",
                "required": True,
                "placeholder": "Pega el texto completo o un extracto representativo..."
            },
            {
                "name": "document_name",
                "label": "Nombre del Documento",
                "type": "text",
                "required": False,
                "placeholder": "Ej: Contrato de servicios 2025"
            },
        ],
    },
]


def list_ai_workflows() -> List[Dict]:
    return AI_WORKFLOW_TEMPLATES


def get_ai_workflow(workflow_id: str) -> Optional[Dict]:
    for workflow in AI_WORKFLOW_TEMPLATES:
        if workflow["id"] == workflow_id:
            return workflow
    return None


def _to_primitive(value: Union[str, int, float, List, Dict, None]) -> Union[str, int, float, List, Dict, None]:
    from uuid import UUID
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_to_primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_primitive(v) for k, v in value.items()}
    return value


def build_workflow_payload(workflow_id: str, field_values: Dict[str, str]) -> Dict[str, str]:
    """
    Normalize and enrich payloads for specific workflows before sending to Temporalio.
    """
    payload = {k: _to_primitive(v) for k, v in field_values.items() if v not in (None, "", [])}

    if workflow_id == "ai-legal-advisory":
        priority = payload.get("priority", "medium")
        payload.setdefault("case_value", "high" if priority == "urgent" else "medium")

    return payload
