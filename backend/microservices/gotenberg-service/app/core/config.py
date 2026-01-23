"""
Configuration for Gotenberg Service
"""
import os
from typing import List

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Service configuration"""
    
    # Service settings
    SERVICE_NAME: str = "gotenberg-service"
    SERVICE_PORT: int = 8005
    LOG_LEVEL: str = "INFO"
    
    # Security
    SECRET_KEY: str
    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )
    
    # Gotenberg configuration (local instance in same container)
    GOTENBERG_BASE_URL: str = os.getenv("GOTENBERG_BASE_URL", "http://localhost:3000")
    
    # File processing configuration - Max upload size in bytes (default: 50MB)
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
        "txt", "md", "html", "htm", "rtf", "odt", "ods", "odp"
    ]

    # Image processing for thumbnails (configurable via env vars)
    THUMBNAIL_WIDTH: int = int(os.getenv("THUMBNAIL_WIDTH", "400"))
    THUMBNAIL_HEIGHT: int = int(os.getenv("THUMBNAIL_HEIGHT", "600"))
    THUMBNAIL_QUALITY: int = int(os.getenv("THUMBNAIL_QUALITY", "85"))

    # Conversion settings (configurable via env vars)
    PDF_CONVERSION_TIMEOUT: int = int(os.getenv("PDF_CONVERSION_TIMEOUT", "30"))  # seconds
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "3600"))  # default: 1 hour
    
    # Default tenant
    DEFAULT_TENANT: str = "default"
    
    # Security settings
    ALLOWED_ORIGINS: list = ["*"]  # Configure for production
    REQUIRE_TENANT_AUTH: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    

settings = Settings()
