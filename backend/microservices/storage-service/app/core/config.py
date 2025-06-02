import os
from typing import Optional

class Settings:
    """Configuración del storage microservice"""
    
    # API Security
    API_KEY: str = os.getenv("STORAGE_API_KEY", "your-secret-api-key-here")
    
    # Google Cloud Storage
    GCS_PROJECT_ID: str = os.getenv("GCS_PROJECT_ID", "your-project-id")
    GCS_CREDENTIALS: Optional[str] = os.getenv("GCS_CREDENTIALS")
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "nexus-documents")
    SIGNED_URL_EXPIRATION: int = int(os.getenv("SIGNED_URL_EXPIRATION", "3600"))  # 1 hour
    
    # Service
    SERVICE_NAME: str = "storage-service"
    SERVICE_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # File limits
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "104857600"))  # 100MB
    ALLOWED_EXTENSIONS: set = {
        "pdf", "doc", "docx", "txt", "md", "csv", "xlsx", "xls"
    }
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    
    # Testing
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

settings = Settings()