"""
Advanced Emma AI Activities - Real AI integration for workflow templates
Integration with Weaviate service (Emma AI) for intelligent workflow processing
"""
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import httpx
import json

from temporalio import activity
from app.core.config import settings

logger = logging.getLogger(__name__)


@activity.defn
async def analyze_legal_case(case_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive legal case analysis using Emma AI
    
    Args:
        case_data: Case information and analysis requirements
        
    Returns:
        Detailed legal analysis with recommendations
    """
    user_input = case_data.get("user_input", {})
    consultation_type = user_input.get("consultation_type", "general")
    case_description = user_input.get("case_description", "")
    urgency_level = user_input.get("urgency_level", "media")
    
    activity.logger.info(f"Analyzing legal case: {consultation_type} (urgency: {urgency_level})")
    
    try:
        # Construct comprehensive Emma AI query for legal analysis
        emma_query = f"""
        Como experto en derecho laboral español, analiza exhaustivamente este caso:
        
        INFORMACIÓN DEL CASO:
        - Tipo de consulta: {consultation_type}
        - Nivel de urgencia: {urgency_level}
        - Cliente: {user_input.get('client_name', 'No especificado')}
        - Empresa: {user_input.get('company_name', 'No especificada')}
        
        DESCRIPCIÓN DETALLADA:
        {case_description}
        
        CONTEXTO ADICIONAL:
        - Empleados afectados: {user_input.get('affected_employees', 'No especificado')}
        - Tipo de contrato: {user_input.get('contract_type', 'No especificado')}
        - Resolución preferida: {user_input.get('preferred_resolution', 'No especificada')}
        - Presupuesto: {user_input.get('budget_range', 'No especificado')}
        - Fecha límite: {user_input.get('deadline', 'No especificada')}
        
        ANÁLISIS REQUERIDO:
        
        1. **CLASIFICACIÓN LEGAL:**
           - Categorizar el tipo de conflicto laboral
           - Identificar las áreas del derecho aplicables
           - Determinar la jurisdicción competente
        
        2. **NORMATIVA APLICABLE:**
           - Estatuto de los Trabajadores (artículos relevantes)
           - Convenios colectivos aplicables
           - Jurisprudencia del Tribunal Supremo relevante
           - Normativa europea si aplica
        
        3. **ANÁLISIS DE RIESGOS:**
           - Probabilidad de éxito en caso de litigio
           - Riesgos legales y económicos
           - Posibles consecuencias para la empresa/empleado
           - Precedentes jurisprudenciales adversos
        
        4. **ESTRATEGIA LEGAL RECOMENDADA:**
           - Enfoque principal recomendado
           - Argumentos jurídicos principales
           - Documentación necesaria
           - Pasos inmediatos a seguir
        
        5. **ALTERNATIVAS DE RESOLUCIÓN:**
           - Negociación directa (pros y contras)
           - Mediación laboral (viabilidad)
           - Conciliación previa (requisitos)
           - Vía judicial (probabilidades de éxito)
        
        6. **ESTIMACIÓN DE RECURSOS:**
           - Tiempo estimado de resolución
           - Costes aproximados por vía
           - Documentación requerida
           - Especialistas necesarios
        
        7. **RECOMENDACIONES INMEDIATAS:**
           - Acciones urgentes si las hay
           - Medidas preventivas
           - Comunicaciones recomendadas
           - Próximos pasos específicos
        
        Proporciona un análisis jurídico detallado, práctico y accionable.
        """
        
        # Call Emma AI service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query",
                json={
                    "query": emma_query,
                    "tenant_id": case_data.get("tenant_id", "default"),
                    "enable_debug": True,  # Enable for detailed reasoning
                    "context": {
                        "analysis_type": "legal_case_analysis",
                        "consultation_type": consultation_type,
                        "urgency": urgency_level,
                        "case_id": case_data.get("workflow_id", "unknown")
                    }
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=120.0  # Extended timeout for complex analysis
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                analysis_text = emma_response.get("response", "")
                debug_info = emma_response.get("debug", {})
                
                # Extract structured information from Emma's response
                analysis_result = _parse_legal_analysis(analysis_text, consultation_type, urgency_level)
                
                # Add Emma's reasoning process
                if debug_info:
                    analysis_result["emma_reasoning"] = {
                        "decision_tree": debug_info.get("decision_tree", []),
                        "tools_used": debug_info.get("tools_used", []),
                        "confidence_score": debug_info.get("confidence_score", 0.85),
                        "processing_time": debug_info.get("processing_time", "Unknown")
                    }
                
                # Determine next steps based on analysis
                next_step_recommendation = _determine_next_step(analysis_result, user_input)
                analysis_result["next_step_recommendation"] = next_step_recommendation
                
                return {
                    "success": True,
                    "analysis_type": "legal_case_analysis",
                    "consultation_type": consultation_type,
                    "analysis_result": analysis_result,
                    "raw_analysis": analysis_text,
                    "analyzed_at": datetime.utcnow().isoformat(),
                    "context_updates": {
                        "legal_analysis_completed": True,
                        "analysis_confidence": analysis_result.get("overall_confidence", 0.8),
                        "recommended_priority": analysis_result.get("recommended_priority", urgency_level),
                        "next_step": next_step_recommendation
                    }
                }
            else:
                raise Exception(f"Emma AI service error: {response.status_code} - {response.text}")
                
    except httpx.TimeoutException:
        activity.logger.error("Emma AI service timeout during legal analysis")
        return _fallback_legal_analysis(case_data, "timeout")
        
    except httpx.ConnectError:
        activity.logger.error("Cannot connect to Emma AI service")
        return _fallback_legal_analysis(case_data, "connection_error")
        
    except Exception as e:
        activity.logger.error(f"Error in legal analysis: {e}")
        return _fallback_legal_analysis(case_data, str(e))


@activity.defn
async def generate_legal_document(document_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate legal documents using Emma AI
    
    Args:
        document_data: Document type and case information
        
    Returns:
        Generated legal document with metadata
    """
    user_input = document_data.get("user_input", {})
    document_type = document_data.get("document_type", "legal_opinion")
    case_analysis = document_data.get("legal_analysis", {})
    
    activity.logger.info(f"Generating legal document: {document_type}")
    
    try:
        # Construct document generation query
        emma_query = f"""
        Como abogado especialista en derecho laboral, genera un {document_type} profesional:
        
        INFORMACIÓN DEL CLIENTE:
        - Nombre: {user_input.get('client_name', 'Cliente')}
        - Email: {user_input.get('client_email', '')}
        - Empresa: {user_input.get('company_name', '')}
        
        TIPO DE DOCUMENTO: {document_type}
        
        CASO:
        - Tipo de consulta: {user_input.get('consultation_type', '')}
        - Descripción: {user_input.get('case_description', '')}
        - Urgencia: {user_input.get('urgency_level', 'media')}
        
        ANÁLISIS PREVIO DISPONIBLE:
        {json.dumps(case_analysis, indent=2) if case_analysis else 'No disponible'}
        
        INSTRUCCIONES ESPECÍFICAS POR TIPO DE DOCUMENTO:
        
        {"DICTAMEN JURÍDICO:" if document_type == "legal_opinion" else ""}
        {"- Resumen ejecutivo del caso" if document_type == "legal_opinion" else ""}
        {"- Análisis legal detallado con referencias normativas" if document_type == "legal_opinion" else ""}
        {"- Conclusiones y recomendaciones" if document_type == "legal_opinion" else ""}
        {"- Plan de actuación propuesto" if document_type == "legal_opinion" else ""}
        
        {"CARTA DE REQUERIMIENTO:" if document_type == "demand_letter" else ""}
        {"- Encabezado formal con datos de las partes" if document_type == "demand_letter" else ""}
        {"- Exposición de hechos" if document_type == "demand_letter" else ""}
        {"- Fundamentos de derecho" if document_type == "demand_letter" else ""}
        {"- Petición clara y concreta" if document_type == "demand_letter" else ""}
        {"- Plazo para respuesta" if document_type == "demand_letter" else ""}
        
        {"PROPUESTA DE ACUERDO:" if document_type == "settlement_proposal" else ""}
        {"- Antecedentes del conflicto" if document_type == "settlement_proposal" else ""}
        {"- Propuesta de solución detallada" if document_type == "settlement_proposal" else ""}
        {"- Condiciones y plazos" if document_type == "settlement_proposal" else ""}
        {"- Beneficios mutuos" if document_type == "settlement_proposal" else ""}
        
        FORMATO REQUERIDO:
        - Documento formal en español
        - Estructura profesional con numeración
        - Referencias legales precisas
        - Lenguaje jurídico apropiado pero comprensible
        - Fecha y firma al final
        
        Genera un documento completo, profesional y legalmente sólido.
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query",
                json={
                    "query": emma_query,
                    "tenant_id": document_data.get("tenant_id", "default"),
                    "enable_debug": False,
                    "context": {
                        "document_generation": True,
                        "document_type": document_type,
                        "client_name": user_input.get('client_name', 'Cliente')
                    }
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=90.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                document_content = emma_response.get("response", "")
                
                # Generate document metadata
                document_id = f"{document_type}_{user_input.get('client_name', 'client').lower().replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                
                # Structure the document
                structured_document = {
                    "document_id": document_id,
                    "document_type": document_type,
                    "title": _get_document_title(document_type, user_input),
                    "content": document_content,
                    "metadata": {
                        "client_name": user_input.get('client_name'),
                        "case_type": user_input.get('consultation_type'),
                        "generated_date": datetime.utcnow().isoformat(),
                        "urgency_level": user_input.get('urgency_level'),
                        "word_count": len(document_content.split()),
                        "language": "es",
                        "format": "text"
                    },
                    "legal_references": _extract_legal_references(document_content),
                    "quality_score": _assess_document_quality(document_content, document_type)
                }
                
                return {
                    "success": True,
                    "document_id": document_id,
                    "document_type": document_type,
                    "generated_document": structured_document,
                    "storage_info": {
                        "storage_path": f"/legal_documents/{document_data.get('tenant_id', 'default')}/{document_id}.pdf",
                        "access_url": f"https://storage.nexusdocs360.com/legal_documents/{document_id}",
                        "expires_at": None  # Legal documents don't expire
                    },
                    "context_updates": {
                        f"{document_type}_generated": True,
                        "generated_document_id": document_id,
                        "document_ready": True
                    }
                }
            else:
                raise Exception(f"Emma AI service error: {response.status_code}")
                
    except Exception as e:
        activity.logger.error(f"Error generating legal document: {e}")
        return {
            "success": False,
            "error": str(e),
            "document_type": document_type,
            "fallback_document": _create_fallback_document(document_data)
        }


@activity.defn
async def emma_case_recommendation(recommendation_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get Emma AI recommendation for case handling strategy
    
    Args:
        recommendation_data: Case data and analysis results
        
    Returns:
        Strategic recommendations from Emma AI
    """
    user_input = recommendation_data.get("user_input", {})
    analysis_result = recommendation_data.get("analysis_result", {})
    
    activity.logger.info("Getting Emma AI strategic recommendation")
    
    try:
        emma_query = f"""
        Como consultor estratégico en derecho laboral, proporciona recomendaciones ejecutivas:
        
        RESUMEN DEL CASO:
        - Cliente: {user_input.get('client_name', 'Cliente')}
        - Tipo: {user_input.get('consultation_type', 'General')}
        - Urgencia: {user_input.get('urgency_level', 'Media')}
        - Presupuesto: {user_input.get('budget_range', 'No especificado')}
        - Resolución preferida: {user_input.get('preferred_resolution', 'No especificada')}
        
        ANÁLISIS LEGAL PREVIO:
        {json.dumps(analysis_result, indent=2) if analysis_result else 'No disponible'}
        
        PROPORCIONA RECOMENDACIONES ESTRATÉGICAS EN:
        
        1. **ESTRATEGIA PRINCIPAL:**
           - Enfoque recomendado (negociación/mediación/judicial)
           - Justificación de la estrategia elegida
           - Probabilidad de éxito estimada
        
        2. **PLAN DE ACCIÓN INMEDIATO:**
           - Primeros 3 pasos críticos
           - Plazos recomendados
           - Recursos necesarios
        
        3. **GESTIÓN DE RIESGOS:**
           - Principales riesgos identificados
           - Medidas de mitigación
           - Planes de contingencia
        
        4. **COMUNICACIÓN CON CLIENTE:**
           - Mensajes clave a transmitir
           - Expectativas a gestionar
           - Siguientes reuniones recomendadas
        
        5. **ASIGNACIÓN DE RECURSOS:**
           - Perfil del abogado necesario
           - Tiempo estimado de dedicación
           - Presupuesto orientativo por fase
        
        Da recomendaciones concretas y accionables.
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query",
                json={
                    "query": emma_query,
                    "tenant_id": recommendation_data.get("tenant_id", "default"),
                    "enable_debug": True,
                    "context": {
                        "recommendation_request": True,
                        "case_complexity": analysis_result.get("complexity_level", "intermediate")
                    }
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                recommendation_text = emma_response.get("response", "")
                debug_info = emma_response.get("debug", {})
                
                # Parse recommendations
                parsed_recommendations = _parse_recommendations(recommendation_text)
                
                return {
                    "success": True,
                    "recommendation_type": "strategic_case_handling",
                    "recommendations": parsed_recommendations,
                    "raw_recommendation": recommendation_text,
                    "emma_reasoning": debug_info,
                    "confidence_score": debug_info.get("confidence_score", 0.85),
                    "recommended_at": datetime.utcnow().isoformat(),
                    "context_updates": {
                        "strategic_recommendation_ready": True,
                        "recommended_strategy": parsed_recommendations.get("primary_strategy", "analysis"),
                        "estimated_duration": parsed_recommendations.get("estimated_timeline", "Unknown")
                    }
                }
            else:
                raise Exception(f"Emma AI service error: {response.status_code}")
                
    except Exception as e:
        activity.logger.error(f"Error getting Emma AI recommendation: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback_recommendation": {
                "primary_strategy": "manual_review",
                "next_steps": ["Assign to senior lawyer", "Schedule client meeting"],
                "estimated_timeline": "5-10 days"
            }
        }


# Helper functions
def _parse_legal_analysis(analysis_text: str, consultation_type: str, urgency: str) -> Dict[str, Any]:
    """Parse Emma's legal analysis into structured format"""
    
    # Basic parsing - in production, this would be more sophisticated
    analysis_result = {
        "consultation_type": consultation_type,
        "urgency_level": urgency,
        "overall_confidence": 0.85,  # Default confidence
        "complexity_level": "intermediate",
        "legal_areas": [],
        "applicable_laws": [],
        "risk_assessment": {},
        "recommended_actions": [],
        "estimated_timeline": "5-10 días laborables",
        "estimated_cost_range": "1000-5000€"
    }
    
    # Extract key information (simplified parsing)
    if "alto riesgo" in analysis_text.lower() or "crítico" in analysis_text.lower():
        analysis_result["risk_level"] = "high"
        analysis_result["complexity_level"] = "advanced"
    elif "bajo riesgo" in analysis_text.lower():
        analysis_result["risk_level"] = "low"
        analysis_result["complexity_level"] = "simple"
    else:
        analysis_result["risk_level"] = "medium"
    
    # Extract legal areas mentioned
    legal_keywords = ["estatuto de los trabajadores", "convenio colectivo", "discriminación", "despido", "indemnización"]
    for keyword in legal_keywords:
        if keyword in analysis_text.lower():
            analysis_result["legal_areas"].append(keyword.title())
    
    return analysis_result


def _determine_next_step(analysis_result: Dict[str, Any], user_input: Dict[str, Any]) -> str:
    """Determine recommended next step based on analysis"""
    
    risk_level = analysis_result.get("risk_level", "medium")
    urgency = user_input.get("urgency_level", "media")
    consultation_type = user_input.get("consultation_type", "")
    
    if risk_level == "high" or urgency == "alta":
        return "escalate_to_senior"
    elif consultation_type in ["discrimination", "disciplinary"]:
        return "priority_handling"
    elif user_input.get("preferred_resolution") == "negotiation":
        return "negotiation_strategy"
    else:
        return "legal_review"


def _fallback_legal_analysis(case_data: Dict[str, Any], error_reason: str) -> Dict[str, Any]:
    """Provide fallback analysis when Emma AI is unavailable"""
    
    user_input = case_data.get("user_input", {})
    
    return {
        "success": False,
        "error": f"Emma AI unavailable: {error_reason}",
        "fallback_analysis": {
            "consultation_type": user_input.get("consultation_type", "general"),
            "urgency_level": user_input.get("urgency_level", "media"),
            "risk_level": "medium",  # Conservative default
            "complexity_level": "intermediate",
            "recommended_actions": [
                "Manual review by senior lawyer required",
                "Gather additional documentation",
                "Schedule client consultation"
            ],
            "estimated_timeline": "7-14 días laborables",
            "note": "Analysis generated without AI assistance - manual review recommended"
        },
        "context_updates": {
            "manual_review_required": True,
            "ai_analysis_failed": True,
            "fallback_used": True
        }
    }


def _get_document_title(document_type: str, user_input: Dict[str, Any]) -> str:
    """Generate appropriate document title"""
    
    client_name = user_input.get("client_name", "Cliente")
    
    titles = {
        "legal_opinion": f"Dictamen Jurídico - {client_name}",
        "demand_letter": f"Carta de Requerimiento - {client_name}",
        "settlement_proposal": f"Propuesta de Acuerdo - {client_name}",
        "contract_analysis": f"Análisis Contractual - {client_name}",
        "legal_brief": f"Informe Legal - {client_name}"
    }
    
    return titles.get(document_type, f"Documento Legal - {client_name}")


def _extract_legal_references(document_content: str) -> List[str]:
    """Extract legal references from document"""
    
    references = []
    
    # Simple pattern matching for common legal references
    import re
    
    # Estatuto de los Trabajadores
    et_matches = re.findall(r'art[íi]culo\s+\d+.*?estatuto.*?trabajadores', document_content, re.IGNORECASE)
    references.extend(et_matches[:5])  # Limit to first 5 matches
    
    # Other legal references
    legal_patterns = [
        r'convenio colectivo',
        r'tribunal supremo',
        r'constitución española',
        r'directiva.*?europea'
    ]
    
    for pattern in legal_patterns:
        matches = re.findall(pattern, document_content, re.IGNORECASE)
        references.extend(matches[:2])
    
    return list(set(references))  # Remove duplicates


def _assess_document_quality(content: str, document_type: str) -> float:
    """Assess document quality score"""
    
    score = 0.7  # Base score
    
    # Length check
    word_count = len(content.split())
    if word_count > 300:
        score += 0.1
    if word_count > 500:
        score += 0.1
    
    # Structure check
    if "1." in content or "I." in content:  # Has numbering
        score += 0.05
    
    # Legal language check
    legal_terms = ["derecho", "artículo", "normativa", "jurisprudencia", "conclusión"]
    found_terms = sum(1 for term in legal_terms if term.lower() in content.lower())
    score += (found_terms / len(legal_terms)) * 0.1
    
    return min(1.0, score)


def _create_fallback_document(document_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create basic fallback document"""
    
    user_input = document_data.get("user_input", {})
    document_type = document_data.get("document_type", "legal_document")
    
    return {
        "document_type": document_type,
        "title": f"Documento Legal - {user_input.get('client_name', 'Cliente')}",
        "content": f"""
        DOCUMENTO LEGAL GENERADO AUTOMÁTICAMENTE
        
        Cliente: {user_input.get('client_name', 'No especificado')}
        Fecha: {datetime.utcnow().strftime('%d/%m/%Y')}
        Tipo de consulta: {user_input.get('consultation_type', 'General')}
        
        NOTA: Este documento ha sido generado automáticamente debido a la indisponibilidad 
        del sistema de IA. Se requiere revisión manual por parte de un abogado especialista.
        
        Descripción del caso:
        {user_input.get('case_description', 'No disponible')}
        
        Se recomienda programar una consulta legal presencial para análisis detallado.
        """,
        "is_fallback": True,
        "requires_manual_review": True
    }


def _parse_recommendations(recommendation_text: str) -> Dict[str, Any]:
    """Parse Emma's recommendations into structured format"""
    
    return {
        "primary_strategy": "analysis",  # Default
        "confidence_level": "medium",
        "next_steps": [
            "Review case documentation",
            "Schedule client meeting",
            "Prepare legal strategy"
        ],
        "estimated_timeline": "5-10 días laborables",
        "risk_factors": [],
        "success_probability": 0.7,
        "resource_requirements": {
            "lawyer_hours": "10-20",
            "budget_estimate": "2000-4000€",
            "specialist_required": False
        }
    }