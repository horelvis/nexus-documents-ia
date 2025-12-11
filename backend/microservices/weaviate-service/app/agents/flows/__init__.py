"""
Flows de orquestación para agentes.

Este módulo implementa patrones de orquestación:
- DocumentAnalysisFlow: Análisis de documentos usando SwarmWorkflow nativo (RECOMENDADO)
- PlanningFlow: Orquestador legacy con planificación dinámica usando ChatAgent
- legal_context: Utilidades para buscar legislación del BOE

FRAMEWORK: Microsoft Agent Framework
"""
from .planning_flow import PlanningFlow, FlowResult, get_planning_flow
from .document_analysis_flow import DocumentAnalysisFlow, AnalysisResult, get_document_analysis_flow
from .legal_context import search_legal_context, get_topics_for_agent

__all__ = [
    # Recommended (native SwarmWorkflow)
    "DocumentAnalysisFlow",
    "AnalysisResult",
    "get_document_analysis_flow",
    # Legacy (still used by some endpoints)
    "PlanningFlow",
    "FlowResult",
    "get_planning_flow",
    # Utilities
    "search_legal_context",
    "get_topics_for_agent",
]
