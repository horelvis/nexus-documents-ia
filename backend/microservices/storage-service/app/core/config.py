import os
import logging
from typing import Optional

# Configurar logging temprano
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings:
    """Configuración del storage microservice"""
    
    # API Security
    API_KEY: str = os.getenv("API_KEY", "your-secret-api-key-here")
    
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
        "pdf", "doc", "docx", "txt", "md", "csv", "xlsx", "xls",
        "png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp", "json"
    }
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    
    # Testing
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

# Crear instancia y log de configuración
settings = Settings()

# Log de variables importantes para debugging
logger.info("=== STORAGE SERVICE CONFIGURATION ===")
logger.info(f"API_KEY: {settings.API_KEY[:10]}... (masked)")
logger.info(f"GCS_PROJECT_ID: {settings.GCS_PROJECT_ID}")
logger.info(f"GCS_CREDENTIALS: {settings.GCS_CREDENTIALS}")
logger.info(f"GCS_BUCKET_NAME: {settings.GCS_BUCKET_NAME}")
logger.info(f"DEBUG: {settings.DEBUG}")
logger.info(f"TESTING: {settings.TESTING}")
logger.info(f"REDIS_HOST: {settings.REDIS_HOST}")
logger.info(f"REDIS_PORT: {settings.REDIS_PORT}")
logger.info("=== END CONFIGURATION ===")

# Log de variables de entorno raw
logger.info("=== RAW ENVIRONMENT VARIABLES ===")
for key in ["API_KEY", "GCS_PROJECT_ID", "GCS_CREDENTIALS", "GCS_BUCKET_NAME", "DEBUG", "TESTING", "REDIS_HOST", "REDIS_PORT"]:
    value = os.getenv(key, "NOT_SET")
    if key == "API_KEY" and value != "NOT_SET":
        value = f"{value[:10]}... (masked)"
    logger.info(f"ENV {key}: {value}")
logger.info("=== END RAW ENV VARS ===")