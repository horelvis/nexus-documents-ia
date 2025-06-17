"""
Dynamic Agent Loader - Loads agent definitions from JSON files
"""
import os
import json
from typing import Dict, List, Optional
from pathlib import Path
from loguru import logger
from crewai import Agent
from langchain_core.language_models import BaseChatModel

from app.agents.agent_schema import AgentDefinition, AgentCollection, AgentCapability


class DynamicAgentLoader:
    """Loads and manages agent definitions from JSON files"""
    
    def __init__(self, definitions_path: Optional[str] = None):
        """
        Initialize the agent loader
        
        Args:
            definitions_path: Path to agent definitions directory
        """
        if definitions_path:
            self.definitions_path = Path(definitions_path)
        else:
            # Default to app/agents/definitions
            self.definitions_path = Path(__file__).parent / "definitions"
        
        self.agents_collection = AgentCollection(agents=[])
        self._agent_cache: Dict[str, Agent] = {}
        
    def load_all_agents(self) -> AgentCollection:
        """Load all agent definitions from JSON files"""
        logger.info(f"Loading agents from {self.definitions_path}")
        
        if not self.definitions_path.exists():
            logger.warning(f"Definitions path does not exist: {self.definitions_path}")
            return self.agents_collection
        
        # Load all JSON files
        json_files = list(self.definitions_path.glob("*.json"))
        logger.info(f"Found {len(json_files)} agent definition files")
        
        for json_file in json_files:
            try:
                self._load_agent_file(json_file)
            except Exception as e:
                logger.error(f"Failed to load agent from {json_file}: {e}")
        
        logger.info(f"Loaded {len(self.agents_collection.agents)} agents successfully")
        return self.agents_collection
    
    def _load_agent_file(self, file_path: Path) -> None:
        """Load a single agent definition from JSON file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate and create agent definition
            agent_def = AgentDefinition(**data)
            
            # Check if agent already exists
            existing = self.agents_collection.get_agent(agent_def.id)
            if existing:
                logger.warning(f"Agent {agent_def.id} already loaded, updating definition")
                # Remove old definition
                self.agents_collection.agents = [
                    a for a in self.agents_collection.agents if a.id != agent_def.id
                ]
            
            # Add to collection
            self.agents_collection.agents.append(agent_def)
            logger.info(f"Loaded agent: {agent_def.id} ({agent_def.name})")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading agent from {file_path}: {e}")
            raise
    
    def reload_agents(self) -> AgentCollection:
        """Reload all agent definitions (useful for hot-reloading)"""
        logger.info("Reloading agent definitions...")
        self.agents_collection = AgentCollection(agents=[])
        self._agent_cache.clear()
        return self.load_all_agents()
    
    def get_agent_definition(self, agent_id: str) -> Optional[AgentDefinition]:
        """Get a specific agent definition by ID"""
        return self.agents_collection.get_agent(agent_id)
    
    def get_agents_for_document_type(self, doc_type: str) -> List[AgentDefinition]:
        """Get all agents that can handle a specific document type"""
        return self.agents_collection.get_agents_for_document_type(doc_type)
    
    def get_agents_with_capability(self, capability: AgentCapability) -> List[AgentDefinition]:
        """Get all agents with a specific capability"""
        return self.agents_collection.get_agents_with_capability(capability)
    
    def create_crewai_agent(
        self, 
        agent_def: AgentDefinition, 
        llm: BaseChatModel,
        context: Optional[Dict] = None
    ) -> Agent:
        """
        Create a CrewAI agent from an agent definition
        
        Args:
            agent_def: Agent definition
            llm: Language model to use
            context: Additional context for the agent
            
        Returns:
            CrewAI Agent instance
        """
        # Check cache first
        if agent_def.id in self._agent_cache:
            return self._agent_cache[agent_def.id]
        
        # Build system message with context
        system_message = agent_def.backstory
        if agent_def.system_prompt_template and context:
            system_message = agent_def.system_prompt_template.format(**context)
        
        # Create CrewAI agent
        agent = Agent(
            role=agent_def.role,
            goal=agent_def.goal,
            backstory=system_message,
            verbose=agent_def.verbose,
            allow_delegation=agent_def.allow_delegation,
            max_iter=agent_def.max_iterations,
            llm=llm,
            # Additional attributes from definition
            tools=[],  # Tools would be loaded separately
            memory=True,  # Enable memory for all agents
        )
        
        # Cache the agent
        self._agent_cache[agent_def.id] = agent
        
        return agent
    
    def create_agents_for_task(
        self,
        task_type: str,
        document_type: str,
        llm: BaseChatModel,
        required_capabilities: Optional[List[AgentCapability]] = None,
        context: Optional[Dict] = None
    ) -> List[Agent]:
        """
        Create a team of agents for a specific task
        
        Args:
            task_type: Type of task to perform
            document_type: Type of document to process
            llm: Language model to use
            required_capabilities: Required agent capabilities
            context: Additional context
            
        Returns:
            List of CrewAI agents
        """
        # Get agents that can handle this document type
        suitable_agents = self.get_agents_for_document_type(document_type)
        
        # Filter by required capabilities if specified
        if required_capabilities:
            suitable_agents = [
                agent for agent in suitable_agents
                if any(cap in agent.capabilities for cap in required_capabilities)
            ]
        
        # Filter by active status
        suitable_agents = [agent for agent in suitable_agents if agent.active]
        
        # Sort by relevance (agents with more matching capabilities first)
        if required_capabilities:
            suitable_agents.sort(
                key=lambda a: sum(1 for cap in required_capabilities if cap in a.capabilities),
                reverse=True
            )
        
        # Create CrewAI agents
        crew_agents = []
        for agent_def in suitable_agents:
            try:
                agent = self.create_crewai_agent(agent_def, llm, context)
                crew_agents.append(agent)
            except Exception as e:
                logger.error(f"Failed to create agent {agent_def.id}: {e}")
        
        return crew_agents
    
    def get_agent_selection_rules(self) -> Dict[str, List[str]]:
        """
        Get document type to agent mapping rules based on loaded agents
        
        Returns:
            Dictionary mapping document types to agent IDs
        """
        rules = {}
        
        for agent in self.agents_collection.agents:
            if not agent.active:
                continue
                
            for doc_type in agent.document_types:
                if doc_type not in rules:
                    rules[doc_type] = []
                rules[doc_type].append(agent.id)
        
        return rules
    
    def save_agent_definition(self, agent_def: AgentDefinition) -> str:
        """
        Save an agent definition to a JSON file
        
        Args:
            agent_def: Agent definition to save
            
        Returns:
            Path to saved file
        """
        file_path = self.definitions_path / f"{agent_def.id}.json"
        
        # Create directory if it doesn't exist
        self.definitions_path.mkdir(parents=True, exist_ok=True)
        
        # Save to file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(agent_def.dict(), f, indent=2)
        
        logger.info(f"Saved agent definition to {file_path}")
        
        # Reload to update collection
        self._load_agent_file(file_path)
        
        return str(file_path)


# Global instance for easy access
agent_loader = DynamicAgentLoader()