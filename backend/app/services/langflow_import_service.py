"""
Langflow Import Service - Convert Langflow flows to Agent Definitions
"""
import json
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AgentDefinition, AgentType, AgentStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class LangflowImportService:
    """Service to import and convert Langflow flows to agent definitions"""
    
    @staticmethod
    def parse_langflow_export(langflow_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Langflow export and extract agent configuration
        
        Langflow export structure:
        {
            "name": "Flow Name",
            "description": "Flow description",
            "data": {
                "nodes": [...],
                "edges": [...],
                "viewport": {...}
            }
        }
        """
        try:
            # Extract basic info
            flow_name = langflow_json.get("name", "Unnamed Flow")
            flow_description = langflow_json.get("description", "")
            
            # Extract nodes data
            nodes = langflow_json.get("data", {}).get("nodes", [])
            edges = langflow_json.get("data", {}).get("edges", [])
            
            # Find the main agent/chain configuration
            agent_config = LangflowImportService._extract_agent_config(nodes, edges)
            
            # Build agent definition
            agent_def = {
                "name": LangflowImportService._sanitize_name(flow_name),
                "display_name": flow_name,
                "description": flow_description or f"Agent imported from Langflow: {flow_name}",
                "agent_type": LangflowImportService._determine_agent_type(nodes),
                "capabilities": LangflowImportService._extract_capabilities(nodes),
                "system_prompt": LangflowImportService._extract_system_prompt(nodes),
                "parameters": agent_config,
                "ui_config": LangflowImportService._generate_ui_config(nodes, flow_name),
                "langflow_metadata": {
                    "flow_id": langflow_json.get("id"),
                    "version": langflow_json.get("version", "1.0.0"),
                    "nodes_count": len(nodes),
                    "edges_count": len(edges),
                    "imported_at": datetime.utcnow().isoformat()
                }
            }
            
            return agent_def
            
        except Exception as e:
            logger.error(f"Error parsing Langflow export: {str(e)}")
            raise ValueError(f"Invalid Langflow export format: {str(e)}")
    
    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Convert flow name to valid agent name"""
        # Replace spaces and special chars with underscores
        import re
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Add prefix if starts with number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"agent_{sanitized}"
        return sanitized[:100]  # Limit length
    
    @staticmethod
    def _determine_agent_type(nodes: List[Dict]) -> AgentType:
        """Determine agent type based on nodes"""
        node_types = [node.get("data", {}).get("type", "") for node in nodes]
        
        # Check for specific patterns
        if any("conversation" in t.lower() for t in node_types):
            return AgentType.CONVERSATIONAL
        elif any("analysis" in t.lower() or "analyze" in t.lower() for t in node_types):
            return AgentType.ANALYTICAL
        elif any("workflow" in t.lower() or "sequence" in t.lower() for t in node_types):
            return AgentType.WORKFLOW
        else:
            return AgentType.CUSTOM
    
    @staticmethod
    def _extract_capabilities(nodes: List[Dict]) -> List[str]:
        """Extract capabilities from node types and configurations"""
        capabilities = set()
        
        for node in nodes:
            node_data = node.get("data", {})
            node_type = node_data.get("type", "").lower()
            
            # Map node types to capabilities
            if "chat" in node_type or "conversation" in node_type:
                capabilities.add("chat")
            if "memory" in node_type:
                capabilities.add("memory")
            if "tool" in node_type:
                capabilities.add("tool_use")
            if "retriever" in node_type or "vectorstore" in node_type:
                capabilities.add("rag")
            if "agent" in node_type:
                capabilities.add("autonomous")
            if "chain" in node_type:
                capabilities.add("chaining")
            if "prompt" in node_type:
                capabilities.add("prompting")
            
            # Check for specific tools
            tool_name = node_data.get("tool_name", "")
            if tool_name:
                capabilities.add(f"tool_{tool_name.lower()}")
        
        return list(capabilities)
    
    @staticmethod
    def _extract_system_prompt(nodes: List[Dict]) -> str:
        """Extract system prompt from prompt nodes"""
        prompts = []
        
        for node in nodes:
            node_data = node.get("data", {})
            node_type = node_data.get("type", "").lower()
            
            # Look for prompt nodes
            if "prompt" in node_type or "system" in node_type:
                template = node_data.get("template", "")
                if template:
                    prompts.append(template)
                
                # Check for prompt in node parameters
                for key, value in node_data.items():
                    if "prompt" in key.lower() and isinstance(value, str) and value:
                        prompts.append(value)
        
        # Combine prompts or use default
        if prompts:
            return "\n\n".join(prompts)
        else:
            return "You are a helpful AI assistant created with Langflow. Follow the user's instructions and provide helpful responses."
    
    @staticmethod
    def _extract_agent_config(nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
        """Extract detailed agent configuration from nodes and edges"""
        config = {
            "nodes": {},
            "connections": [],
            "tools": [],
            "memory_config": {},
            "llm_config": {}
        }
        
        # Process nodes
        for node in nodes:
            node_id = node.get("id")
            node_data = node.get("data", {})
            node_type = node_data.get("type", "")
            
            config["nodes"][node_id] = {
                "type": node_type,
                "config": node_data.get("node", {}),
                "position": node.get("position", {})
            }
            
            # Extract specific configurations
            if "tool" in node_type.lower():
                config["tools"].append({
                    "name": node_data.get("tool_name", node_type),
                    "config": node_data
                })
            elif "memory" in node_type.lower():
                config["memory_config"] = node_data
            elif "llm" in node_type.lower() or "model" in node_type.lower():
                config["llm_config"] = node_data
        
        # Process edges (connections)
        for edge in edges:
            config["connections"].append({
                "source": edge.get("source"),
                "target": edge.get("target"),
                "sourceHandle": edge.get("sourceHandle"),
                "targetHandle": edge.get("targetHandle")
            })
        
        return config
    
    @staticmethod
    def _generate_ui_config(nodes: List[Dict], flow_name: str) -> Dict[str, Any]:
        """Generate UI configuration based on flow structure"""
        # Determine icon based on node types
        node_types = [node.get("data", {}).get("type", "").lower() for node in nodes]
        
        icon = "IconRobot"  # Default
        color = "blue"      # Default
        
        # Icon mapping
        if any("chat" in t for t in node_types):
            icon = "IconMessageCircle"
            color = "blue"
        elif any("analysis" in t or "analyze" in t for t in node_types):
            icon = "IconChartBar"
            color = "emerald"
        elif any("tool" in t for t in node_types):
            icon = "IconTool"
            color = "purple"
        elif any("chain" in t for t in node_types):
            icon = "IconLink"
            color = "amber"
        
        # Generate quick actions based on capabilities
        quick_actions = []
        if any("chat" in t for t in node_types):
            quick_actions.append(f"Chat with {flow_name}")
        if any("analysis" in t for t in node_types):
            quick_actions.append(f"Analyze documents with {flow_name}")
        if any("tool" in t for t in node_types):
            quick_actions.append(f"Execute {flow_name} tools")
        
        return {
            "icon": icon,
            "color": color,
            "quick_actions": quick_actions,
            "show_thinking": True,  # Enable chain of thought by default
            "expandable": True
        }
    
    @staticmethod
    async def import_from_langflow(
        db: Session,
        langflow_json: Dict[str, Any],
        tenant_id: UUID,
        user_id: UUID,
        is_public: bool = False
    ) -> AgentDefinition:
        """Import a Langflow flow and create an agent definition"""
        
        # Parse the Langflow export
        agent_data = LangflowImportService.parse_langflow_export(langflow_json)
        
        # Check if agent with same name exists
        existing = db.query(AgentDefinition).filter(
            AgentDefinition.name == agent_data["name"],
            AgentDefinition.tenant_id == (None if is_public else tenant_id)
        ).first()
        
        if existing:
            # Update existing agent
            for key, value in agent_data.items():
                if key != "name":  # Don't change the name
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            agent = existing
            logger.info(f"Updated existing agent: {agent.name}")
        else:
            # Create new agent definition
            agent = AgentDefinition(
                **agent_data,
                tenant_id=None if is_public else tenant_id,
                created_by=user_id,
                is_public=is_public,
                status=AgentStatus.ACTIVE
            )
            db.add(agent)
            logger.info(f"Created new agent from Langflow: {agent.name}")
        
        db.commit()
        db.refresh(agent)
        
        return agent
    
    @staticmethod
    async def import_from_langflow_url(
        db: Session,
        flow_url: str,
        tenant_id: UUID,
        user_id: UUID,
        is_public: bool = False
    ) -> AgentDefinition:
        """Import a Langflow flow from URL (e.g., Langflow API)"""
        import httpx
        
        try:
            # Fetch flow from Langflow API
            async with httpx.AsyncClient() as client:
                response = await client.get(flow_url)
                response.raise_for_status()
                langflow_json = response.json()
            
            # Import the flow
            return await LangflowImportService.import_from_langflow(
                db, langflow_json, tenant_id, user_id, is_public
            )
            
        except httpx.HTTPError as e:
            logger.error(f"Error fetching Langflow flow from URL: {str(e)}")
            raise ValueError(f"Could not fetch flow from URL: {str(e)}")
    
    @staticmethod
    def validate_langflow_export(langflow_json: Dict[str, Any]) -> bool:
        """Validate that the JSON is a valid Langflow export"""
        required_keys = ["name", "data"]
        data_keys = ["nodes", "edges"]
        
        # Check top-level structure
        if not all(key in langflow_json for key in required_keys):
            return False
        
        # Check data structure
        data = langflow_json.get("data", {})
        if not all(key in data for key in data_keys):
            return False
        
        # Check nodes structure
        nodes = data.get("nodes", [])
        if not isinstance(nodes, list):
            return False
        
        # Basic node validation
        for node in nodes:
            if not isinstance(node, dict) or "id" not in node or "data" not in node:
                return False
        
        return True