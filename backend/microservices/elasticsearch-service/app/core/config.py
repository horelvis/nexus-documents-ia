"""Configuration for Elasticsearch microservice"""
import os
from typing import Optional

class Settings:
    """Application settings"""

    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8008"))

    # Elasticsearch Configuration
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_USER: Optional[str] = os.getenv("ELASTICSEARCH_USER")
    ELASTICSEARCH_PASSWORD: Optional[str] = os.getenv("ELASTICSEARCH_PASSWORD")

    # Security
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "dev-api-key-2024")

    # Environment
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

settings = Settings()