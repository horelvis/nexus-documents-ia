"""
Configuration for Gotenberg microservice
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Security configuration
    API_KEY: str = "your-secret-api-key-here"
    
    # Gotenberg configuration
    GOTENBERG_BASE_URL: str = "http://gotenberg:3000"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()