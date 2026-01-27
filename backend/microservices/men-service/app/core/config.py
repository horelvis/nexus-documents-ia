"""
MEN Service Configuration.

Defines settings for the Mixture of Experts Network including:
- Orchestrator model (domain classification)
- LLM Modeler (response synthesis)
- Expert models (tenant-specific knowledge)
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """FastAPI service settings from environment variables."""

    # Service identification
    service_name: str = "men-service"
    service_port: int = 8010
    service_version: str = "1.0.0"

    # Authentication
    MICROSERVICES_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("MICROSERVICES_API_KEY", "API_KEY")
    )

    # Feature flags
    men_enabled: bool = Field(default=True, alias="MEN_ENABLED")
    experts_enabled: bool = Field(default=True, alias="MEN_EXPERTS_ENABLED")
    modeler_enabled: bool = Field(default=True, alias="MEN_MODELER_ENABLED")

    # Model paths and configuration
    orchestrator_model: str = Field(
        default="Qwen/Qwen2.5-1.5B-Instruct",
        alias="MEN_ORCHESTRATOR_MODEL"
    )
    llm_modeler_model: str = Field(
        default="Qwen/Qwen2.5-3B-Instruct",
        alias="MEN_MODELER_MODEL"
    )
    expert_base_model: str = Field(
        default="Qwen/Qwen2.5-0.5B-Instruct",
        alias="MEN_EXPERT_BASE_MODEL"
    )

    # Experts directory
    experts_dir: str = Field(
        default="/app/trained_experts",
        alias="MEN_EXPERTS_DIR"
    )

    # LLM Modeler settings
    llm_modeler_max_tokens: int = Field(default=500, alias="MEN_MODELER_MAX_TOKENS")
    llm_modeler_temperature: float = Field(default=0.7, alias="MEN_MODELER_TEMPERATURE")
    llm_modeler_history_turns: int = Field(default=5, alias="MEN_MODELER_HISTORY_TURNS")

    # Expert settings
    expert_max_tokens: int = Field(default=300, alias="MEN_EXPERT_MAX_TOKENS")
    unload_experts_after_query: bool = Field(default=True, alias="MEN_UNLOAD_EXPERTS")

    # Orchestrator settings
    orchestrator_confidence_threshold: float = Field(
        default=0.6,
        alias="MEN_ORCHESTRATOR_THRESHOLD"
    )

    # HuggingFace token for model downloads
    hf_token: Optional[str] = Field(default=None, alias="HF_TOKEN")

    # CUDA settings
    cuda_visible_devices: str = Field(default="0", alias="CUDA_VISIBLE_DEVICES")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")

    class Config:
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()


@dataclass
class MENConfig:
    """
    Configuration dataclass for the MEN system.

    Provides a structured way to pass configuration to the MEN components
    with sensible defaults matching the Settings class.
    """

    # Orchestrator (domain classifier) - ~1.5 GB VRAM
    orchestrator_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    orchestrator_confidence_threshold: float = 0.6

    # LLM Modeler (response synthesizer) - ~2.5 GB VRAM
    llm_modeler_model: str = "Qwen/Qwen2.5-3B-Instruct"
    llm_modeler_max_tokens: int = 500
    llm_modeler_temperature: float = 0.7
    llm_modeler_history_turns: int = 5

    # Experts (specialized per domain/tenant) - ~0.5 GB VRAM each
    expert_base_model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    expert_max_tokens: int = 300
    unload_experts_after_query: bool = True

    # Directory for trained expert LoRA weights
    experts_dir: str = "/app/trained_experts"

    # Supported domains for classification
    domains: List[str] = field(default_factory=lambda: [
        "legal",
        "contract",
        "compliance",
        "finance",
        "hr",
        "technical",
        "general"
    ])

    # Feature flags
    experts_enabled: bool = True
    modeler_enabled: bool = True

    @classmethod
    def from_settings(cls, s: Settings) -> "MENConfig":
        """Create MENConfig from Settings instance."""
        return cls(
            orchestrator_model=s.orchestrator_model,
            orchestrator_confidence_threshold=s.orchestrator_confidence_threshold,
            llm_modeler_model=s.llm_modeler_model,
            llm_modeler_max_tokens=s.llm_modeler_max_tokens,
            llm_modeler_temperature=s.llm_modeler_temperature,
            llm_modeler_history_turns=s.llm_modeler_history_turns,
            expert_base_model=s.expert_base_model,
            expert_max_tokens=s.expert_max_tokens,
            unload_experts_after_query=s.unload_experts_after_query,
            experts_dir=s.experts_dir,
            experts_enabled=s.experts_enabled,
            modeler_enabled=s.modeler_enabled,
        )


# VRAM estimation constants
VRAM_ESTIMATES = {
    "orchestrator": 1.5,  # GB for Qwen2.5-1.5B @ 4-bit
    "modeler": 2.5,       # GB for Qwen2.5-3B @ 4-bit
    "expert": 0.5,        # GB for Qwen2.5-0.5B + LoRA @ 4-bit
    "base_total": 4.0,    # GB (orchestrator + modeler)
    "peak_total": 5.0,    # GB (with expert loaded)
}
