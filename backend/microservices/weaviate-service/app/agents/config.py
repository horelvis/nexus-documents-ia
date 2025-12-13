"""
Agent Framework Configuration

Centralized configuration for agent behavior, timeouts, and fallback settings.
Supports multiple LLM providers with vLLM as the primary option.
"""

import os
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class WorkflowType(str, Enum):
    """Available workflow orchestration patterns"""
    AUTO = "auto"           # System chooses based on query analysis
    SEQUENTIAL = "sequential"  # RoundRobinGroupChat - ordered execution
    GROUP_CHAT = "group_chat"  # SelectorGroupChat - LLM selects agent
    SWARM = "swarm"         # Handoff pattern - agents delegate


class AgentType(str, Enum):
    """Available specialized agents"""
    SEARCH = "search_specialist"
    ANALYST = "document_analyst"
    CONTRACT = "contract_reviewer"
    COMPLIANCE = "compliance_checker"
    SUMMARIZER = "summarizer"
    TRIAGE = "triage"  # For swarm pattern


@dataclass
class AgentConfig:
    """Configuration for Agent Framework"""

    # Feature toggle
    enabled: bool = False  # AutoGen legacy disabled by default

    # Workflow defaults
    default_workflow: WorkflowType = WorkflowType.AUTO
    max_turns: int = 15
    timeout_seconds: int = 300

    # Fallback settings
    fallback_to_rag: bool = True
    fallback_threshold: float = 0.3  # Confidence threshold

    # Model settings - Multi-provider support
    model_provider: str = "vllm"  # vllm (primary), openai, anthropic, google, ollama (legacy)
    default_temperature: float = 0.2  # Default temperature for agents

    # Per-agent temperature configuration
    # Lower = more deterministic (legal analysis), Higher = more creative (summaries)
    agent_temperatures: dict = None  # Set in from_env()

    @staticmethod
    def get_default_agent_temperatures() -> dict:
        """Load temperature settings from YAML config or use fallback defaults."""
        import yaml
        from pathlib import Path

        # Try to load from YAML config
        config_path = Path(__file__).parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml"

        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config and 'agent_config' in config:
                        temps = config['agent_config'].get('temperatures', {})
                        if temps:
                            return temps
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load agent temperatures from YAML: {e}")

        # Fallback defaults if YAML not available
        return {
            "ContractAgent": 0.1,
            "LaborAgent": 0.1,
            "ComplianceAgent": 0.1,
            "FiscalAgent": 0.1,
            "PrivacyAgent": 0.1,
            "RealEstateAgent": 0.1,
            "EducationAgent": 0.1,
            "SearchAgent": 0.2,
            "AnalystAgent": 0.2,
            "SummarizerAgent": 0.3,
            "DocumentDetector": 0.1,  # Low temp for precise classification
            "PlannerAgent": 0.2,  # Moderate for creative planning
            "default": 0.2,
        }

    # vLLM (PRIMARY - high-throughput GPU inference)
    vllm_enabled: bool = True
    vllm_base_url: str = "http://vllm:8000/v1"
    vllm_model: str = "Qwen/Qwen3-8B"

    # Ollama (LEGACY - use vLLM instead)
    ollama_base_url: str = "http://genai-ollama:11434"
    ollama_model: str = "llama3.2:latest"

    # OpenAI (fallback)
    openai_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None

    # Anthropic (fallback)
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_api_key: Optional[str] = None

    # Google (fallback)
    google_model: str = "gemini-1.5-flash"
    google_api_key: Optional[str] = None

    # Agent-specific settings
    search_top_k: int = 10
    analyst_depth: str = "comprehensive"
    compliance_jurisdiction: str = "es"

    # Redis settings (for NativeAgent thread persistence)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    def get_temperature_for_agent(self, agent_name: str) -> float:
        """Get the temperature setting for a specific agent."""
        temps = self.agent_temperatures or self.get_default_agent_temperatures()

        if agent_name in temps:
            return float(temps[agent_name])

        # Use 'default' from config if available, otherwise use class default
        return float(temps.get("default", self.default_temperature))

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Create configuration from environment variables"""
        config = cls(
            # Feature toggle
            # AutoGen legacy is deprecated; keep it off unless explicitly requested
            enabled=os.getenv("AUTOGEN_ENABLED", "false").lower() == "true",

            # Workflow
            default_workflow=WorkflowType(
                os.getenv("AUTOGEN_DEFAULT_WORKFLOW", "auto")
            ),
            max_turns=int(os.getenv("AUTOGEN_MAX_TURNS", "15")),
            timeout_seconds=int(os.getenv("AUTOGEN_TIMEOUT_SECONDS", "300")),

            # Fallback
            fallback_to_rag=os.getenv(
                "AUTOGEN_FALLBACK_TO_RAG", "true"
            ).lower() == "true",
            fallback_threshold=float(
                os.getenv("AUTOGEN_FALLBACK_THRESHOLD", "0.3")
            ),

            # Model - Multi-provider (vLLM is default)
            model_provider=os.getenv("LLM_PROVIDER", "vllm"),
            default_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),

            # vLLM (PRIMARY)
            vllm_enabled=os.getenv("VLLM_ENABLED", "true").lower() == "true",
            vllm_base_url=os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"),
            vllm_model=os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B"),

            # Ollama (LEGACY)
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://genai-ollama:11434"
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2:latest")),

            # OpenAI (fallback)
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),

            # Anthropic (fallback)
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),

            # Google (fallback)
            google_model=os.getenv("GOOGLE_MODEL", "gemini-1.5-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),

            # Agent-specific
            search_top_k=int(os.getenv("AUTOGEN_SEARCH_TOP_K", "10")),
            analyst_depth=os.getenv("AUTOGEN_ANALYST_DEPTH", "comprehensive"),
            compliance_jurisdiction=os.getenv(
                "AUTOGEN_COMPLIANCE_JURISDICTION", "es"
            ),

            # Redis (for NativeAgent thread persistence)
            redis_host=os.getenv("REDIS_HOST", "redis"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),

            # Per-agent temperatures (uses defaults)
            agent_temperatures=cls.get_default_agent_temperatures(),
        )
        return config


# Global configuration instance
agent_config = AgentConfig.from_env()
