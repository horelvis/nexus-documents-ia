"""
BPM AI API Endpoints - Ubicación correcta en API Core
Prototipo para renovación de contratos con BPM + Emma AI
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from app.services.bpmn_ai_service import bpmn_ai_service
from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bpmn-ai", tags=["BPM AI"])


# Pydantic Models
class ContractRenewalRequest(BaseModel):
    contract_id: str = Field(..., description="ID del contrato a renovar")
    tenant_id: str = Field(..., description="ID del tenant")
    user_id: str = Field(..., description="ID del usuario que solicita")
    force_regenerate: bool = Field(False, description="Forzar regeneración del BPMN")
    
    class Config:
        schema_extra = {
            "example": {
                "contract_id": "contract_001",
                "tenant_id": "tenant_abc", 
                "user_id": "user_123",
                "force_regenerate": False
            }
        }


class BPMNGenerationRequest(BaseModel):
    process_description: str = Field(..., description="Descripción del proceso en lenguaje natural")
    tenant_id: str = Field(..., description="ID del tenant")
    process_type: str = Field(default="general", description="Tipo de proceso")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contexto adicional")
    
    class Config:
        schema_extra = {
            "example": {
                "process_description": "Proceso de renovación de contrato temporal que vence en enero",
                "tenant_id": "tenant_abc",
                "process_type": "contract_renewal",
                "context": {
                    "employee_name": "Juan Pérez",
                    "contract_type": "temporal"
                }
            }
        }


@router.get("/health")
async def health_check():
    """Health check del servicio BPM AI"""
    try:
        health_status = await bpmn_ai_service.health_check()
        
        # Determinar si el servicio está saludable
        is_healthy = (
            health_status.get("initialized", False) and
            "Error" not in health_status.get("ollama_service", "") and
            "Error" not in health_status.get("emma_ai_service", "")
        )
        
        if not is_healthy:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "details": health_status,
                    "message": "Algunos servicios no están disponibles pero el core funciona"
                }
            )
        
        return {
            "status": "healthy",
            "service": "bpmn-ai-service", 
            "details": health_status
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@router.post("/generate-bpmn")
async def generate_bpmn_from_description(
    request: BPMNGenerationRequest,
    current_user = Depends(get_current_user)
):
    """Genera diagrama BPMN desde descripción en lenguaje natural"""
    try:
        logger.info(f"Generating BPMN for tenant {request.tenant_id}")
        
        # Crear datos de contrato desde el contexto
        contract_data = {
            "contract_id": "generated_process",
            "tenant_id": request.tenant_id,
            "process_type": request.process_type,
            "description": request.process_description,
            **request.context
        }
        
        result = await bpmn_ai_service.generate_contract_renewal_bpmn(
            contract_data=contract_data,
            tenant_id=request.tenant_id
        )
        
        return {
            "success": True,
            "message": "BPMN generado exitosamente",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error generating BPMN: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error generando BPMN",
                "error": str(e)
            }
        )


@router.post("/contracts/{contract_id}/renewal")
async def generate_contract_renewal_process(
    contract_id: str,
    request: ContractRenewalRequest,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user)
):
    """Genera proceso completo de renovación para un contrato específico"""
    try:
        logger.info(f"Starting contract renewal process for {contract_id}")
        
        # Validar que el contract_id coincida
        if contract_id != request.contract_id:
            raise HTTPException(
                status_code=400,
                detail="Contract ID en path no coincide con el del body"
            )
        
        result = await bpmn_ai_service.generate_contract_renewal_bpmn(
            contract_data={"contract_id": contract_id, "tenant_id": request.tenant_id},
            tenant_id=request.tenant_id
        )
        
        return {
            "success": True,
            "message": f"Proceso de renovación generado para contrato {contract_id}",
            "contract_id": contract_id,
            "tenant_id": request.tenant_id,
            "data": result,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in contract renewal process: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error en proceso de renovación",
                "contract_id": contract_id,
                "error": str(e)
            }
        )


@router.post("/contracts/{contract_id}/execute")
async def execute_contract_renewal(
    contract_id: str,
    tenant_id: str,
    user_id: str,
    background_tasks: BackgroundTasks,
    current_user = Depends(get_current_user)
):
    """Ejecuta el proceso completo de renovación de contrato"""
    try:
        logger.info(f"Executing contract renewal for {contract_id}")
        
        # Ejecutar en background para procesos largos
        background_tasks.add_task(
            _execute_contract_renewal_background,
            contract_id,
            tenant_id,
            user_id
        )
        
        return {
            "success": True,
            "message": f"Proceso de renovación iniciado para contrato {contract_id}",
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "status": "processing",
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error executing contract renewal: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error ejecutando renovación",
                "contract_id": contract_id,
                "error": str(e)
            }
        )


@router.get("/contracts/{contract_id}/bpmn")
async def get_contract_bpmn(
    contract_id: str,
    tenant_id: str,
    current_user = Depends(get_current_user)
):
    """Obtiene el BPMN generado para un contrato específico"""
    try:
        # Generar BPMN para el contrato
        contract_data = {"contract_id": contract_id, "tenant_id": tenant_id}
        
        result = await bpmn_ai_service.generate_contract_renewal_bpmn(
            contract_data=contract_data,
            tenant_id=tenant_id
        )
        
        return {
            "success": True,
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "bpmn_data": result,
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error retrieving BPMN for contract {contract_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Error obteniendo BPMN para contrato {contract_id}",
                "error": str(e)
            }
        )


# Endpoint de prueba/demo OPTIMIZADO - SIN AUTENTICACIÓN PARA TESTING
@router.post("/demo/contract-renewal")
async def demo_contract_renewal(
    fast: bool = True  # Parámetro para demo rápido vs completo
):
    """Demo completo del proceso de renovación de contrato (público para testing)"""
    try:
        demo_contract_data = {
            "contract_id": "demo_contract_001",
            "tenant_id": "demo_tenant",
            "employee_name": "Ana González",
            "contract_type": "temporal",
            "expiration_date": "2025-02-15",
            "position": "Desarrolladora Senior",
            "performance_rating": "Excelente"
        }
        
        if fast:
            # DEMO RÁPIDO: Respuestas pre-calculadas (< 1 segundo)
            logger.info("🚀 Fast demo mode: usando respuestas pre-calculadas")
            
            return {
                "success": True,
                "message": "Demo de renovación de contrato completado (FAST MODE)",
                "demo_data": demo_contract_data,
                "performance_note": "⚡ Fast mode: < 1 segundo vs ~30 segundos con Ollama real",
                "architecture_note": "✅ Refactorizado: API Core -> Ollama Service (arquitectura correcta)",
                "bpmn_generation": {
                    "contract_id": "demo_contract_001",
                    "process_description": """Proceso de renovación de contrato temporal para Ana González que vence 2025-02-15:
        
        1. RRHH recibe alerta automática 30 días antes del vencimiento
        2. Se analiza el historial de rendimiento del empleado
        3. Se evalúa la necesidad operativa del puesto
        4. Se verifica cumplimiento de objetivos y asistencia
        5. Manager directo proporciona evaluación del empleado
        6. Si evaluación es positiva y hay necesidad operativa: se procede con renovación
        7. Si evaluación es negativa o no hay necesidad: se prepara terminación
        8. Para renovación: se genera nuevo contrato con condiciones actualizadas
        9. Se envía contrato a empleado para firma digital
        10. Se programa seguimiento si no hay respuesta en 7 días
        11. Una vez firmado, se actualiza sistema y se notifica a stakeholders
        12. Para terminación: se calcula liquidación y se programa finiquito""",
                    "extracted_elements": {
                        "agents": [
                            {"name": "RRHH", "confidence": 1.0},
                            {"name": "Manager", "confidence": 1.0},
                            {"name": "Empleado", "confidence": 1.0},
                            {"name": "Legal", "confidence": 0.9}
                        ],
                        "tasks": [
                            {"description": "Analizar rendimiento", "confidence": 1.0},
                            {"description": "Evaluar necesidad operativa", "confidence": 1.0},
                            {"description": "Generar contrato", "confidence": 1.0},
                            {"description": "Enviar para firma", "confidence": 1.0},
                            {"description": "Actualizar sistema", "confidence": 0.95}
                        ],
                        "conditions": [
                            {"condition": "evaluación positiva", "confidence": 1.0},
                            {"condition": "necesidad operativa", "confidence": 1.0},
                            {"condition": "firma completada", "confidence": 0.9}
                        ],
                        "process_info": [
                            {"info": "30 días antes del vencimiento", "confidence": 1.0},
                            {"info": "7 días para respuesta", "confidence": 1.0}
                        ]
                    },
                    "generated_bpmn": """
        START_EVENT: contract_expiration_alert
        →
        SERVICE_TASK: analyze_employee_performance (RRHH)
        →
        SERVICE_TASK: evaluate_operational_need (Manager)
        →
        EXCLUSIVE_GATEWAY: renewal_decision
        ├─ YES: performance_good AND operational_need
        │   →
        │   SERVICE_TASK: generate_renewal_contract (RRHH)
        │   →
        │   USER_TASK: employee_contract_signature (Empleado)
        │   →
        │   SERVICE_TASK: update_system_records (RRHH)
        │   →
        │   END_EVENT: renewal_completed
        │
        └─ NO: performance_poor OR no_operational_need
            →
            SERVICE_TASK: calculate_severance (RRHH)
            →
            SERVICE_TASK: prepare_termination_docs (Legal)
            →
            END_EVENT: termination_prepared
        """,
                    "validated_bpmn": {
                        "original_bpmn": "START_EVENT → SERVICE_TASK → ...",
                        "optimized_bpmn": "Versión optimizada con validación legal española",
                        "legal_compliance_points": [
                            "✅ Verificación Art. 15 Estatuto de los Trabajadores",
                            "✅ Plazo preaviso 15 días naturales según convenio",
                            "✅ Procedimiento contradictorio garantizado",
                            "✅ Documentación obligatoria completa"
                        ],
                        "recommendations": [
                            "Incluir cláusula prórroga automática si aplica",
                            "Documentar evaluación de rendimiento detalladamente",
                            "Verificar convenio colectivo específico del sector"
                        ],
                        "identified_risks": [
                            "Posible impugnación si no se justifica la no renovación",
                            "Riesgo de fraude de ley por sucesión de contratos temporales"
                        ],
                        "emma_confidence": 0.95
                    },
                    "execution_plan": {
                        "execution_steps": [
                            "1. Analizar historial de rendimiento empleado",
                            "2. Evaluar necesidad operativa del puesto",
                            "3. Tomar decisión renovación basada en datos",
                            "4. Generar documentos apropiados",
                            "5. Ejecutar workflow seleccionado"
                        ],
                        "timeline": {"total_duration": "15 días laborables"},
                        "stakeholders": {
                            "RRHH": "Coordinador del proceso",
                            "Manager": "Evaluador de rendimiento",
                            "Empleado": "Beneficiario del contrato",
                            "Legal": "Revisor de cumplimiento normativo"
                        },
                        "automated_actions": [
                            "Análisis de rendimiento vía API HRIS",
                            "Generación de contratos desde plantillas",
                            "Envío de notificaciones automáticas",
                            "Actualización de registros sistema"
                        ]
                    },
                    "created_at": datetime.utcnow().isoformat()
                },
                "execution_result": {
                    "steps_completed": 5,
                    "total_steps": 5,
                    "execution_log": [
                        {
                            "step_number": 0,
                            "step_description": "1. Analizar rendimiento empleado",
                            "result": {
                                "success": True,
                                "result": "✅ Análisis completado: Rendimiento EXCELENTE (95/100)",
                                "decision": "renovar",
                                "next_action": "Evaluar necesidad operativa",
                                "confidence": 0.97
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        },
                        {
                            "step_number": 1,
                            "step_description": "2. Evaluar necesidad operativa",
                            "result": {
                                "success": True,
                                "result": "✅ Necesidad confirmada: Puesto crítico para equipo desarrollo",
                                "decision": "renovar",
                                "next_action": "Proceder con renovación",
                                "confidence": 0.92
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        },
                        {
                            "step_number": 2,
                            "step_description": "3. Tomar decisión renovación",
                            "result": {
                                "success": True,
                                "result": "✅ DECISIÓN: RENOVAR contrato por 12 meses más",
                                "decision": "renovar",
                                "next_action": "Generar nuevo contrato",
                                "confidence": 0.98
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        },
                        {
                            "step_number": 3,
                            "step_description": "4. Generar documentos apropiados",
                            "result": {
                                "success": True,
                                "result": "✅ Contrato renovación generado con mejora salarial 8%",
                                "decision": "renovar",
                                "next_action": "Enviar para firma",
                                "confidence": 0.94
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        },
                        {
                            "step_number": 4,
                            "step_description": "5. Ejecutar proceso seleccionado",
                            "result": {
                                "success": True,
                                "result": "✅ Proceso completado: Contrato enviado a Ana González para firma digital",
                                "decision": "renovar",
                                "next_action": "Monitorear firma",
                                "confidence": 1.0
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        }
                    ],
                    "final_decision": "RENOVAR - Empleado de alto rendimiento en puesto crítico"
                },
                "completed_at": datetime.utcnow().isoformat()
            }
        else:
            # DEMO COMPLETO: Llamadas reales a Ollama (~30 segundos)
            logger.info("🐌 Full demo mode: usando Ollama real (puede tardar ~30 segundos)")
            
            # Generar BPMN con llamadas reales a microservicios
            result = await bpmn_ai_service.generate_contract_renewal_bpmn(
                contract_data=demo_contract_data,
                tenant_id="demo_tenant"
            )
            
            return {
                "success": True,
                "message": "Demo de renovación de contrato completado (FULL OLLAMA)",
                "demo_data": demo_contract_data,
                "performance_note": "🐌 Full mode: ~30 segundos con Ollama real",
                "architecture_note": "✅ Refactorizado: API Core -> Ollama Service (arquitectura correcta)",
                "bpmn_generation": result,
                "execution_result": {
                    "steps_completed": 1,
                    "total_steps": 1,
                    "execution_log": [
                        {
                            "step_number": 0,
                            "step_description": "BPMN generado via Ollama service",
                            "result": {"success": True, "decision": "generado"},
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "completed"
                        }
                    ],
                    "final_decision": "BPMN generado exitosamente"
                },
                "completed_at": datetime.utcnow().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Demo execution failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Error en demo de renovación",
                "error": str(e)
            }
        )


async def _execute_contract_renewal_background(
    contract_id: str,
    tenant_id: str,
    user_id: str
):
    """Ejecuta proceso de renovación en background"""
    try:
        logger.info(f"Background execution started for contract {contract_id}")
        
        result = await bpmn_ai_service.execute_contract_renewal_process(
            contract_id=contract_id,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        logger.info(f"Background execution completed for contract {contract_id}: {result['success']}")
        
        # TODO: Notificar resultado al usuario (webhook, websocket, etc.)
        
    except Exception as e:
        logger.error(f"Background execution failed for contract {contract_id}: {e}")