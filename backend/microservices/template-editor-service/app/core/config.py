"""
Template Editor Service Configuration
"""
from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service Configuration
    service_name: str = "template-editor-service"
    service_port: int = 8011
    debug: bool = True
    log_level: str = "INFO"
    
    # Database
    database_url: str = "postgresql+asyncpg://nexus_user:nexus_password@db:5432/nexus_db"
    
    # Google APIs
    google_credentials_path: str = "/app/credentials/google-service-account.json"
    google_drive_folder_id: Optional[str] = None  # Optional parent folder for temp docs
    
    # Security
    microservices_api_key: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    
    # Redis for session management
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 2  # Different DB for template sessions
    
    # Session Configuration
    edit_session_timeout_hours: int = 2
    cleanup_interval_minutes: int = 15
    
    # Storage Service Integration
    storage_service_url: str = "http://storage-service:8003"
    
    # Main API Integration
    main_api_url: str = "http://api:8000"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
