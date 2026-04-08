"""
Learning configuration for Emma AI preference learning system.
"""

import os
from pydantic_settings import BaseSettings


class LearningSettings(BaseSettings):
    """Settings for the preference learning system."""

    # Feature flags
    learning_enabled: bool = os.getenv("ENABLE_FEEDBACK_LEARNING", "true").lower() == "true"

    # Storage settings
    feedback_storage_days: int = int(os.getenv("FEEDBACK_STORAGE_DAYS", "30"))

    # Redis settings
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))

    # Database settings
    database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://nexus_user:nexus_password@db:5432/nouxcube")

    # Learning thresholds
    min_interactions_for_learning: int = 5
    learning_rate: float = 0.1
    decay_factor: float = 0.95

    class Config:
        env_file = ".env"
        case_sensitive = False


# Singleton instance
learning_settings = LearningSettings()
