"""
Agent Execution Service with Streaming and Background Processing
"""
import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional, List
from uuid import UUID, uuid4
from enum import Enum
from sqlalchemy.orm import Session

from app.services.agent_service import AgentService
from app.services.digital_signature_agent import DigitalSignatureAgent
from app.services.langchain_client import LangChainClient
from app.db.models import Agent, AgentExecution
from app.schemas.agent import ExecutionCreate

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Estados de ejecución"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentExecutionService:
    """Servicio para ejecutar agentes con streaming y procesamiento en background"""
    
    def __init__(self, db: Session):
        self.db = db
        self.agent_service = AgentService(db)
        self.active_executions: Dict[str, Dict[str, Any]] = {}
    
    async def execute_agent_streaming(
        self,
        agent_id: UUID,
        task_type: str,
        parameters: Dict[str, Any],
        tenant_id: UUID,
        user_id: UUID,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar agente con streaming de resultados"""
        
        execution_id = str(uuid4())
        
        try:
            # Verificar acceso al agente
            agent = self.agent_service.get_agent(agent_id, tenant_id)
            if not agent:
                yield {
                    "type": "error",
                    "execution_id": execution_id,
                    "content": "Agent not found",
                    "timestamp": datetime.now().isoformat()
                }
                return
            
            if not agent.is_public and agent.created_by != user_id:
                yield {
                    "type": "error",
                    "execution_id": execution_id,
                    "content": "Access denied to private agent",
                    "timestamp": datetime.now().isoformat()
                }
                return
            
            # Crear registro de ejecución
            execution_data = ExecutionCreate(
                agent_id=agent_id,
                task_type=task_type,
                input_data={
                    "parameters": parameters,
                    "context": context or {}
                }
            )
            
            execution = self.agent_service.create_execution(
                execution_data, tenant_id, user_id
            )
            
            # Registrar ejecución activa
            self.active_executions[execution_id] = {
                "execution_id": execution.id,
                "agent_id": agent_id,
                "status": ExecutionStatus.PENDING,
                "start_time": datetime.now(),
                "agent_type": agent.type
            }
            
            yield {
                "type": "execution_started",
                "execution_id": execution_id,
                "db_execution_id": str(execution.id),
                "agent_id": str(agent_id),
                "agent_name": agent.name,
                "task_type": task_type,
                "timestamp": datetime.now().isoformat()
            }
            
            # Actualizar estado a running
            self.agent_service.update_execution_status(execution.id, "running")
            self.active_executions[execution_id]["status"] = ExecutionStatus.RUNNING
            
            # Ejecutar según el tipo de agente
            if agent.type == "digital_signature":
                async for result in self._execute_signature_agent(
                    execution_id, agent_id, tenant_id, user_id, task_type, parameters, context
                ):
                    yield result
            elif agent.type == "document_analyzer":
                async for result in self._execute_document_analyzer(
                    execution_id, agent_id, tenant_id, user_id, task_type, parameters, context
                ):
                    yield result
            else:
                async for result in self._execute_generic_agent(
                    execution_id, agent_id, tenant_id, user_id, task_type, parameters, context
                ):
                    yield result
            
            # Marcar como completado
            if execution_id in self.active_executions:
                self.active_executions[execution_id]["status"] = ExecutionStatus.COMPLETED
                self.agent_service.update_execution_status(
                    execution.id, 
                    "completed",
                    output_data={"execution_id": execution_id}
                )
            
            yield {
                "type": "execution_completed",
                "execution_id": execution_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in agent execution: {str(e)}")
            
            # Marcar como fallido
            if execution_id in self.active_executions:
                self.active_executions[execution_id]["status"] = ExecutionStatus.FAILED
                db_execution_id = self.active_executions[execution_id].get("execution_id")
                if db_execution_id:
                    self.agent_service.update_execution_status(
                        db_execution_id,
                        "failed",
                        error_message=str(e)
                    )
            
            yield {
                "type": "execution_error",
                "execution_id": execution_id,
                "content": str(e),
                "timestamp": datetime.now().isoformat()
            }
        
        finally:
            # Limpiar ejecución activa
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]
    
    async def _execute_signature_agent(
        self,
        execution_id: str,
        agent_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar agente de firma digital"""
        
        try:
            signature_agent = DigitalSignatureAgent(self.db, agent_id, tenant_id)
            
            # Determinar acción según task_type
            if task_type == "create_signature_request":
                yield {
                    "type": "task_progress",
                    "execution_id": execution_id,
                    "content": "Creando solicitud de firma...",
                    "progress": 10,
                    "timestamp": datetime.now().isoformat()
                }
                
                result = await signature_agent._create_signature_request(parameters, user_id)
                
                yield {
                    "type": "task_result",
                    "execution_id": execution_id,
                    "task_type": task_type,
                    "result": result,
                    "progress": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
            elif task_type == "get_signature_status":
                yield {
                    "type": "task_progress",
                    "execution_id": execution_id,
                    "content": "Consultando estado de firma...",
                    "progress": 50,
                    "timestamp": datetime.now().isoformat()
                }
                
                result = await signature_agent._get_signature_status(parameters, user_id)
                
                yield {
                    "type": "task_result",
                    "execution_id": execution_id,
                    "task_type": task_type,
                    "result": result,
                    "progress": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
            elif task_type == "list_signature_requests":
                result = await signature_agent._list_signature_requests(parameters, user_id)
                
                yield {
                    "type": "task_result",
                    "execution_id": execution_id,
                    "task_type": task_type,
                    "result": result,
                    "progress": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
            else:
                yield {
                    "type": "task_error",
                    "execution_id": execution_id,
                    "content": f"Task type '{task_type}' not supported for signature agent",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error executing signature agent: {str(e)}")
            yield {
                "type": "task_error",
                "execution_id": execution_id,
                "content": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _execute_document_analyzer(
        self,
        execution_id: str,
        agent_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar agente analizador de documentos"""
        
        try:
            yield {
                "type": "task_progress",
                "execution_id": execution_id,
                "content": "Iniciando análisis de documentos...",
                "progress": 10,
                "timestamp": datetime.now().isoformat()
            }
            
            # Usar LangChain para análisis
            async with LangChainClient() as client:
                
                if task_type == "analyze_document":
                    document_content = parameters.get("document_content", "")
                    analysis_type = parameters.get("analysis_type", "general")
                    
                    yield {
                        "type": "task_progress",
                        "execution_id": execution_id,
                        "content": f"Analizando documento ({analysis_type})...",
                        "progress": 30,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    # Preparar prompt según tipo de análisis
                    if analysis_type == "summary":
                        prompt = f"Resume el siguiente documento:\n\n{document_content}"
                    elif analysis_type == "keywords":
                        prompt = f"Extrae las palabras clave más importantes del siguiente documento:\n\n{document_content}"
                    elif analysis_type == "sentiment":
                        prompt = f"Analiza el sentimiento del siguiente documento:\n\n{document_content}"
                    else:
                        prompt = f"Analiza el siguiente documento de manera general:\n\n{document_content}"
                    
                    yield {
                        "type": "task_progress",
                        "execution_id": execution_id,
                        "content": "Procesando con IA...",
                        "progress": 60,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    response = await client.generate_response(
                        query=prompt,
                        tenant_id=str(tenant_id),
                        max_tokens=1000
                    )
                    
                    result = {
                        "analysis_type": analysis_type,
                        "analysis": response.get("answer", ""),
                        "sources": response.get("sources", []),
                        "confidence": 0.85  # Simulado
                    }
                    
                elif task_type == "search_documents":
                    query = parameters.get("query", "")
                    
                    yield {
                        "type": "task_progress",
                        "execution_id": execution_id,
                        "content": f"Buscando documentos: '{query}'...",
                        "progress": 50,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    search_results = await client.search_similar(
                        tenant_id=str(tenant_id),
                        query=query,
                        limit=parameters.get("limit", 10)
                    )
                    
                    result = {
                        "query": query,
                        "documents": search_results,
                        "total_found": len(search_results)
                    }
                
                else:
                    result = {"error": f"Task type '{task_type}' not supported"}
                
                yield {
                    "type": "task_result",
                    "execution_id": execution_id,
                    "task_type": task_type,
                    "result": result,
                    "progress": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error executing document analyzer: {str(e)}")
            yield {
                "type": "task_error",
                "execution_id": execution_id,
                "content": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _execute_generic_agent(
        self,
        execution_id: str,
        agent_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar agente genérico"""
        
        try:
            yield {
                "type": "task_progress",
                "execution_id": execution_id,
                "content": "Ejecutando tarea genérica...",
                "progress": 30,
                "timestamp": datetime.now().isoformat()
            }
            
            # Simular procesamiento
            await asyncio.sleep(1)
            
            yield {
                "type": "task_progress",
                "execution_id": execution_id,
                "content": "Procesando con IA...",
                "progress": 70,
                "timestamp": datetime.now().isoformat()
            }
            
            # Usar LangChain para generar respuesta
            async with LangChainClient() as client:
                prompt = f"""Ejecuta la siguiente tarea:
                
Tipo de tarea: {task_type}
Parámetros: {json.dumps(parameters, indent=2)}
Contexto: {json.dumps(context, indent=2)}

Proporciona una respuesta detallada y útil."""
                
                response = await client.generate_response(
                    query=prompt,
                    tenant_id=str(tenant_id),
                    max_tokens=800
                )
                
                result = {
                    "task_type": task_type,
                    "response": response.get("answer", ""),
                    "parameters_used": parameters,
                    "sources": response.get("sources", [])
                }
                
                yield {
                    "type": "task_result",
                    "execution_id": execution_id,
                    "task_type": task_type,
                    "result": result,
                    "progress": 100,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error executing generic agent: {str(e)}")
            yield {
                "type": "task_error",
                "execution_id": execution_id,
                "content": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_active_executions(self, user_id: UUID = None) -> List[Dict[str, Any]]:
        """Obtener ejecuciones activas"""
        executions = []
        for exec_id, exec_data in self.active_executions.items():
            executions.append({
                "execution_id": exec_id,
                "agent_id": str(exec_data["agent_id"]),
                "status": exec_data["status"].value,
                "start_time": exec_data["start_time"].isoformat(),
                "agent_type": exec_data["agent_type"]
            })
        return executions
    
    def cancel_execution(self, execution_id: str) -> bool:
        """Cancelar una ejecución activa"""
        if execution_id in self.active_executions:
            self.active_executions[execution_id]["status"] = ExecutionStatus.CANCELLED
            
            # Actualizar en base de datos
            db_execution_id = self.active_executions[execution_id].get("execution_id")
            if db_execution_id:
                self.agent_service.update_execution_status(
                    db_execution_id,
                    "cancelled",
                    error_message="Execution cancelled by user"
                )
            
            return True
        return False
    
    async def execute_batch_tasks(
        self,
        agent_id: UUID,
        tasks: List[Dict[str, Any]],
        tenant_id: UUID,
        user_id: UUID
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ejecutar múltiples tareas en lote"""
        
        batch_id = str(uuid4())
        total_tasks = len(tasks)
        
        yield {
            "type": "batch_started",
            "batch_id": batch_id,
            "total_tasks": total_tasks,
            "agent_id": str(agent_id),
            "timestamp": datetime.now().isoformat()
        }
        
        completed_tasks = 0
        failed_tasks = 0
        
        for i, task in enumerate(tasks):
            task_id = f"{batch_id}_task_{i}"
            
            yield {
                "type": "batch_progress",
                "batch_id": batch_id,
                "task_id": task_id,
                "task_index": i,
                "total_tasks": total_tasks,
                "content": f"Ejecutando tarea {i+1}/{total_tasks}...",
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                # Ejecutar tarea individual
                task_results = []
                async for result in self.execute_agent_streaming(
                    agent_id=agent_id,
                    task_type=task.get("task_type", "generic"),
                    parameters=task.get("parameters", {}),
                    tenant_id=tenant_id,
                    user_id=user_id,
                    context=task.get("context", {})
                ):
                    if result.get("type") == "task_result":
                        task_results.append(result)
                
                completed_tasks += 1
                
                yield {
                    "type": "batch_task_completed",
                    "batch_id": batch_id,
                    "task_id": task_id,
                    "task_index": i,
                    "results": task_results,
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                failed_tasks += 1
                logger.error(f"Error in batch task {i}: {str(e)}")
                
                yield {
                    "type": "batch_task_failed",
                    "batch_id": batch_id,
                    "task_id": task_id,
                    "task_index": i,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
        
        # Resumen final del lote
        yield {
            "type": "batch_completed",
            "batch_id": batch_id,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0,
            "timestamp": datetime.now().isoformat()
        }