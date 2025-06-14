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
# from app.services.digital_signature_langroid_agent import DigitalSignatureLangroidAgent
from app.services.enhanced_langroid_agent import DocumentAnalysisAgent, ContractAnalysisAgent
from app.services.financial_analysis_agent import FinancialAnalysisAgent

logger = logging.getLogger(__name__)


class LangroidAgentService:
    """Service for managing Langroid agents"""
    
    def __init__(self):
        self.active_agents: Dict[str, Dict[str, Any]] = {}
        # Start with built-in agents - use full agent IDs as expected by frontend
        self.agent_classes = {
            "digital_signature": self._create_signature_agent,
            "digital_signature_agent": self._create_signature_agent,
            "document_analyzer": self._create_document_analyzer,
            "document_analyzer_agent": self._create_document_analyzer,
            "rag_assistant": self._create_rag_assistant,
            "rag_assistant_agent": self._create_rag_assistant,
            "legal_compliance": self._create_legal_compliance_agent,
            "legal_compliance_agent": self._create_legal_compliance_agent,
            "financial_analysis": self._create_financial_analysis_agent,
            "financial_analysis_agent": self._create_financial_analysis_agent,
            "generic": self._create_generic_agent
        }
        self.dynamic_agent_definitions: Dict[str, Dict[str, Any]] = {}
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
                # Don't set storage_path for server mode
                # "embedding_model": app_settings.DEFAULT_EMBEDDING_MODEL  # Will set this per tenant
            }
            logger.info(f"Configured vector store: {app_settings.QDRANT_HOST}:{app_settings.QDRANT_PORT}")
        except Exception as e:
            logger.error(f"Failed to configure vector store: {e}")
            self.base_vector_store_config = {"cloud": False}
        
        logger.info("Langroid Agent Service initialized successfully")
        
        # Load dynamic agent definitions
        await self._load_dynamic_agents()
    
    def _get_tenant_vector_store_config(self, tenant_id: str):
        """Get vector store config isolated by tenant"""
        try:
            collection_name = f"nexus_langroid_agents_{tenant_id}"
            
            # Create minimal config that works
            config = QdrantDBConfig(
                cloud=False,
                host=app_settings.QDRANT_HOST,
                port=app_settings.QDRANT_PORT,
                collection_name=collection_name
            )
            return config
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
                "last_used": datetime.now(),
                "persistent": config.get("persistent", True)  # Por defecto son persistentes
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
        
        # First, return all available agent types (both built-in and dynamic)
        available_agents = []
        
        # Built-in agents with their metadata
        built_in_agents = {
            "digital_signature_agent": {
                "id": "digital_signature_agent",
                "name": "Digital Signature Agent",
                "description": "Handles digital signature workflows and document signing",
                "type": "signature",
                "icon": "signature"
            },
            "document_analyzer_agent": {
                "id": "document_analyzer_agent", 
                "name": "Document Analyzer Agent",
                "description": "Analyzes documents for various purposes",
                "type": "document",
                "icon": "document"
            },
            "rag_assistant_agent": {
                "id": "rag_assistant_agent",
                "name": "RAG Assistant Agent",
                "description": "Retrieval-Augmented Generation for document Q&A",
                "type": "rag",
                "icon": "rag"
            },
            "legal_compliance_agent": {
                "id": "legal_compliance_agent",
                "name": "Legal Compliance Agent",
                "description": "Analyzes documents for legal compliance",
                "type": "legal",
                "icon": "legal"
            },
            "financial_analysis_agent": {
                "id": "financial_analysis_agent",
                "name": "Financial Analysis Agent",
                "description": "Analyzes financial documents and provides insights",
                "type": "financial",
                "icon": "financial"
            }
        }
        
        # Add built-in agents
        for agent_key, agent_meta in built_in_agents.items():
            available_agents.append(agent_meta)
        
        # Add dynamic agents
        for agent_name, agent_def in self.dynamic_agent_definitions.items():
            available_agents.append({
                "id": agent_name,
                "name": agent_def.get("display_name", agent_name.replace("_", " ").title()),
                "description": agent_def.get("description", "Custom agent from Langflow"),
                "type": agent_def.get("type", "custom"),
                "icon": agent_def.get("ui_config", {}).get("icon", "robot")
            })
        
        # Then add any active agent instances for this tenant
        active_instances = []
        for agent_id, agent_info in self.active_agents.items():
            if agent_info["tenant_id"] == tenant_id:
                active_instances.append({
                    "instance_id": agent_id,
                    "agent_id": agent_info["type"],
                    "type": agent_info["type"],
                    "name": agent_info["configuration"].get("name", f"{agent_info['type'].replace('_', ' ').title()} Agent"),
                    "persistent": agent_info.get("persistent", True),
                    "created_at": agent_info["created_at"].isoformat(),
                    "last_used": agent_info["last_used"].isoformat(),
                    "configuration": agent_info["configuration"],
                    "user_id": agent_info["user_id"]
                })
        
        return available_agents
    
    async def chat_with_agent(
        self,
        agent_id: str,
        tenant_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Chat with an agent and stream responses"""
        
        # Check if this is an agent type rather than an instance
        if agent_id in self.agent_classes and agent_id not in self.active_agents:
            # Create a temporary agent instance for this chat
            try:
                temp_agent_id = await self.create_agent(
                    agent_type=agent_id,
                    tenant_id=tenant_id,
                    user_id="system",  # System-created for chat
                    configuration={"persistent": False}
                )
                agent_id = temp_agent_id
            except Exception as e:
                yield {
                    "type": "error",
                    "content": f"Failed to create agent instance: {str(e)}",
                    "metadata": {"agent_id": agent_id}
                }
                return
        
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
    ) -> ChatAgent:
        """Create digital signature agent"""
        
        try:
            # For now, create a simple ChatAgent instead of complex DigitalSignatureLangroidAgent
            # to avoid LLMFunctionSpec validation errors
            vector_config = self._get_tenant_vector_store_config(tenant_id)
            
            agent_config = ChatAgentConfig(
                name="DigitalSignatureAgent",
                llm=self.llm_config,
                vecdb=vector_config,  # May be None if vector store unavailable
                system_message="""You are a digital signature assistant specialized in managing signature workflows.

Your capabilities include:
- Creating signature requests for documents
- Managing multi-party signature workflows
- Tracking signature status and completion
- Handling sequential and parallel signature processes
- Providing updates on signature requests

Always provide clear guidance on signature processes and help users manage their document signature workflows efficiently."""
            )
            
            return ChatAgent(agent_config)
            
        except Exception as e:
            logger.error(f"Failed to create signature agent: {e}")
            # Fallback to minimal agent
            agent_config = ChatAgentConfig(
                name="DigitalSignatureAgent",
                system_message="You are a digital signature assistant."
            )
            return ChatAgent(agent_config)
    
    async def _create_document_analyzer(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> DocumentAnalysisAgent:
        """Create enhanced document analyzer agent with chain of thought"""
        
        # Return enhanced agent with visible reasoning
        return DocumentAnalysisAgent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            user_id=user_id,
            config=config
        )
    
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
                collection_name=f"{app_settings.QDRANT_COLLECTION_PREFIX}_{tenant_id}"
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
    
    async def _create_legal_compliance_agent(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> ContractAnalysisAgent:
        """Create enhanced legal compliance agent with chain of thought"""
        
        # Use enhanced contract analysis agent with visible reasoning
        return ContractAnalysisAgent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            user_id=user_id,
            config=config
        )
    
    async def _create_financial_analysis_agent(
        self,
        agent_id: str,
        tenant_id: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> FinancialAnalysisAgent:
        """Create enhanced financial analysis agent with chain of thought"""
        
        # Return enhanced financial agent with visible reasoning
        return FinancialAnalysisAgent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            user_id=user_id,
            config=config
        )
    
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
    
    async def _load_dynamic_agents(self):
        """Load dynamic agent definitions from JSON files"""
        try:
            logger.info("Loading dynamic agent definitions from JSON files...")
            
            import json
            import os
            from pathlib import Path
            
            # Directory where Langflow exports are stored
            agents_dir = Path("/app/agents")
            if not agents_dir.exists():
                agents_dir = Path("./agents")  # Fallback for local development
            if not agents_dir.exists():
                # Also check the langflow flows directory
                agents_dir = Path("/app/docker/langflow/flows")
            if not agents_dir.exists():
                # Try relative path from service location
                agents_dir = Path("../../docker/langflow/flows")
            
            if agents_dir.exists():
                # Load all JSON files from agents directory
                for json_file in agents_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r') as f:
                            agent_def = json.load(f)
                        
                        # Convert Langflow export to agent definition
                        if "data" in agent_def and "nodes" in agent_def.get("data", {}):
                            # This is a Langflow export, convert it
                            from app.services.langflow_import_service import LangflowImportService
                            agent_def = LangflowImportService.parse_langflow_export(agent_def)
                        
                        agent_name = agent_def.get("name")
                        if agent_name and agent_name not in self.agent_classes:
                            self.dynamic_agent_definitions[agent_name] = agent_def
                            
                            # Create factory function with proper closure
                            def make_factory(definition):
                                return lambda aid, tid, uid, cfg: self._create_dynamic_agent(
                                    aid, tid, uid, cfg, definition
                                )
                            
                            self.agent_classes[agent_name] = make_factory(agent_def)
                            logger.info(f"Loaded agent from {json_file.name}: {agent_name}")
                            
                    except Exception as e:
                        logger.error(f"Error loading agent from {json_file}: {e}")
                
                logger.info(f"Loaded {len(self.dynamic_agent_definitions)} dynamic agents from files")
            else:
                logger.info(f"Agents directory not found at {agents_dir}")
            
            # Load example agent if no dynamic agents loaded
            if not self.dynamic_agent_definitions:
                logger.info("Loading example agent...")
                example_agent = {
                    "name": "example_langflow_agent",
                    "display_name": "Example Langflow Agent",
                    "description": "Example agent that can be created in Langflow",
                    "system_prompt": "You are a helpful assistant created with Langflow.",
                    "capabilities": ["chat", "rag", "tool_use"],
                    "ui_config": {
                        "icon": "IconRobot",
                        "color": "purple",
                        "quick_actions": [
                            "Chat with Langflow agent",
                            "Analyze documents",
                            "Execute tools"
                        ]
                    }
                }
                
                self.dynamic_agent_definitions["example_langflow_agent"] = example_agent
                self.agent_classes["example_langflow_agent"] = lambda aid, tid, uid, cfg: self._create_dynamic_agent(
                    aid, tid, uid, cfg, example_agent
                )
                logger.info("Loaded example agent")
                
        except Exception as e:
            logger.error(f"Error loading dynamic agents: {e}")
    
    async def _create_dynamic_agent(
        self,
        agent_id: str,
        tenant_id: str, 
        user_id: str,
        config: Dict[str, Any],
        definition: Dict[str, Any]
    ) -> ChatAgent:
        """Create a dynamic agent based on definition"""
        
        # Use the definition to configure the agent
        system_prompt = definition.get("system_prompt", "You are a helpful AI assistant.")
        
        # Check if we should use a specialized base class
        base_class_name = definition.get("base_class", "generic")
        
        if base_class_name == "financial" or "financial" in definition.get("capabilities", []):
            # Use FinancialAnalysisAgent for financial agents
            return FinancialAnalysisAgent(
                agent_id=agent_id,
                tenant_id=tenant_id,
                user_id=user_id,
                config={
                    **config,
                    "system_prompt": system_prompt,
                    "definition": definition
                }
            )
        else:
            # Use generic ChatAgent
            vector_config = self._get_tenant_vector_store_config(tenant_id)
            
            agent_config = ChatAgentConfig(
                name=definition.get("display_name", "Dynamic Agent"),
                llm=self.llm_config,
                vecdb=vector_config,
                system_message=system_prompt
            )
            
            return ChatAgent(agent_config)