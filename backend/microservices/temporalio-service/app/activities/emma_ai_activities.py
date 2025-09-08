"""Emma AI Activities for Temporalio Workflows"""
from datetime import timedelta
from typing import Dict, Any
import httpx
import logging

from temporalio import activity
from app.core.config import settings

logger = logging.getLogger(__name__)


@activity.defn
async def analyze_employee_performance(contract_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze employee performance using Emma AI
    
    Args:
        contract_data: Dictionary containing contract and employee information
        
    Returns:
        Performance analysis with recommendation and confidence score
    """
    activity.logger.info(f"Analyzing performance for employee: {contract_data.get('employee_name')}")
    
    try:
        # Prepare Emma AI query for performance analysis
        emma_query = f"""
        Analiza el rendimiento del empleado para tomar decisión de renovación de contrato:
        
        Empleado: {contract_data.get('employee_name', 'N/A')}
        Posición: {contract_data.get('position', 'N/A')}
        Rating actual: {contract_data.get('performance_rating', 'No especificado')}
        Tipo de contrato: {contract_data.get('contract_type', 'N/A')}
        
        Evalúa:
        1. Rendimiento general del empleado
        2. Contribución al equipo y objetivos
        3. Potencial de crecimiento
        4. Recomendación de continuidad
        
        Proporciona un análisis detallado con puntuación numérica (0-100) y recomendación.
        """
        
        # Call Emma AI service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query",
                json={
                    "query": emma_query,
                    "tenant_id": contract_data.get("tenant_id"),
                    "enable_debug": False
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}"
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                analysis_text = emma_response.get("response", "")
                
                # Extract key metrics from Emma's response (simplified parsing)
                performance_score = 85  # Default good score
                recommendation = "renovar"  # Default recommendation
                confidence = 0.85
                
                # Simple keyword-based scoring (in real implementation, use Emma's structured response)
                if "excelente" in analysis_text.lower() or "excepcional" in analysis_text.lower():
                    performance_score = 95
                    confidence = 0.95
                elif "bueno" in analysis_text.lower() or "satisfactorio" in analysis_text.lower():
                    performance_score = 80
                    confidence = 0.80
                elif "bajo" in analysis_text.lower() or "insatisfactorio" in analysis_text.lower():
                    performance_score = 45
                    recommendation = "no_renovar"
                    confidence = 0.90
                
                return {
                    "success": True,
                    "employee_name": contract_data.get('employee_name'),
                    "performance_score": performance_score,
                    "recommendation": recommendation,
                    "confidence": confidence,
                    "analysis_summary": analysis_text[:500] + "..." if len(analysis_text) > 500 else analysis_text,
                    "analyzed_at": activity.now().isoformat()
                }
            else:
                raise Exception(f"Emma AI service error: {response.status_code}")
                
    except httpx.TimeoutException:
        activity.logger.error("Timeout calling Emma AI service")
        # Fallback analysis
        return {
            "success": False,
            "error": "timeout",
            "fallback_analysis": {
                "performance_score": 75,  # Neutral score
                "recommendation": "revisar_manualmente",
                "confidence": 0.5,
                "note": "Analysis timed out, manual review required"
            }
        }
        
    except Exception as e:
        activity.logger.error(f"Error in performance analysis: {e}")
        # Fallback analysis
        return {
            "success": False,
            "error": str(e),
            "fallback_analysis": {
                "performance_score": 75,
                "recommendation": "revisar_manualmente",
                "confidence": 0.3,
                "note": f"Analysis failed: {str(e)}"
            }
        }


@activity.defn
async def evaluate_operational_need(contract_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate operational need for the position using Emma AI
    
    Args:
        contract_data: Dictionary containing position and business information
        
    Returns:
        Operational need assessment with business justification
    """
    activity.logger.info(f"Evaluating operational need for position: {contract_data.get('position')}")
    
    try:
        emma_query = f"""
        Evalúa la necesidad operativa para mantener esta posición:
        
        Posición: {contract_data.get('position', 'N/A')}
        Tipo de contrato: {contract_data.get('contract_type', 'N/A')}
        Fecha vencimiento: {contract_data.get('expiration_date', 'N/A')}
        
        Analiza:
        1. Criticidad de la posición para operaciones
        2. Carga de trabajo actual y proyectada
        3. Impacto si la posición queda vacante
        4. Justificación económica de continuidad
        5. Alternativas (reestructuración, outsourcing, etc.)
        
        Proporciona evaluación con recomendación business-driven.
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query",
                json={
                    "query": emma_query,
                    "tenant_id": contract_data.get("tenant_id"),
                    "enable_debug": False
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}"
                },
                timeout=45.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                evaluation_text = emma_response.get("response", "")
                
                # Extract operational metrics
                operational_score = 85  # Default
                business_need = "alta"
                cost_justification = "justificado"
                
                # Keyword-based evaluation
                if "crítica" in evaluation_text.lower() or "esencial" in evaluation_text.lower():
                    operational_score = 95
                    business_need = "crítica"
                elif "importante" in evaluation_text.lower():
                    operational_score = 80
                    business_need = "alta"
                elif "prescindible" in evaluation_text.lower() or "innecesaria" in evaluation_text.lower():
                    operational_score = 30
                    business_need = "baja"
                    cost_justification = "no_justificado"
                
                return {
                    "success": True,
                    "position": contract_data.get('position'),
                    "operational_score": operational_score,
                    "business_need": business_need,
                    "cost_justification": cost_justification,
                    "evaluation_summary": evaluation_text[:500] + "..." if len(evaluation_text) > 500 else evaluation_text,
                    "recommendation": "mantener" if operational_score > 70 else "revisar",
                    "evaluated_at": activity.now().isoformat()
                }
            else:
                raise Exception(f"Emma AI service error: {response.status_code}")
                
    except Exception as e:
        activity.logger.error(f"Error in operational evaluation: {e}")
        # Fallback evaluation
        return {
            "success": False,
            "error": str(e),
            "fallback_evaluation": {
                "operational_score": 75,
                "business_need": "media",
                "cost_justification": "revisar_manualmente",
                "recommendation": "evaluar_caso_por_caso",
                "note": f"Evaluation failed: {str(e)}"
            }
        }


@activity.defn
async def generate_contract_recommendation(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate final contract recommendation based on performance and operational analysis
    
    Args:
        analysis_data: Combined performance and operational analysis data
        
    Returns:
        Final recommendation with supporting data and confidence
    """
    contract_id = analysis_data.get("contract_id")
    activity.logger.info(f"Generating recommendation for contract: {contract_id}")
    
    try:
        # Get analysis results
        performance_analysis = analysis_data.get("performance_analysis", {})
        operational_evaluation = analysis_data.get("operational_evaluation", {})
        contract_data = analysis_data.get("contract_data", {})
        
        # Prepare comprehensive recommendation query
        emma_query = f"""
        Genera recomendación final para renovación de contrato basada en análisis completo:
        
        EMPLEADO: {contract_data.get('employee_name', 'N/A')}
        POSICIÓN: {contract_data.get('position', 'N/A')}
        
        ANÁLISIS RENDIMIENTO:
        - Puntuación: {performance_analysis.get('performance_score', 'N/A')}/100
        - Recomendación: {performance_analysis.get('recommendation', 'N/A')}
        - Confianza: {performance_analysis.get('confidence', 'N/A')}
        
        EVALUACIÓN OPERATIVA:
        - Puntuación: {operational_evaluation.get('operational_score', 'N/A')}/100  
        - Necesidad: {operational_evaluation.get('business_need', 'N/A')}
        - Justificación: {operational_evaluation.get('cost_justification', 'N/A')}
        
        DECISIÓN REQUERIDA:
        1. RENOVAR o NO RENOVAR contrato
        2. Si RENOVAR: condiciones propuestas (duración, salario)
        3. Si NO RENOVAR: razones y proceso de terminación
        4. Nivel de confianza en la recomendación
        
        Proporciona recomendación ejecutiva clara y accionable.
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.EMMA_AI_SERVICE_URL}/elysia/query", 
                json={
                    "query": emma_query,
                    "tenant_id": analysis_data.get("tenant_id"),
                    "enable_debug": False
                },
                headers={
                    "Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}"
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                emma_response = response.json()
                recommendation_text = emma_response.get("response", "")
                
                # Decision logic based on scores
                performance_score = performance_analysis.get('performance_score', 75)
                operational_score = operational_evaluation.get('operational_score', 75)
                
                # Combined scoring
                combined_score = (performance_score * 0.6) + (operational_score * 0.4)
                
                if combined_score >= 80:
                    decision = "RENEW"
                    recommended_duration = "12 months"
                    salary_adjustment = "maintain_or_increase"
                    confidence = 0.90
                elif combined_score >= 60:
                    decision = "RENEW" 
                    recommended_duration = "6 months"
                    salary_adjustment = "maintain"
                    confidence = 0.70
                else:
                    decision = "TERMINATE"
                    termination_reason = "performance_and_operational_concerns"
                    confidence = 0.85
                
                result = {
                    "success": True,
                    "contract_id": contract_id,
                    "decision": decision,
                    "confidence": confidence,
                    "combined_score": combined_score,
                    "recommendation_text": recommendation_text,
                    "generated_at": activity.now().isoformat()
                }
                
                if decision == "RENEW":
                    result.update({
                        "recommended_duration": recommended_duration,
                        "salary_adjustment": salary_adjustment,
                        "renewal_conditions": [
                            "Performance review after 3 months",
                            "Clear objective setting",
                            "Regular feedback sessions"
                        ]
                    })
                else:
                    result.update({
                        "termination_reason": termination_reason,
                        "termination_process": [
                            "Prepare termination documentation",
                            "Calculate final compensation", 
                            "Schedule exit interview",
                            "Knowledge transfer planning"
                        ]
                    })
                
                return result
                
            else:
                raise Exception(f"Emma AI service error: {response.status_code}")
                
    except Exception as e:
        activity.logger.error(f"Error generating recommendation: {e}")
        
        # Fallback decision based on available data
        performance_score = analysis_data.get("performance_analysis", {}).get('performance_score', 75)
        operational_score = analysis_data.get("operational_evaluation", {}).get('operational_score', 75)
        
        fallback_decision = "RENEW" if (performance_score + operational_score) / 2 > 65 else "TERMINATE"
        
        return {
            "success": False,
            "error": str(e),
            "fallback_recommendation": {
                "decision": fallback_decision,
                "confidence": 0.5,
                "note": "Recommendation generated with fallback logic due to service error",
                "manual_review_required": True
            }
        }