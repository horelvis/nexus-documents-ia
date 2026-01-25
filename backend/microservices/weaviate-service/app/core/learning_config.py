"""
Centralized Configuration for Learning System

This module provides a single source of truth for all learning-related
configuration, replacing scattered hardcoded values across:
- continuous_learning.py
- knowledge_learning.py
- knowledge_classifier.py
- learning_service.py

Uses Pydantic Settings for:
- Type validation with ranges
- Environment variable support
- Centralized defaults
- Documentation through field descriptions

Usage:
    from app.core.learning_config import learning_settings

    # Access settings
    print(learning_settings.min_examples_for_training)

    # Override via environment
    # LEARNING_MIN_EXAMPLES=1000 python main.py

Version 1.0 - January 2026
"""

import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class LearningSettings(BaseSettings):
    """
    Centralized settings for the Learning System.

    Replaces hardcoded values in:
    - ContinuousLearningService (SLM Router fine-tuning)
    - KnowledgeLearningCollector (Knowledge source training)
    - SetFitKnowledgeClassifier (Knowledge classification)
    - PreferenceLearningService (User preference learning)
    """

    # =========================================================================
    # Path Configuration
    # =========================================================================
    # Base directories for models and data
    models_base_dir: str = Field(
        default="/data/models",
        validation_alias="LEARNING_MODELS_DIR",
        description="Base directory for trained models"
    )
    adapters_base_dir: str = Field(
        default="/data/adapters",
        validation_alias="LEARNING_ADAPTERS_DIR",
        description="Base directory for LoRA adapters"
    )
    knowledge_examples_dir: str = Field(
        default="/app/data/knowledge_examples",
        validation_alias="KNOWLEDGE_EXAMPLES_DIR",
        description="Directory for collected knowledge training examples"
    )
    nexus_router_model_dir: str = Field(
        default="/app/models/nexus_router",
        validation_alias="NEXUS_ROUTER_MODEL_DIR",
        description="Directory for NexusRouter classifier models"
    )

    # =========================================================================
    # ML Model Configuration
    # =========================================================================
    # SLM (Small Language Model) for routing
    slm_model_name: str = Field(
        default="Qwen/Qwen2-0.5B-Instruct",
        validation_alias="SLM_MODEL",
        description="Base model for SLM Router fine-tuning"
    )

    # SetFit base model for knowledge classification
    setfit_base_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        validation_alias="SETFIT_BASE_MODEL",
        description="Base model for SetFit knowledge classifier"
    )

    # =========================================================================
    # Training Thresholds
    # =========================================================================
    # Minimum examples before triggering training
    min_examples_for_training: int = Field(
        default=500,
        ge=10,
        le=10000,
        validation_alias="LEARNING_MIN_EXAMPLES",
        description="Minimum training examples before fine-tuning"
    )

    # Maximum examples per training batch
    max_examples_per_training: int = Field(
        default=5000,
        ge=100,
        le=50000,
        validation_alias="LEARNING_MAX_EXAMPLES",
        description="Maximum examples to use per training run"
    )

    # Success rate threshold
    min_success_rate: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        validation_alias="LEARNING_MIN_SUCCESS_RATE",
        description="Minimum success rate (0.0-1.0) required to trigger training"
    )

    # Classification confidence threshold
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        validation_alias="LEARNING_CONFIDENCE_THRESHOLD",
        description="Minimum confidence for classification acceptance"
    )

    # =========================================================================
    # Training Schedule
    # =========================================================================
    # Maintenance window for automated training
    maintenance_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="LEARNING_MAINTENANCE_HOUR",
        description="Hour (0-23) for maintenance window training"
    )
    maintenance_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Minute (0-59) for maintenance window start"
    )

    # Check interval for monitoring
    check_interval_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        validation_alias="LEARNING_CHECK_INTERVAL",
        description="Interval in seconds between training checks"
    )

    # =========================================================================
    # LoRA Fine-Tuning Parameters
    # =========================================================================
    lora_rank: int = Field(
        default=16,
        ge=4,
        le=64,
        description="LoRA adapter rank (higher = more parameters)"
    )
    lora_alpha: int = Field(
        default=32,
        ge=8,
        le=128,
        description="LoRA alpha scaling factor"
    )
    lora_dropout: float = Field(
        default=0.05,
        ge=0.0,
        le=0.5,
        description="LoRA dropout rate"
    )
    training_epochs: int = Field(
        default=2,
        ge=1,
        le=10,
        validation_alias="LEARNING_EPOCHS",
        description="Number of training epochs"
    )
    training_batch_size: int = Field(
        default=4,
        ge=1,
        le=32,
        validation_alias="LEARNING_BATCH_SIZE",
        description="Training batch size"
    )
    training_learning_rate: float = Field(
        default=2e-4,
        ge=1e-6,
        le=1e-2,
        description="Training learning rate"
    )

    # =========================================================================
    # Knowledge Classifier Settings
    # =========================================================================
    knowledge_min_examples_to_train: int = Field(
        default=20,
        ge=5,
        le=1000,
        description="Minimum examples for knowledge classifier training"
    )
    knowledge_min_examples_per_source: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Minimum examples per knowledge source"
    )
    knowledge_max_examples_per_source: int = Field(
        default=500,
        ge=10,
        le=10000,
        description="Maximum examples per knowledge source (prevents imbalance)"
    )
    knowledge_train_eval_split: float = Field(
        default=0.2,
        ge=0.1,
        le=0.5,
        description="Train/eval split ratio for knowledge classifier"
    )
    knowledge_dedup_by_text: bool = Field(
        default=True,
        description="Deduplicate training examples by text"
    )

    # =========================================================================
    # Preference Learning Settings
    # =========================================================================
    preference_cache_ttl_hours: int = Field(
        default=1,
        ge=1,
        le=24,
        description="Profile cache TTL in hours"
    )
    preference_buffer_threshold: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Interactions before profile update"
    )
    preference_max_frequent_queries: int = Field(
        default=50,
        ge=10,
        le=500,
        description="Maximum frequent queries to store per user"
    )
    preference_max_frequent_documents: int = Field(
        default=20,
        ge=5,
        le=100,
        description="Maximum frequent documents to store per user"
    )
    preference_max_interactions: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Maximum interactions to store per user"
    )

    # =========================================================================
    # Security Configuration
    # =========================================================================
    # Trusted model sources for trust_remote_code=True
    trusted_model_sources: List[str] = Field(
        default=["Qwen", "sentence-transformers", "BAAI", "microsoft", "meta-llama"],
        description="Organizations whose models are trusted for remote code execution"
    )

    # Enable strict security mode (disables trust_remote_code for untrusted sources)
    strict_model_security: bool = Field(
        default=True,
        validation_alias="LEARNING_STRICT_SECURITY",
        description="If True, only trusted sources can use trust_remote_code"
    )

    # =========================================================================
    # Redis Keys Configuration
    # =========================================================================
    redis_prefix: str = Field(
        default="slm:learning:",
        description="Redis key prefix for learning data"
    )

    # =========================================================================
    # Continuous Learning Toggle
    # =========================================================================
    continuous_learning_enabled: bool = Field(
        default=True,
        validation_alias="CONTINUOUS_LEARNING_ENABLED",
        description="Enable/disable continuous learning system"
    )

    @field_validator('trusted_model_sources', mode='before')
    @classmethod
    def parse_trusted_sources(cls, v):
        """Parse comma-separated string to list if needed."""
        if isinstance(v, str):
            return [s.strip() for s in v.split(',') if s.strip()]
        return v

    def is_model_trusted(self, model_name: str) -> bool:
        """
        Check if a model is from a trusted source.

        Args:
            model_name: Full model name (e.g., "Qwen/Qwen2-0.5B-Instruct")

        Returns:
            True if the model organization is in trusted_model_sources
        """
        return any(source.lower() in model_name.lower()
                   for source in self.trusted_model_sources)

    def get_knowledge_source_model_path(self) -> Path:
        """Get the path for knowledge source classifier models."""
        return Path(self.nexus_router_model_dir) / "knowledge_source"

    def get_adapter_version_path(self, version: int) -> Path:
        """Get the path for a specific adapter version."""
        return Path(self.adapters_base_dir) / f"v{version}"

    def get_current_model_path(self) -> Path:
        """Get the path for the current deployed model."""
        return Path(self.models_base_dir) / "current"

    class Config:
        env_prefix = "LEARNING_"
        case_sensitive = False
        extra = "ignore"


# Singleton instance
learning_settings = LearningSettings()


# Compatibility layer for existing code
def get_learning_settings() -> LearningSettings:
    """
    Get the learning settings singleton.

    Returns:
        LearningSettings instance

    Note:
        This function is provided for dependency injection compatibility.
        Direct access via `learning_settings` is also supported.
    """
    return learning_settings
