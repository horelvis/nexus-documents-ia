"""
BPM AI Service - Integración de modelos especializados BPM con Emma AI
Prototipo para renovación de contratos laborales
"""
import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import (
        AutoTokenizer, 
        AutoModelForSeq2SeqLM, 
        AutoModelForTokenClassification,
        pipeline
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers not available, using fallback implementation")

from .elysia_service import ElysiaService


class BPMNAIService:
    """Servicio que integra modelos BPM especializados con Emma AI"""
    
    def __init__(self):
        self.emma = None
        self.txt2bpmn_model = None
        self.txt2bpmn_tokenizer = None
        self.bpmn_extractor = None
        self._initialized = False
        
    async def initialize(self):
        """Inicializa los modelos BPM y Emma AI"""
        if self._initialized:
            return
            
        try:
            # Inicializar Emma AI
            from .elysia_service import elysia_service
            self.emma = elysia_service
            
            if TRANSFORMERS_AVAILABLE:
                # Cargar modelo TXT2BPMN (con fallback si no está disponible)
                try:
                    logger.info("Loading TXT2BPMN model...")
                    self.txt2bpmn_tokenizer = AutoTokenizer.from_pretrained("fachati/TXT2BPMN")
                    self.txt2bpmn_model = AutoModelForSeq2SeqLM.from_pretrained("fachati/TXT2BPMN")
                    
                    # Cargar modelo de extracción BPMN
                    logger.info("Loading BPMN extraction model...")
                    self.bpmn_extractor = pipeline(
                        "token-classification",
                        model="jtlicardo/bpmn-information-extraction",
                        tokenizer="jtlicardo/bpmn-information-extraction",
                        aggregation_strategy="simple"
                    )
                    
                    logger.info("BPM models loaded successfully")
                except Exception as e:
                    logger.warning(f"Could not load HuggingFace models: {e}")
                    self.txt2bpmn_model = None
                    self.bpmn_extractor = None
            else:
                logger.info("Using fallback BPM implementation")
                
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Error initializing BPM AI Service: {e}")
            raise
    
    async def generate_contract_renewal_bpmn(
        self,
        contract_data: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Genera BPMN para proceso de renovación de contrato"""
        
        if not self._initialized:
            await self.initialize()
        
        # 1. Crear descripción del proceso de renovación
        process_description = self._create_renewal_description(contract_data)
        
        # 2. Extraer elementos del proceso usando modelo especializado
        extracted_elements = await self._extract_bpmn_elements(process_description)
        
        # 3. Generar BPMN usando modelo TXT2BPMN
        generated_bpmn = await self._generate_bpmn_diagram(process_description)
        
        # 4. Emma AI valida y optimiza para normativa española
        validated_bpmn = await self._emma_validate_and_optimize(
            generated_bpmn, contract_data, tenant_id
        )
        
        # 5. Crear plan de ejecución
        execution_plan = await self._create_execution_plan(validated_bpmn, contract_data, tenant_id)
        
        return {
            "contract_id": contract_data.get("contract_id"),
            "process_description": process_description,
            "extracted_elements": extracted_elements,
            "generated_bpmn": generated_bpmn,
            "validated_bpmn": validated_bpmn,
            "execution_plan": execution_plan,
            "created_at": datetime.utcnow().isoformat()
        }
    
    def _create_renewal_description(self, contract_data: Dict[str, Any]) -> str:
        """Crea descripción estructurada del proceso de renovación"""
        
        employee_name = contract_data.get("employee_name", "empleado")
        contract_type = contract_data.get("contract_type", "temporal")
        expiration_date = contract_data.get("expiration_date", "próximamente")
        
        description = f"""
        Proceso de renovación de contrato {contract_type} para {employee_name} que vence {expiration_date}:
        
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
        12. Para terminación: se calcula liquidación y se programa finiquito
        """
        
        return description.strip()
    
    async def _extract_bpmn_elements(self, description: str) -> Dict[str, Any]:
        """Extrae elementos BPM usando modelo especializado"""
        
        if self.bpmn_extractor:
            try:
                # Usar modelo BERT especializado para extraer elementos
                elements = self.bpmn_extractor(description)
                
                # Procesar y estructurar elementos
                structured_elements = {
                    "agents": [],
                    "tasks": [],
                    "conditions": [],
                    "process_info": []
                }
                
                for element in elements:
                    label = element.get("entity_group", "").lower()
                    text = element.get("word", "")
                    confidence = element.get("score", 0.0)
                    
                    if label == "agent":
                        structured_elements["agents"].append({
                            "name": text,
                            "confidence": confidence
                        })
                    elif label == "task":
                        structured_elements["tasks"].append({
                            "description": text,
                            "confidence": confidence
                        })
                    elif label == "condition":
                        structured_elements["conditions"].append({
                            "condition": text,
                            "confidence": confidence
                        })
                    elif label in ["process_info", "task_info"]:
                        structured_elements["process_info"].append({
                            "info": text,
                            "confidence": confidence
                        })
                
                return structured_elements
                
            except Exception as e:
                logger.error(f"Error extracting BPMN elements: {e}")
        
        # Fallback: extracción simple con reglas
        return {
            "agents": [
                {"name": "RRHH", "confidence": 1.0},
                {"name": "Manager", "confidence": 1.0},
                {"name": "Empleado", "confidence": 1.0}
            ],
            "tasks": [
                {"description": "Analizar rendimiento", "confidence": 1.0},
                {"description": "Evaluar necesidad operativa", "confidence": 1.0},
                {"description": "Generar contrato", "confidence": 1.0},
                {"description": "Enviar para firma", "confidence": 1.0}
            ],
            "conditions": [
                {"condition": "evaluación positiva", "confidence": 1.0},
                {"condition": "necesidad operativa", "confidence": 1.0}
            ],
            "process_info": [
                {"info": "30 días antes del vencimiento", "confidence": 1.0},
                {"info": "7 días para respuesta", "confidence": 1.0}
            ]
        }
    
    async def _generate_bpmn_diagram(self, description: str) -> str:
        """Genera diagrama BPMN usando modelo TXT2BPMN"""
        
        if self.txt2bpmn_model and self.txt2bpmn_tokenizer:
            try:
                # Tokenizar descripción
                inputs = self.txt2bpmn_tokenizer(
                    description,
                    return_tensors="pt",
                    max_length=512,
                    truncation=True,
                    padding=True
                )
                
                # Generar BPMN
                with torch.no_grad():
                    outputs = self.txt2bpmn_model.generate(
                        inputs.input_ids,
                        max_length=1024,
                        num_beams=4,
                        early_stopping=True,
                        pad_token_id=self.txt2bpmn_tokenizer.eos_token_id
                    )
                
                # Decodificar resultado
                bpmn_diagram = self.txt2bpmn_tokenizer.decode(
                    outputs[0], 
                    skip_special_tokens=True
                )
                
                return bpmn_diagram
                
            except Exception as e:
                logger.error(f"Error generating BPMN with model: {e}")
        
        # Fallback: BPMN simplificado para renovación de contratos
        return """
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
        """
    
    async def _emma_validate_and_optimize(
        self,
        bpmn_diagram: str,
        contract_data: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Emma AI valida y optimiza BPMN para normativa española"""
        
        validation_prompt = f"""
        Valida y optimiza este proceso BPMN para renovación de contrato laboral en España:

        PROCESO BPMN GENERADO:
        {bpmn_diagram}

        DATOS DEL CONTRATO:
        {json.dumps(contract_data, indent=2)}

        VALIDACIONES REQUERIDAS:
        1. Cumplimiento Estatuto de los Trabajadores
        2. Plazos legales para notificaciones
        3. Derechos del trabajador en el proceso
        4. Documentación obligatoria
        5. Procedimientos de la empresa (tenant {tenant_id})

        OPTIMIZACIONES:
        1. Añadir checkpoints de cumplimiento legal
        2. Incluir timeouts apropiados
        3. Manejar excepciones y escalaciones
        4. Definir documentos generados en cada paso
        5. Asegurar trazabilidad completa

        Proporciona:
        - BPMN optimizado con mejoras específicas
        - Lista de puntos de cumplimiento legal añadidos
        - Recomendaciones para la implementación
        - Riesgos identificados y mitigaciones
        """
        
        try:
            from ..schemas.elysia import ElysiaQuery
            
            elysia_query = ElysiaQuery(
                query=validation_prompt,
                tenant_id=tenant_id,
                enable_debug=False
            )
            
            validation_result = await self.emma.execute_query(elysia_query)
            
            return {
                "original_bpmn": bpmn_diagram,
                "optimized_bpmn": validation_result.get("optimized_bpmn", bpmn_diagram),
                "legal_compliance_points": validation_result.get("compliance_points", []),
                "recommendations": validation_result.get("recommendations", []),
                "identified_risks": validation_result.get("risks", []),
                "emma_confidence": validation_result.get("confidence", 0.8)
            }
            
        except Exception as e:
            logger.error(f"Error validating with Emma AI: {e}")
            return {
                "original_bpmn": bpmn_diagram,
                "optimized_bpmn": bpmn_diagram,
                "legal_compliance_points": ["Validación manual requerida"],
                "recommendations": ["Revisar con equipo legal"],
                "identified_risks": ["Validación automática falló"],
                "emma_confidence": 0.5
            }
    
    async def _create_execution_plan(
        self,
        validated_bpmn: Dict[str, Any],
        contract_data: Dict[str, Any],
        tenant_id: str
    ) -> Dict[str, Any]:
        """Crea plan de ejecución específico para el contrato"""
        
        execution_prompt = f"""
        Crea plan de ejecución detallado para este proceso de renovación:

        BPMN VALIDADO:
        {validated_bpmn.get('optimized_bpmn', '')}

        CONTRATO:
        {json.dumps(contract_data, indent=2)}

        PLAN REQUERIDO:
        1. Secuencia exacta de pasos con responsables
        2. Timeouts y deadlines específicos
        3. Documentos a generar en cada paso
        4. Puntos de decisión con criterios claros
        5. Acciones automáticas vs manuales
        6. Notificaciones y comunicaciones
        7. Contingencias y escalaciones

        Formato: Lista estructurada con timing específico
        """
        
        try:
            from ..schemas.elysia import ElysiaQuery
            
            elysia_query = ElysiaQuery(
                query=execution_prompt,
                tenant_id=tenant_id,
                enable_debug=False
            )
            
            plan_result = await self.emma.execute_query(elysia_query)
            
            return {
                "execution_steps": plan_result.get("steps", []),
                "timeline": plan_result.get("timeline", {}),
                "stakeholders": plan_result.get("stakeholders", {}),
                "documents_to_generate": plan_result.get("documents", []),
                "decision_criteria": plan_result.get("decision_criteria", {}),
                "automated_actions": plan_result.get("automated_actions", []),
                "manual_actions": plan_result.get("manual_actions", [])
            }
            
        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            return {
                "execution_steps": [
                    "1. Analizar rendimiento empleado",
                    "2. Evaluar necesidad operativa", 
                    "3. Tomar decisión renovación",
                    "4. Generar documentos apropiados",
                    "5. Ejecutar proceso seleccionado"
                ],
                "timeline": {"total_duration": "15 días"},
                "stakeholders": {"RRHH": "Coordinador", "Manager": "Evaluador", "Empleado": "Beneficiario"},
                "error": str(e)
            }
    
    async def execute_contract_renewal_process(
        self,
        contract_id: str,
        tenant_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Ejecuta el proceso completo de renovación de contrato"""
        
        try:
            # 1. Obtener datos del contrato (mock para prototipo)
            contract_data = await self._get_contract_data(contract_id, tenant_id)
            
            # 2. Generar y validar BPMN
            bpmn_result = await self.generate_contract_renewal_bpmn(contract_data, tenant_id)
            
            # 3. Ejecutar plan paso a paso
            execution_result = await self._execute_process_plan(
                bpmn_result["execution_plan"],
                contract_data,
                tenant_id,
                user_id
            )
            
            return {
                "success": True,
                "contract_id": contract_id,
                "process_type": "contract_renewal",
                "bpmn_generation": bpmn_result,
                "execution_result": execution_result,
                "completed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error executing contract renewal process: {e}")
            return {
                "success": False,
                "contract_id": contract_id,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _get_contract_data(self, contract_id: str, tenant_id: str) -> Dict[str, Any]:
        """Obtiene datos del contrato (mock para prototipo)"""
        
        # TODO: Integrar con base de datos real
        return {
            "contract_id": contract_id,
            "tenant_id": tenant_id,
            "employee_name": "Juan Pérez",
            "employee_id": "emp_001",
            "contract_type": "temporal",
            "start_date": "2024-01-15",
            "expiration_date": "2025-01-15",
            "position": "Analista Junior",
            "department": "IT",
            "manager": "María García",
            "current_salary": 35000,
            "performance_rating": "Satisfactorio",
            "attendance_score": 95,
            "contract_extensions": 1,
            "original_contract_date": "2023-01-15"
        }
    
    async def _execute_process_plan(
        self,
        execution_plan: Dict[str, Any],
        contract_data: Dict[str, Any],
        tenant_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Ejecuta el plan de proceso con Emma AI"""
        
        execution_log = []
        current_step = 0
        
        steps = execution_plan.get("execution_steps", [])
        
        for step in steps:
            try:
                step_result = await self._execute_single_step(
                    step,
                    current_step,
                    contract_data,
                    execution_log,
                    tenant_id
                )
                
                execution_log.append({
                    "step_number": current_step,
                    "step_description": step,
                    "result": step_result,
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "completed" if step_result.get("success") else "failed"
                })
                
                current_step += 1
                
                # Simular delay entre pasos
                await asyncio.sleep(0.1)
                
            except Exception as e:
                execution_log.append({
                    "step_number": current_step,
                    "step_description": step,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "error"
                })
                break
        
        return {
            "steps_completed": current_step,
            "total_steps": len(steps),
            "execution_log": execution_log,
            "final_decision": execution_log[-1].get("result", {}).get("decision", "pending") if execution_log else "error"
        }
    
    async def _execute_single_step(
        self,
        step_description: str,
        step_number: int,
        contract_data: Dict[str, Any],
        previous_results: List[Dict[str, Any]],
        tenant_id: str = "default"
    ) -> Dict[str, Any]:
        """Ejecuta un paso individual del proceso usando Emma AI"""
        
        step_prompt = f"""
        Ejecuta este paso del proceso de renovación de contrato:

        PASO {step_number + 1}: {step_description}

        CONTEXTO DEL CONTRATO:
        {json.dumps(contract_data, indent=2)}

        RESULTADOS PREVIOS:
        {json.dumps(previous_results[-3:] if len(previous_results) > 3 else previous_results, indent=2)}

        INSTRUCCIONES:
        1. Analiza la información disponible
        2. Ejecuta la acción específica del paso
        3. Proporciona resultado concreto
        4. Si es un punto de decisión, toma la decisión basada en datos
        5. Sugiere siguiente acción si aplica

        Responde con estructura JSON que incluya:
        - success: boolean
        - result: descripción del resultado
        - decision: si aplica (renovar/no_renovar/pendiente)
        - next_action: qué hacer después
        - confidence: nivel de confianza (0-1)
        """
        
        try:
            from ..schemas.elysia import ElysiaQuery
            
            elysia_query = ElysiaQuery(
                query=step_prompt,
                tenant_id=tenant_id,
                enable_debug=False
            )
            
            step_result = await self.emma.execute_query(elysia_query)
            
            return {
                "success": True,
                "result": step_result.get("result", f"Completado paso: {step_description}"),
                "decision": step_result.get("decision", "N/A"),
                "next_action": step_result.get("next_action", "Continuar con siguiente paso"),
                "confidence": step_result.get("confidence", 0.8),
                "emma_reasoning": step_result.get("reasoning", "")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": f"Error ejecutando: {step_description}"
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado del servicio BPM AI"""
        
        try:
            if not self._initialized:
                await self.initialize()
            
            status = {
                "service": "bpmn_ai_service",
                "initialized": self._initialized,
                "transformers_available": TRANSFORMERS_AVAILABLE,
                "models_loaded": {
                    "txt2bpmn": self.txt2bpmn_model is not None,
                    "bpmn_extractor": self.bpmn_extractor is not None,
                    "emma_ai": self.emma is not None
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Test Emma AI
            if self.emma:
                try:
                    from ..schemas.elysia import ElysiaQuery
                    
                    test_query = ElysiaQuery(
                        query="Test health check",
                        tenant_id="health",
                        enable_debug=False
                    )
                    
                    test_response = await self.emma.execute_query(test_query)
                    status["emma_test"] = "OK"
                except Exception as e:
                    status["emma_test"] = f"Error: {e}"
            
            return status
            
        except Exception as e:
            return {
                "service": "bpmn_ai_service",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Instancia global del servicio
bpmn_ai_service = BPMNAIService()