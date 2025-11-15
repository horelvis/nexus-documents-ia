"""
AI Agent Activities for Temporal Workflows
Based on temporal-ai-agent patterns for intelligent workflow execution
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from temporalio import activity
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Agent state management"""
    agent_id: str
    conversation_history: List[Dict[str, Any]]
    current_context: Dict[str, Any]
    memory: Dict[str, Any]
    tools_available: List[str]
    last_action: Optional[Dict[str, Any]] = None
    created_at: str = None
    updated_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


@dataclass
class AgentInput:
    """Input for AI agent activities"""
    agent_type: str
    task_description: str
    context: Dict[str, Any]
    user_input: str
    agent_state: Optional[Dict[str, Any]] = None
    tools_config: Optional[Dict[str, Any]] = None


@dataclass
class AgentResult:
    """Result from AI agent activities"""
    success: bool
    agent_response: str
    actions_taken: List[Dict[str, Any]]
    updated_state: Dict[str, Any]
    recommendations: List[str]
    context_updates: Dict[str, Any]
    requires_human_input: bool = False
    error_message: Optional[str] = None


class EmmaAIAgentClient:
    """Client for interacting with Emma AI via Weaviate service"""
    
    def __init__(self):
        self.base_url = f"http://weaviate-service:{settings.weaviate_service_port}"
        self.timeout = httpx.Timeout(60.0)
    
    async def query_emma(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Query Emma AI for intelligent responses"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/elysia/chat",
                    json={
                        "query": query,
                        "context": context,
                        "tenant_id": context.get("tenant_id", "default"),
                        "user_id": context.get("user_id", "system")
                    },
                    headers={"Authorization": f"Bearer {settings.MICROSERVICES_API_KEY}"}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Emma AI query failed: {response.status_code} - {response.text}")
                    return {"error": f"Emma AI query failed: {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"Error querying Emma AI: {e}")
            return {"error": f"Emma AI connection error: {str(e)}"}


@activity.defn
async def emma_legal_advisor_agent(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Emma AI Legal Advisor Agent - Provides legal consultation and advice
    """
    try:
        agent_input = AgentInput(**input_data)
        
        # Initialize or restore agent state
        if agent_input.agent_state:
            agent_state = AgentState(**agent_input.agent_state)
        else:
            agent_state = AgentState(
                agent_id=f"emma_legal_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                conversation_history=[],
                current_context=agent_input.context,
                memory={},
                tools_available=["legal_search", "case_analysis", "document_generation"]
            )
        
        # Add user input to conversation history
        agent_state.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": "user_input",
            "content": agent_input.user_input,
            "context": agent_input.context
        })
        
        # Query Emma AI for legal advice
        emma_client = EmmaAIAgentClient()
        
        # Prepare legal consultation query
        legal_query = f"""
        Como Emma AI, asesora legal especializada, necesito tu ayuda con:
        
        Consulta: {agent_input.user_input}
        
        Contexto del caso:
        - Tipo de caso: {agent_input.context.get('case_type', 'General')}
        - Cliente: {agent_input.context.get('client_name', 'No especificado')}
        - Descripción: {agent_input.context.get('description', 'No proporcionada')}
        
        Por favor, proporciona:
        1. Análisis legal preliminar
        2. Recomendaciones de acción
        3. Documentos necesarios
        4. Próximos pasos sugeridos
        """
        
        emma_response = await emma_client.query_emma(legal_query, agent_input.context)
        
        if "error" in emma_response:
            return asdict(AgentResult(
                success=False,
                agent_response=f"Error al consultar Emma AI: {emma_response['error']}",
                actions_taken=[],
                updated_state=asdict(agent_state),
                recommendations=[],
                context_updates={},
                error_message=emma_response["error"]
            ))
        
        # Process Emma's response
        actions_taken = [
            {
                "action": "legal_consultation",
                "timestamp": datetime.now().isoformat(),
                "details": "Consulta realizada con Emma AI para asesoría legal"
            }
        ]
        
        # Extract recommendations from Emma's response
        recommendations = [
            "Revisar documentación legal pertinente",
            "Considerar precedentes aplicables",
            "Evaluar estrategias legales disponibles"
        ]
        
        # Update agent state
        agent_state.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": "emma_response",
            "content": emma_response.get("response", "Sin respuesta"),
            "analysis": emma_response
        })
        
        agent_state.last_action = actions_taken[-1]
        agent_state.memory["last_consultation"] = {
            "query": agent_input.user_input,
            "response": emma_response,
            "timestamp": datetime.now().isoformat()
        }
        
        # Determine if human input is needed
        requires_human = "requiere revisión humana" in emma_response.get("response", "").lower()
        
        return asdict(AgentResult(
            success=True,
            agent_response=emma_response.get("response", "Consulta procesada exitosamente"),
            actions_taken=actions_taken,
            updated_state=asdict(agent_state),
            recommendations=recommendations,
            context_updates={
                "legal_analysis_completed": True,
                "emma_consultation_timestamp": datetime.now().isoformat(),
                "requires_legal_review": requires_human
            },
            requires_human_input=requires_human
        ))
        
    except Exception as e:
        logger.error(f"Error in Emma Legal Advisor Agent: {e}")
        return asdict(AgentResult(
            success=False,
            agent_response=f"Error interno del agente: {str(e)}",
            actions_taken=[],
            updated_state={},
            recommendations=[],
            context_updates={},
            error_message=str(e)
        ))


@activity.defn
async def emma_document_analyzer_agent(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Emma AI Document Analyzer Agent - Analyzes legal documents and extracts insights
    """
    try:
        agent_input = AgentInput(**input_data)
        
        # Initialize agent state
        if agent_input.agent_state:
            agent_state = AgentState(**agent_input.agent_state)
        else:
            agent_state = AgentState(
                agent_id=f"emma_doc_analyzer_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                conversation_history=[],
                current_context=agent_input.context,
                memory={},
                tools_available=["document_analysis", "entity_extraction", "summary_generation"]
            )
        
        emma_client = EmmaAIAgentClient()
        
        # Prepare document analysis query
        analysis_query = f"""
        Como Emma AI, necesito analizar el siguiente documento/contenido:
        
        Contenido: {agent_input.user_input}
        
        Contexto:
        {json.dumps(agent_input.context, indent=2, ensure_ascii=False)}
        
        Por favor, proporciona:
        1. Resumen ejecutivo del documento
        2. Entidades clave identificadas
        3. Puntos críticos o riesgos
        4. Recomendaciones de acción
        """
        
        emma_response = await emma_client.query_emma(analysis_query, agent_input.context)
        
        if "error" in emma_response:
            return asdict(AgentResult(
                success=False,
                agent_response=f"Error al analizar documento: {emma_response['error']}",
                actions_taken=[],
                updated_state=asdict(agent_state),
                recommendations=[],
                context_updates={},
                error_message=emma_response["error"]
            ))
        
        # Process analysis results
        actions_taken = [
            {
                "action": "document_analysis",
                "timestamp": datetime.now().isoformat(),
                "details": "Análisis de documento completado con Emma AI"
            }
        ]
        
        # Update agent state with analysis
        agent_state.conversation_history.append({
            "timestamp": datetime.now().isoformat(),
            "type": "document_analysis",
            "content": agent_input.user_input,
            "analysis_result": emma_response
        })
        
        agent_state.memory["document_analysis"] = {
            "analyzed_content": agent_input.user_input[:500] + "..." if len(agent_input.user_input) > 500 else agent_input.user_input,
            "analysis_result": emma_response,
            "timestamp": datetime.now().isoformat()
        }
        
        return asdict(AgentResult(
            success=True,
            agent_response=emma_response.get("response", "Análisis de documento completado"),
            actions_taken=actions_taken,
            updated_state=asdict(agent_state),
            recommendations=[
                "Revisar entidades identificadas",
                "Validar puntos críticos señalados",
                "Considerar acciones recomendadas"
            ],
            context_updates={
                "document_analyzed": True,
                "analysis_timestamp": datetime.now().isoformat(),
                "entities_extracted": emma_response.get("entities", [])
            }
        ))
        
    except Exception as e:
        logger.error(f"Error in Emma Document Analyzer Agent: {e}")
        return asdict(AgentResult(
            success=False,
            agent_response=f"Error en análisis de documento: {str(e)}",
            actions_taken=[],
            updated_state={},
            recommendations=[],
            context_updates={},
            error_message=str(e)
        ))


@activity.defn
async def multi_agent_coordinator(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Multi-Agent Coordinator - Orchestrates multiple AI agents for complex tasks
    """
    try:
        coordination_input = input_data
        
        # Define agent sequence based on task type
        task_type = coordination_input.get("task_type", "general")
        
        if task_type == "legal_case_analysis":
            agent_sequence = [
                {"agent": "emma_document_analyzer_agent", "input": coordination_input},
                {"agent": "emma_legal_advisor_agent", "input": coordination_input}
            ]
        else:
            agent_sequence = [
                {"agent": "emma_legal_advisor_agent", "input": coordination_input}
            ]
        
        # Execute agent sequence
        coordination_results = []
        combined_context = coordination_input.get("context", {})
        
        for agent_config in agent_sequence:
            # Prepare input for current agent
            agent_input = agent_config["input"].copy()
            agent_input["context"] = combined_context
            
            # Execute agent based on type
            if agent_config["agent"] == "emma_document_analyzer_agent":
                result = await emma_document_analyzer_agent(agent_input)
            elif agent_config["agent"] == "emma_legal_advisor_agent":
                result = await emma_legal_advisor_agent(agent_input)
            else:
                continue
            
            coordination_results.append({
                "agent": agent_config["agent"],
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
            # Update combined context with results
            if result["success"] and result["context_updates"]:
                combined_context.update(result["context_updates"])
        
        # Combine all results
        all_actions = []
        all_recommendations = []
        requires_human = False
        
        for coord_result in coordination_results:
            if coord_result["result"]["success"]:
                all_actions.extend(coord_result["result"]["actions_taken"])
                all_recommendations.extend(coord_result["result"]["recommendations"])
                if coord_result["result"]["requires_human_input"]:
                    requires_human = True
        
        return {
            "success": True,
            "coordination_results": coordination_results,
            "combined_actions": all_actions,
            "combined_recommendations": list(set(all_recommendations)),  # Remove duplicates
            "final_context": combined_context,
            "requires_human_input": requires_human,
            "coordination_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in Multi-Agent Coordinator: {e}")
        return {
            "success": False,
            "error": str(e),
            "coordination_results": [],
            "timestamp": datetime.now().isoformat()
        }


@activity.defn
async def agent_state_persistence(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agent State Persistence - Saves and retrieves agent states
    """
    try:
        operation = input_data.get("operation")  # "save" or "load"
        agent_id = input_data.get("agent_id")
        
        if operation == "save":
            agent_state = input_data.get("agent_state")
            # In a real implementation, this would save to a database
            # For now, we'll return success with timestamp
            return {
                "success": True,
                "operation": "save",
                "agent_id": agent_id,
                "saved_at": datetime.now().isoformat(),
                "message": f"Agent state saved for {agent_id}"
            }
            
        elif operation == "load":
            # In a real implementation, this would load from a database
            # For now, return a basic state structure
            return {
                "success": True,
                "operation": "load",
                "agent_id": agent_id,
                "agent_state": {
                    "agent_id": agent_id,
                    "conversation_history": [],
                    "current_context": {},
                    "memory": {},
                    "tools_available": [],
                    "loaded_at": datetime.now().isoformat()
                },
                "message": f"Agent state loaded for {agent_id}"
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown operation: {operation}",
                "agent_id": agent_id
            }
            
    except Exception as e:
        logger.error(f"Error in Agent State Persistence: {e}")
        return {
            "success": False,
            "error": str(e),
            "operation": input_data.get("operation"),
            "agent_id": input_data.get("agent_id")
        }


# Export all agent activities
def get_ai_agent_activities():
    """Return all AI agent activities for worker registration"""
    return [
        emma_legal_advisor_agent,
        emma_document_analyzer_agent,
        multi_agent_coordinator,
        agent_state_persistence
    ]
