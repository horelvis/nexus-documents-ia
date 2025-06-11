"""
Langroid Agent Service - Core service for managing Langroid-based agents
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator
import json

import langroid as lr
from langroid.agent.base import Agent
from langroid.agent.chat_agent import ChatAgent, ChatAgentConfig
from langroid.agent.task import Task

# Handle different Langroid versions with compatibility imports
try:
    # Try to use proper Ollama configuration
    from langroid.language_models.openai_gpt import OpenAIGPTConfig
    from langroid.language_models.base import LLMMessage, Role
    from langroid.utils.configuration import Settings
    from langroid.vector_store.qdrantdb import QdrantDBConfig
    USE_OLLAMA_CONFIG = True
except ImportError:
    try:
        # Fallback to older import paths
        from langroid.language_models.openai_gpt import OpenAIGPTConfig
        from langroid.language_models.base import LLMMessage, Role
        from langroid.utils.configuration import settings as Settings
        QdrantDBConfig = lr.vector_store.QdrantDBConfig
        USE_OLLAMA_CONFIG = True
    except ImportError:
        # Last resort compatibility
        import langroid.language_models as lm
        OpenAIGPTConfig = lm.OpenAIGPTConfig
        from langroid.language_models.base import LLMMessage, Role
        Settings = None
        QdrantDBConfig = lr.vector_store.QdrantDBConfig
        USE_OLLAMA_CONFIG = False

from app.core.config import settings as app_settings
from app.services.digital_signature_langroid_agent import DigitalSignatureLangroidAgent

logger = logging.getLogger(__name__)


class LangroidAgentService:
    """Service for managing Langroid agents"""
    
    def __init__(self):
        self.active_agents: Dict[str, Dict[str, Any]] = {}
        self.agent_classes = {
            "digital_signature": DigitalSignatureLangroidAgent,
            "document_analyzer": self._create_document_analyzer,
            "rag_assistant": self._create_rag_assistant,
            "generic": self._create_generic_agent
        }
        self.llm_config = None
    
    async def initialize(self):
        """Initialize the service"""
        logger.info("Initializing Langroid Agent Service...")
        
        # Configure LLM with minimal required parameters
        try:
            # Use minimal OpenAI config that works with Langroid
            self.llm_config = OpenAIGPTConfig(
                chat_model=app_settings.DEFAULT_LLM_MODEL,
                temperature=0.1,
                max_output_tokens=2000,
                # Use dummy API key since Ollama doesn't require authentication
                api_key="dummy-key-for-ollama"
            )
            logger.info(f"Configured LLM with model: {app_settings.DEFAULT_LLM_MODEL}")
        except Exception as e:
            logger.error(f"Failed to create LLM config: {e}")
            # Try even more minimal config
            self.llm_config = OpenAIGPTConfig()
        
        # Configure base vector store config (will be customized per tenant)
        try:
            self.base_vector_store_config = {
                "cloud": False,
                "host": app_settings.QDRANT_HOST,
                "port": app_settings.QDRANT_PORT,
                "storage_path": None,  # Use server mode
                "embedding_model": app_settings.DEFAULT_EMBEDDING_MODEL
            }
            logger.info(f"Configured vector store: {app_settings.QDRANT_HOST}:{app_settings.QDRANT_PORT}")
        except Exception as e:
            logger.error(f"Failed to configure vector store: {e}")
            self.base_vector_store_config = {"cloud": False}
        
        logger.info("Langroid Agent Service initialized successfully")
    
    def _get_tenant_vector_store_config(self, tenant_id: str):
        """Get vector store config isolated by tenant"""
        try:
            collection_name = f"nexus_langroid_agents_{tenant_id}"
            
            return QdrantDBConfig(
                **self.base_vector_store_config,
                collection_name=collection_name
            )
        except Exception as e:
            logger.warning(f"Failed to create vector store config for tenant {tenant_id}: {e}")
            # Return None to indicate no vector store available
            return None
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up Langroid Agent Service...")
        
        # Clean up all active agents
        for agent_id in list(self.active_agents.keys()):
            await self._cleanup_agent(agent_id)
        
        logger.info("Langroid Agent Service cleanup completed")
    
    async def create_agent(
        self,
        agent_type: str,
        tenant_id: str,
        user_id: str,
        configuration: Dict[str, Any] = None
    ) -> str:
        """Create a new agent instance"""
        
        if agent_type not in self.agent_classes:
            raise ValueError(f"Unsupported agent type: {agent_type}")
        
        agent_id = str(uuid.uuid4())
        config = configuration or {}
        
        try:
            # Create agent instance based on type
            if agent_type == "digital_signature":
                agent_instance = await self._create_signature_agent(
                    agent_id, tenant_id, user_id, config
                )
            else:
                agent_creator = self.agent_classes[agent_type]
                agent_instance = await agent_creator(
                    agent_id, tenant_id, user_id, config
                )
            
            # Store agent info
            self.active_agents[agent_id] = {
                "instance": agent_instance,
                "type": agent_type,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "configuration": config,
                "created_at": datetime.now(),
                "last_used": datetime.now()
            }
            
            logger.info(f"Created {agent_type} agent {agent_id} for tenant {tenant_id}")
            return agent_id
            
        except Exception as e:
            logger.error(f"Error creating agent: {str(e)}")
            raise
    
    async def delete_agent(self, agent_id: str, tenant_id: str) -> bool:
        """Delete an agent instance"""
        
        if agent_id not in self.active_agents:
            return False
        
        agent_info = self.active_agents[agent_id]
        
        # Verify tenant access
        if agent_info["tenant_id"] != tenant_id:
            raise PermissionError("Access denied to agent")
        
        await self._cleanup_agent(agent_id)
        return True
    
    async def list_agents(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all agents for a tenant"""
        
        agents = []
        for agent_id, agent_info in self.active_agents.items():
            if agent_info["tenant_id"] == tenant_id:
                agents.append({
                    "agent_id": agent_id,
                    "type": agent_info["type"],
                    "created_at": agent_info["created_at"].isoformat(),
                    "last_used": agent_info["last_used"].isoformat(),
                    "configuration": agent_info["configuration"]
                })
        
        return agents
    
    async def chat_with_agent(
        self,
        agent_id: str,
        tenant_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat with an agent and stream responses"""
        
        if agent_id not in self.active_agents:
            yield {
                "type": "error",
                "content": "Agent not found",
                "metadata": {"agent_id": agent_id}
            }
            return
        
        agent_info = self.active_agents[agent_id]
        
        # Verify tenant access
        if agent_info["tenant_id"] != tenant_id:
            yield {
                "type": "error",
                "content": "Access denied to agent",
                "metadata": {"agent_id": agent_id}
            }
            return
        
        # Update last used
        agent_info["last_used"] = datetime.now()
        
        try:
            agent_instance = agent_info["instance"]
            
            # Handle chat based on agent type
            if hasattr(agent_instance, 'chat_stream'):
                # Custom streaming method
                async for response in agent_instance.chat_stream(
                    message, conversation_id, context
                ):
                    yield response
            else:
                # Use Langroid Task for standard agents
                task = Task(agent_instance)
                
                # Run task and stream responses
                async for response in self._run_task_with_streaming(
                    task, message, context
                ):
                    yield response
                    
        except Exception as e:
            logger.error(f"Error in agent chat: {str(e)}")
            yield {
                "type": "error",
                "content": str(e),
                "metadata": {"agent_id": agent_id, "error_type": type(e).__name__}
            }
    
    async def execute_agent_task(
        self,
        agent_id: str,
        tenant_id: str,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a specific task with an agent"""
        
        if agent_id not in self.active_agents:
            yield {
                "type": "error",
                "content": "Agent not found",
                "metadata": {"agent_id": agent_id}
            }
            return
        
        agent_info = self.active_agents[agent_id]
        
        # Verify tenant access
        if agent_info["tenant_id"] != tenant_id:
            yield {
                "type": "error",
                "content": "Access denied to agent",
                "metadata": {"agent_id": agent_id}
            }
            return
        
        # Update last used
        agent_info["last_used"] = datetime.now()
        
        try:
            agent_instance = agent_info["instance"]
            
            yield {
                "type": "task_started",
                "content": f"Starting task: {task_type}",
                "metadata": {
                    "agent_id": agent_id,
                    "task_type": task_type,
                    "parameters": parameters
                }
            }
            
            # Execute task based on agent type
            if hasattr(agent_instance, 'execute_task_stream'):
                # Custom task execution with streaming
                async for response in agent_instance.execute_task_stream(
                    task_type, parameters, context
                ):
                    yield response
            else:
                # Default task execution
                result = await self._execute_default_task(
                    agent_instance, task_type, parameters, context
                )
                
                yield {
                    "type": "task_result",
                    "content": "Task completed",
                    "metadata": {
                        "agent_id": agent_id,
                        "task_type": task_type,
                        "result": result
                    }
                }
                
        except Exception as e:
            logger.error(f"Error executing agent task: {str(e)}")
            yield {
                "type": "error",
                "content": str(e),
                "metadata": {
                    "agent_id": agent_id,
                    "task_type": task_type,
                    "error_type": type(e).__name__
                }
            }
    
    # =====================================
    # AGENT CREATORS
    # =====================================
    
    async def _create_signature_agent(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> DigitalSignatureLangroidAgent:
        """Create digital signature agent"""
        
        return DigitalSignatureLangroidAgent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            user_id=user_id,
            llm_config=self.llm_config,
            vector_config=self._get_tenant_vector_store_config(tenant_id),
            config=config
        )
    
    async def _create_document_analyzer(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> ChatAgent:
        """Create document analyzer agent"""
        
        vector_config = self._get_tenant_vector_store_config(tenant_id)
        
        agent_config = ChatAgentConfig(
            name="DocumentAnalyzer",
            llm=self.llm_config,
            vecdb=vector_config,  # May be None if vector store unavailable
            system_message="""You are an expert document analyzer.
            
Your capabilities include:
- Summarizing documents
- Extracting key information
- Analyzing sentiment and tone
- Identifying important entities
- Suggesting tags and categories

Always provide clear, structured analysis with specific examples from the document."""
        )
        
        return ChatAgent(agent_config)
    
    async def _create_rag_assistant(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> ChatAgent:
        """Create RAG assistant agent"""
        
        # Configure collection name for tenant
        try:
            vector_config = QdrantDBConfig(
                cloud=False,
                host=app_settings.QDRANT_HOST,
                port=app_settings.QDRANT_PORT,
                storage_path=None,
                collection_name=f"{app_settings.QDRANT_COLLECTION_PREFIX}_{tenant_id}",
                embedding_model=app_settings.DEFAULT_EMBEDDING_MODEL
            )
        except Exception as e:
            logger.warning(f"Failed to create vector config for RAG assistant: {e}")
            vector_config = None
        
        agent_config = ChatAgentConfig(
            name="RAGAssistant",
            llm=self.llm_config,
            vecdb=vector_config,
            system_message="""You are a knowledgeable assistant that helps users find and understand information from their documents.

Your capabilities:
- Search through document collections
- Answer questions based on document content
- Provide detailed explanations with source references
- Suggest related topics and documents

Always cite your sources and indicate confidence levels in your answers."""
        )
        
        return ChatAgent(agent_config)
    
    async def _create_generic_agent(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> ChatAgent:
        """Create generic agent"""
        
        system_message = config.get(
            "system_message",
            "You are a helpful AI assistant. Answer questions clearly and concisely."
        )
        
        try:
            agent_config = ChatAgentConfig(
                name="GenericAgent",
                llm=self.llm_config,
                system_message=system_message
            )
        except Exception as e:
            logger.error(f"Failed to create generic agent config: {e}")
            # Fallback to minimal config
            agent_config = ChatAgentConfig(
                name="GenericAgent",
                system_message=system_message
            )
        
        return ChatAgent(agent_config)
    
    # =====================================
    # HELPER METHODS
    # =====================================
    
    async def _run_task_with_streaming(
        self,
        task: Task,
        message: str,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run a Langroid task with streaming responses"""
        
        try:
            # Start the task
            yield {
                "type": "message",
                "content": "Processing your request...",
                "metadata": {"status": "thinking"}
            }
            
            # Run the task (this is a simplified approach)
            # In practice, you'd want to implement proper streaming
            # with Langroid's streaming capabilities
            
            response = task.run(message)
            
            yield {
                "type": "message",
                "content": response.content if hasattr(response, 'content') else str(response),
                "metadata": {
                    "status": "completed",
                    "context": context
                }
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": f"Task execution failed: {str(e)}",
                "metadata": {"error_type": type(e).__name__}
            }
    
    async def _execute_default_task(
        self,
        agent_instance: Agent,
        task_type: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute default task for agents without custom task handling"""
        
        # Create a task prompt based on the task type and parameters
        task_prompt = f"""Execute the following task:

Task Type: {task_type}
Parameters: {json.dumps(parameters, indent=2)}
Context: {json.dumps(context or {}, indent=2)}

Provide a detailed response for this task."""
        
        # Create and run task
        task = Task(agent_instance)
        response = task.run(task_prompt)
        
        return {
            "task_type": task_type,
            "response": response.content if hasattr(response, 'content') else str(response),
            "parameters": parameters,
            "context": context
        }
    
    async def _cleanup_agent(self, agent_id: str):
        """Clean up an agent instance"""
        
        if agent_id in self.active_agents:
            agent_info = self.active_agents[agent_id]
            
            # Cleanup agent-specific resources
            if hasattr(agent_info["instance"], "cleanup"):
                try:
                    await agent_info["instance"].cleanup()
                except Exception as e:
                    logger.error(f"Error cleaning up agent {agent_id}: {str(e)}")
            
            # Remove from active agents
            del self.active_agents[agent_id]
            
            logger.info(f"Cleaned up agent {agent_id}")