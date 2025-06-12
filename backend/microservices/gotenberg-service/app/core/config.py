"""
Configuration for Gotenberg Service
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration"""
    
    # Service settings
    SERVICE_NAME: str = "gotenberg-service"
    SERVICE_PORT: int = 8005
    LOG_LEVEL: str = "INFO"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this")
    API_KEY: str = os.getenv("API_KEY", "your-secret-api-key-here")
    
    # Gotenberg configuration (local instance in same container)
    GOTENBERG_BASE_URL: str = os.getenv("GOTENBERG_BASE_URL", "http://localhost:3000")
    
    # File processing configuration
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
        "txt", "md", "html", "htm", "rtf", "odt", "ods", "odp"
    ]
    
    # Image processing for thumbnails
    THUMBNAIL_WIDTH: int = 400
    THUMBNAIL_HEIGHT: int = 600
    THUMBNAIL_QUALITY: int = 85
    
    # Conversion settings
    PDF_CONVERSION_TIMEOUT: int = 30  # seconds
    CACHE_ENABLED: bool = True
    CACHE_TTL: int = 3600  # 1 hour
    
    # Default tenant
    DEFAULT_TENANT: str = "default"
    
    # Security settings
    ALLOWED_ORIGINS: list = ["*"]  # Configure for production
    REQUIRE_TENANT_AUTH: bool = True
    
    class Config:
        env_file = ".env"


settings = Settings()