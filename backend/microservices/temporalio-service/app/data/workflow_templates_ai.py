"""
AI-Enhanced Workflow Templates
Templates that utilize the new AI Agent activities for intelligent workflow execution
"""

from typing import Dict, Any, List


def get_ai_enhanced_legal_advisory_template() -> Dict[str, Any]:
    """
    AI-Enhanced Legal Advisory Template
    Uses AI agents for intelligent legal consultation and document analysis
    """
    return {
        "id": "ai-legal-advisory-template",
        "name": "Asesoría Legal Inteligente con Emma AI",
        "description": "Consulta legal avanzada con agentes AI para análisis inteligente y recomendaciones personalizadas",
        "version": "2.0",
        "tenant_id": "default",
        "created_by": "system",
        "tags": ["legal", "ai-agents", "consultation", "emma"],
        "workflow_definition": {
            "start_step": "initial_analysis",
            "steps": [
                {
                    "step_id": "initial_analysis",
                    "step_name": "Análisis Inicial con Emma AI",
                    "step_type": "activity",
                    "activity_type": "emma_legal_advisor_agent",
                    "activity_config": {
                        "agent_type": "legal_advisor",
                        "task_description": "Realizar análisis legal inicial de la consulta del cliente",
                        "user_input": "{{user_input_data.description}}",
                        "context": {
                            "case_type": "{{user_input_data.case_type}}",
                            "client_name": "{{user_input_data.client_name}}",
                            "priority": "{{user_input_data.priority | default('medium')}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "document_analysis",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "document_analysis",
                    "step_name": "Análisis de Documentos",
                    "step_type": "activity",
                    "activity_type": "emma_document_analyzer_agent",
                    "activity_config": {
                        "agent_type": "document_analyzer",
                        "task_description": "Analizar documentos proporcionados y extraer información relevante",
                        "user_input": "{{user_input_data.documents | default('Sin documentos proporcionados')}}",
                        "context": {
                            "case_type": "{{user_input_data.case_type}}",
                            "client_name": "{{user_input_data.client_name}}",
                            "initial_analysis": "{{step_results.initial_analysis}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "multi_agent_coordination",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "multi_agent_coordination",
                    "step_name": "Coordinación Multi-Agente",
                    "step_type": "activity",
                    "activity_type": "multi_agent_coordinator",
                    "activity_config": {
                        "task_type": "legal_case_analysis",
                        "user_input": "Realizar análisis integral del caso legal",
                        "context": {
                            "case_type": "{{user_input_data.case_type}}",
                            "client_name": "{{user_input_data.client_name}}",
                            "description": "{{user_input_data.description}}",
                            "initial_analysis": "{{step_results.initial_analysis}}",
                            "document_analysis": "{{step_results.document_analysis}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "human_review_decision",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "human_review_decision",
                    "step_name": "Decisión de Revisión Humana",
                    "step_type": "decision",
                    "decision_conditions": {
                        "requires_human_review": "{{step_results.multi_agent_coordination.requires_human_input}}",
                        "complexity_threshold": "high",
                        "case_value": "{{user_input_data.case_value | default('medium')}}"
                    },
                    "next_steps": {
                        "approved": "human_review",
                        "rejected": "finalize_recommendations",
                        "continue": "finalize_recommendations"
                    }
                },
                {
                    "step_id": "human_review",
                    "step_name": "Revisión Humana Especializada",
                    "step_type": "manual",
                    "assignee_role": "legal_expert",
                    "instructions": "Revisar el análisis de los agentes AI y proporcionar validación experta",
                    "required_data": {
                        "expert_validation": True,
                        "additional_recommendations": True,
                        "risk_assessment": True
                    },
                    "next_steps": {
                        "approved": "finalize_recommendations",
                        "rejected": "additional_analysis"
                    }
                },
                {
                    "step_id": "additional_analysis",
                    "step_name": "Análisis Adicional Requerido",
                    "step_type": "activity",
                    "activity_type": "emma_legal_advisor_agent",
                    "activity_config": {
                        "agent_type": "legal_advisor",
                        "task_description": "Realizar análisis adicional basado en retroalimentación de experto humano",
                        "user_input": "{{step_results.human_review.feedback}}",
                        "context": {
                            "previous_analysis": "{{step_results.multi_agent_coordination}}",
                            "expert_feedback": "{{step_results.human_review}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "finalize_recommendations",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "finalize_recommendations",
                    "step_name": "Finalizar Recomendaciones",
                    "step_type": "activity",
                    "activity_type": "agent_state_persistence",
                    "activity_config": {
                        "operation": "save",
                        "agent_id": "legal_case_{{execution_id}}",
                        "agent_state": {
                            "case_summary": "{{step_results}}",
                            "final_recommendations": "{{step_results.multi_agent_coordination.combined_recommendations}}",
                            "completion_timestamp": "{{now()}}"
                        }
                    },
                    "next_steps": {
                        "success": "end",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "error_handling",
                    "step_name": "Manejo de Errores",
                    "step_type": "activity",
                    "activity_type": "send_notification",
                    "activity_config": {
                        "notification_type": "workflow_error",
                        "message": "Error en workflow de asesoría legal: {{error_details}}",
                        "recipients": ["{{user_id}}", "legal_admin"],
                        "tenant_id": "{{tenant_id}}"
                    },
                    "next_steps": {
                        "continue": "end"
                    }
                }
            ]
        },
        "input_schema": {
            "type": "object",
            "required": ["client_name", "case_type", "description"],
            "properties": {
                "client_name": {
                    "type": "string",
                    "description": "Nombre del cliente"
                },
                "case_type": {
                    "type": "string",
                    "enum": ["Laboral", "Civil", "Penal", "Comercial", "Familiar"],
                    "description": "Tipo de caso legal"
                },
                "description": {
                    "type": "string",
                    "description": "Descripción detallada del caso"
                },
                "documents": {
                    "type": "string",
                    "description": "Documentos relacionados (opcional)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Prioridad del caso"
                },
                "case_value": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Valor/complejidad del caso"
                }
            }
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "legal_analysis": {
                    "type": "object",
                    "description": "Análisis legal completo realizado por Emma AI"
                },
                "document_insights": {
                    "type": "object",
                    "description": "Información extraída de documentos"
                },
                "recommendations": {
                    "type": "array",
                    "description": "Recomendaciones finales"
                },
                "next_steps": {
                    "type": "array",
                    "description": "Próximos pasos sugeridos"
                },
                "expert_validation": {
                    "type": "object",
                    "description": "Validación de experto humano (si aplicable)"
                }
            }
        },
        "estimated_duration": "15-45 minutes",
        "complexity_level": "advanced",
        "ai_enhanced": True,
        "agent_types_used": [
            "emma_legal_advisor_agent",
            "emma_document_analyzer_agent",
            "multi_agent_coordinator"
        ]
    }


def get_ai_document_processing_template() -> Dict[str, Any]:
    """
    AI Document Processing Template
    Intelligent document analysis and processing workflow
    """
    return {
        "id": "ai-document-processing-template",
        "name": "Procesamiento Inteligente de Documentos",
        "description": "Análisis automatizado de documentos con agentes AI especializados",
        "version": "1.0",
        "tenant_id": "default",
        "created_by": "system",
        "tags": ["documents", "ai-agents", "analysis", "automation"],
        "workflow_definition": {
            "start_step": "document_intake",
            "steps": [
                {
                    "step_id": "document_intake",
                    "step_name": "Recepción de Documento",
                    "step_type": "activity",
                    "activity_type": "agent_state_persistence",
                    "activity_config": {
                        "operation": "save",
                        "agent_id": "doc_processor_{{execution_id}}",
                        "agent_state": {
                            "document_received": "{{user_input_data.document_content}}",
                            "document_type": "{{user_input_data.document_type}}",
                            "received_at": "{{now()}}"
                        }
                    },
                    "next_steps": {
                        "success": "analyze_document",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "analyze_document",
                    "step_name": "Análisis de Documento",
                    "step_type": "activity",
                    "activity_type": "emma_document_analyzer_agent",
                    "activity_config": {
                        "agent_type": "document_analyzer",
                        "task_description": "Realizar análisis completo del documento",
                        "user_input": "{{user_input_data.document_content}}",
                        "context": {
                            "document_type": "{{user_input_data.document_type}}",
                            "analysis_depth": "{{user_input_data.analysis_depth | default('standard')}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "generate_insights",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "generate_insights",
                    "step_name": "Generación de Insights",
                    "step_type": "activity",
                    "activity_type": "multi_agent_coordinator",
                    "activity_config": {
                        "task_type": "document_analysis",
                        "user_input": "Generar insights y recomendaciones basadas en el análisis",
                        "context": {
                            "document_analysis": "{{step_results.analyze_document}}",
                            "document_type": "{{user_input_data.document_type}}",
                            "tenant_id": "{{tenant_id}}",
                            "user_id": "{{user_id}}"
                        }
                    },
                    "next_steps": {
                        "success": "end",
                        "failure": "error_handling"
                    }
                },
                {
                    "step_id": "error_handling",
                    "step_name": "Manejo de Errores",
                    "step_type": "activity",
                    "activity_type": "send_notification",
                    "activity_config": {
                        "notification_type": "processing_error",
                        "message": "Error procesando documento: {{error_details}}",
                        "recipients": ["{{user_id}}"],
                        "tenant_id": "{{tenant_id}}"
                    },
                    "next_steps": {
                        "continue": "end"
                    }
                }
            ]
        },
        "input_schema": {
            "type": "object",
            "required": ["document_content", "document_type"],
            "properties": {
                "document_content": {
                    "type": "string",
                    "description": "Contenido del documento a analizar"
                },
                "document_type": {
                    "type": "string",
                    "enum": ["contract", "legal_brief", "report", "correspondence", "other"],
                    "description": "Tipo de documento"
                },
                "analysis_depth": {
                    "type": "string",
                    "enum": ["basic", "standard", "deep"],
                    "description": "Profundidad del análisis"
                }
            }
        },
        "estimated_duration": "5-15 minutes",
        "complexity_level": "medium",
        "ai_enhanced": True,
        "agent_types_used": [
            "emma_document_analyzer_agent",
            "multi_agent_coordinator"
        ]
    }


def get_all_ai_enhanced_templates() -> List[Dict[str, Any]]:
    """Get all AI-enhanced workflow templates"""
    return [
        get_ai_enhanced_legal_advisory_template(),
        get_ai_document_processing_template()
    ]