"""
Script to create Asesoría Laboral (Legal Advisory) workflow template
Template for legal consultation and advisory services
"""
import asyncio
import json
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models.workflow_template import WorkflowTemplate, WorkflowTemplateField
import uuid


def create_legal_advisory_template():
    """Create Asesoría Laboral workflow template"""
    
    db = SessionLocal()
    
    try:
        # Template basic info
        template = WorkflowTemplate(
            id=uuid.uuid4(),
            tenant_id="default_tenant",  # Update with actual tenant
            name="Asesoría Laboral",
            description="Proceso completo de asesoría laboral para consultas legales, revisión de contratos y gestión de conflictos laborales",
            category="legal",
            version="1.0.0",
            status="active",
            estimated_duration="5-10 días laborables",
            complexity_level="advanced",
            tags=["legal", "asesoría", "laboral", "contratos", "consulta"],
            is_public=False,
            allowed_roles=["admin", "hr_manager", "legal_team"],
            created_by="system",
            created_at=datetime.utcnow()
        )
        
        # Workflow definition with steps
        workflow_definition = {
            "version": "1.0",
            "start_step": "intake_consultation",
            "steps": [
                {
                    "step_id": "intake_consultation",
                    "step_name": "Recepción de Consulta",
                    "step_type": "manual",
                    "description": "Recepción y clasificación inicial de la consulta laboral",
                    "estimated_duration": "1 hora",
                    "assignee_role": "legal_assistant",
                    "instructions": "Revisar la consulta, clasificar por tipo y urgencia, recopilar documentación inicial",
                    "activity_config": {
                        "required_documents": ["consultation_form", "employment_documents"],
                        "urgency_levels": ["alta", "media", "baja"],
                        "consultation_types": ["contractual", "disciplinary", "termination", "discrimination", "benefits"]
                    },
                    "next_steps": {
                        "continue": "emma_ai_analysis",
                        "insufficient_info": "request_additional_info"
                    }
                },
                {
                    "step_id": "emma_ai_analysis",
                    "step_name": "Análisis Automático con Emma AI",
                    "step_type": "activity",
                    "description": "Emma AI analiza la consulta y proporciona análisis legal preliminar",
                    "estimated_duration": "30 minutos",
                    "activity_type": "emma_ai_legal_analysis",
                    "activity_config": {
                        "analysis_areas": [
                            "Clasificación legal del caso",
                            "Normativa aplicable",
                            "Precedentes relevantes",
                            "Riesgos identificados",
                            "Recomendaciones preliminares"
                        ],
                        "legal_frameworks": ["Estatuto de los Trabajadores", "Convenios Colectivos", "Jurisprudencia"]
                    },
                    "next_steps": {
                        "analysis_complete": "legal_review",
                        "complex_case": "escalate_to_senior"
                    }
                },
                {
                    "step_id": "legal_review",
                    "step_name": "Revisión Legal Especializada",
                    "step_type": "manual",
                    "description": "Abogado especialista revisa el análisis y desarrolla estrategia legal",
                    "estimated_duration": "2-4 horas",
                    "assignee_role": "labor_lawyer",
                    "instructions": "Revisar análisis de Emma AI, validar conclusiones, desarrollar estrategia legal detallada",
                    "activity_config": {
                        "review_checklist": [
                            "Verificar normativa aplicable",
                            "Analizar viabilidad legal",
                            "Evaluar riesgos y costes",
                            "Definir estrategia de actuación",
                            "Preparar recomendaciones"
                        ]
                    },
                    "next_steps": {
                        "strategy_defined": "document_preparation",
                        "negotiation_needed": "negotiation_strategy",
                        "litigation_required": "litigation_preparation"
                    }
                },
                {
                    "step_id": "document_preparation",
                    "step_name": "Preparación de Documentos",
                    "step_type": "activity",
                    "description": "Generación de documentos legales necesarios",
                    "estimated_duration": "2-3 horas",
                    "activity_type": "legal_document_generation",
                    "activity_config": {
                        "document_types": [
                            "Dictamen jurídico",
                            "Cartas de requerimiento",
                            "Contratos y anexos",
                            "Recursos y alegaciones",
                            "Propuestas de acuerdo"
                        ],
                        "review_required": true
                    },
                    "next_steps": {
                        "documents_ready": "client_communication",
                        "approval_needed": "document_approval"
                    }
                },
                {
                    "step_id": "client_communication",
                    "step_name": "Comunicación con Cliente",
                    "step_type": "manual",
                    "description": "Presentación de análisis y recomendaciones al cliente",
                    "estimated_duration": "1-2 horas",
                    "assignee_role": "labor_lawyer",
                    "instructions": "Presentar dictamen legal, explicar opciones disponibles, acordar plan de acción",
                    "activity_config": {
                        "communication_channels": ["meeting", "video_call", "detailed_report"],
                        "deliverables": [
                            "Dictamen legal detallado",
                            "Resumen ejecutivo",
                            "Plan de acción recomendado",
                            "Cronograma de actuaciones"
                        ]
                    },
                    "next_steps": {
                        "client_approved": "execution_phase",
                        "modifications_requested": "revision_cycle",
                        "case_closed": "case_closure"
                    }
                },
                {
                    "step_id": "execution_phase",
                    "step_name": "Ejecución de Actuaciones",
                    "step_type": "manual",
                    "description": "Ejecución del plan legal acordado",
                    "estimated_duration": "Variable según caso",
                    "assignee_role": "labor_lawyer",
                    "instructions": "Ejecutar las actuaciones legales planificadas según cronograma",
                    "activity_config": {
                        "possible_actions": [
                            "Negociación con la otra parte",
                            "Presentación de recursos",
                            "Mediación laboral",
                            "Representación legal",
                            "Seguimiento de cumplimiento"
                        ],
                        "monitoring_required": true
                    },
                    "next_steps": {
                        "successful_resolution": "case_closure",
                        "ongoing_monitoring": "monitoring_phase",
                        "escalation_needed": "escalation"
                    }
                },
                {
                    "step_id": "case_closure",
                    "step_name": "Cierre de Caso",
                    "step_type": "activity",
                    "description": "Documentación final y cierre del caso",
                    "estimated_duration": "1 hora",
                    "activity_type": "case_documentation",
                    "activity_config": {
                        "closure_documents": [
                            "Resumen final del caso",
                            "Resultados obtenidos",
                            "Documentación generada",
                            "Facturación y costes",
                            "Archivo del expediente"
                        ]
                    },
                    "next_steps": {
                        "complete": "end"
                    }
                }
            ]
        }
        
        # Input schema for the form
        input_schema = {
            "type": "object",
            "required": [
                "client_name", 
                "consultation_type", 
                "urgency_level", 
                "case_description"
            ],
            "properties": {
                "client_name": {
                    "type": "string",
                    "title": "Nombre del Cliente",
                    "description": "Nombre completo del solicitante"
                },
                "client_email": {
                    "type": "string",
                    "title": "Email de Contacto",
                    "format": "email"
                },
                "client_phone": {
                    "type": "string", 
                    "title": "Teléfono de Contacto"
                },
                "company_name": {
                    "type": "string",
                    "title": "Empresa/Organización"
                },
                "consultation_type": {
                    "type": "string",
                    "title": "Tipo de Consulta",
                    "enum": ["contractual", "disciplinary", "termination", "discrimination", "benefits", "collective_negotiation", "other"]
                },
                "urgency_level": {
                    "type": "string",
                    "title": "Nivel de Urgencia",
                    "enum": ["alta", "media", "baja"]
                },
                "case_description": {
                    "type": "string",
                    "title": "Descripción del Caso",
                    "description": "Descripción detallada de la situación o consulta"
                },
                "affected_employees": {
                    "type": "number",
                    "title": "Número de Empleados Afectados",
                    "minimum": 1
                },
                "contract_type": {
                    "type": "string",
                    "title": "Tipo de Contrato",
                    "enum": ["indefinido", "temporal", "formacion", "practicas", "obra_servicio", "otro"]
                },
                "has_legal_precedent": {
                    "type": "boolean",
                    "title": "¿Existe Antecedente Legal?"
                },
                "preferred_resolution": {
                    "type": "string",
                    "title": "Resolución Preferida",
                    "enum": ["negotiation", "mediation", "legal_action", "advisory_only"]
                },
                "budget_range": {
                    "type": "string",
                    "title": "Rango Presupuestario",
                    "enum": ["<1000", "1000-5000", "5000-15000", ">15000"]
                },
                "deadline": {
                    "type": "string",
                    "title": "Fecha Límite",
                    "format": "date"
                },
                "additional_notes": {
                    "type": "string",
                    "title": "Notas Adicionales"
                }
            }
        }
        
        # Validation rules
        validation_rules = {
            "business_rules": {
                "max_urgency_cases_per_day": 5,
                "require_approval_for_litigation": True,
                "mandatory_documentation": ["consultation_form"],
                "budget_approval_threshold": 10000
            },
            "legal_compliance": {
                "data_protection_required": True,
                "client_confidentiality": True,
                "professional_liability_insurance": True
            }
        }
        
        # Notification configuration
        notification_config = {
            "case_created": {
                "notify": ["legal_team", "client"],
                "template": "case_created_notification"
            },
            "analysis_complete": {
                "notify": ["client", "assigned_lawyer"],
                "template": "analysis_ready_notification"
            },
            "documents_ready": {
                "notify": ["client"],
                "template": "documents_ready_notification"
            },
            "case_closed": {
                "notify": ["client", "legal_team", "billing_department"],
                "template": "case_closure_notification"
            },
            "deadline_approaching": {
                "notify": ["assigned_lawyer", "legal_manager"],
                "template": "deadline_reminder",
                "trigger_days_before": 3
            }
        }
        
        # Set template data
        template.workflow_definition = workflow_definition
        template.input_schema = input_schema
        template.validation_rules = validation_rules
        template.notification_config = notification_config
        
        # Save template
        db.add(template)
        db.commit()
        db.refresh(template)
        
        # Create template fields
        fields_data = [
            {
                "field_name": "client_name",
                "field_label": "Nombre del Cliente",
                "field_type": "text",
                "is_required": True,
                "field_order": 1,
                "field_group": "client_info",
                "placeholder_text": "Nombre completo"
            },
            {
                "field_name": "client_email", 
                "field_label": "Email de Contacto",
                "field_type": "email",
                "is_required": True,
                "field_order": 2,
                "field_group": "client_info",
                "placeholder_text": "email@ejemplo.com"
            },
            {
                "field_name": "client_phone",
                "field_label": "Teléfono de Contacto",
                "field_type": "phone",
                "is_required": False,
                "field_order": 3,
                "field_group": "client_info",
                "placeholder_text": "+34 600 000 000"
            },
            {
                "field_name": "company_name",
                "field_label": "Empresa/Organización", 
                "field_type": "text",
                "is_required": False,
                "field_order": 4,
                "field_group": "client_info",
                "placeholder_text": "Nombre de la empresa"
            },
            {
                "field_name": "consultation_type",
                "field_label": "Tipo de Consulta",
                "field_type": "select",
                "is_required": True,
                "field_order": 5,
                "field_group": "case_details",
                "field_options": [
                    {"value": "contractual", "label": "Asuntos Contractuales"},
                    {"value": "disciplinary", "label": "Procedimientos Disciplinarios"},
                    {"value": "termination", "label": "Despidos y Terminaciones"},
                    {"value": "discrimination", "label": "Discriminación Laboral"},
                    {"value": "benefits", "label": "Prestaciones y Beneficios"},
                    {"value": "collective_negotiation", "label": "Negociación Colectiva"},
                    {"value": "other", "label": "Otros"}
                ]
            },
            {
                "field_name": "urgency_level",
                "field_label": "Nivel de Urgencia",
                "field_type": "select", 
                "is_required": True,
                "field_order": 6,
                "field_group": "case_details",
                "field_options": [
                    {"value": "alta", "label": "Alta - Requiere atención inmediata"},
                    {"value": "media", "label": "Media - Atención en 48-72h"},
                    {"value": "baja", "label": "Baja - Consulta general"}
                ]
            },
            {
                "field_name": "case_description",
                "field_label": "Descripción del Caso",
                "field_type": "textarea",
                "is_required": True,
                "field_order": 7,
                "field_group": "case_details",
                "placeholder_text": "Describa detalladamente la situación o consulta legal...",
                "help_text": "Incluya toda la información relevante: fechas, personas involucradas, documentos disponibles"
            },
            {
                "field_name": "affected_employees",
                "field_label": "Empleados Afectados",
                "field_type": "number",
                "is_required": False,
                "field_order": 8,
                "field_group": "case_details",
                "validation_rules": {"minimum": 1}
            },
            {
                "field_name": "contract_type",
                "field_label": "Tipo de Contrato",
                "field_type": "select",
                "is_required": False,
                "field_order": 9,
                "field_group": "case_details",
                "field_options": [
                    {"value": "indefinido", "label": "Contrato Indefinido"},
                    {"value": "temporal", "label": "Contrato Temporal"},
                    {"value": "formacion", "label": "Contrato de Formación"},
                    {"value": "practicas", "label": "Contrato en Prácticas"},
                    {"value": "obra_servicio", "label": "Obra o Servicio"},
                    {"value": "otro", "label": "Otro tipo"}
                ]
            },
            {
                "field_name": "preferred_resolution",
                "field_label": "Resolución Preferida",
                "field_type": "select",
                "is_required": False,
                "field_order": 10,
                "field_group": "preferences",
                "field_options": [
                    {"value": "negotiation", "label": "Negociación directa"},
                    {"value": "mediation", "label": "Mediación laboral"},
                    {"value": "legal_action", "label": "Acción legal/judicial"},
                    {"value": "advisory_only", "label": "Solo asesoría"}
                ]
            },
            {
                "field_name": "budget_range",
                "field_label": "Rango Presupuestario",
                "field_type": "select",
                "is_required": False,
                "field_order": 11,
                "field_group": "preferences",
                "field_options": [
                    {"value": "<1000", "label": "Menos de 1,000€"},
                    {"value": "1000-5000", "label": "1,000€ - 5,000€"},
                    {"value": "5000-15000", "label": "5,000€ - 15,000€"},
                    {"value": ">15000", "label": "Más de 15,000€"}
                ]
            },
            {
                "field_name": "deadline",
                "field_label": "Fecha Límite",
                "field_type": "date",
                "is_required": False,
                "field_order": 12,
                "field_group": "preferences",
                "help_text": "Si existe una fecha límite legal o de negocio"
            },
            {
                "field_name": "additional_notes",
                "field_label": "Información Adicional",
                "field_type": "textarea",
                "is_required": False,
                "field_order": 13,
                "field_group": "additional",
                "placeholder_text": "Cualquier información adicional relevante..."
            }
        ]
        
        for field_data in fields_data:
            field = WorkflowTemplateField(
                template_id=template.id,
                **field_data
            )
            db.add(field)
        
        db.commit()
        
        print(f"✅ Created Legal Advisory template with ID: {template.id}")
        print(f"Template name: {template.name}")
        print(f"Steps: {len(workflow_definition['steps'])}")
        print(f"Input fields: {len(fields_data)}")
        
        return template.id
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating template: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    template_id = create_legal_advisory_template()
    print(f"Legal Advisory template created successfully: {template_id}")