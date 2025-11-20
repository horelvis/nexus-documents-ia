import os
import logging
from typing import Optional

# Configurar logging temprano
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings:
    """Configuración del storage microservice"""
    
    # API Security
    MICROSERVICES_API_KEY: str = os.getenv("MICROSERVICES_API_KEY", "")
    
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
    _DEFAULT_ALLOWED_EXTENSIONS = "pdf,doc,docx,txt,md,csv,xlsx,xls,png,jpg,jpeg,gif,bmp,tiff,webp,json,odt"
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    
    # Testing
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD")

    def __init__(self):
        allowed_extensions_raw = (
            os.getenv("STORAGE_ALLOWED_EXTENSIONS")
            or os.getenv("ALLOWED_EXTENSIONS")
            or self._DEFAULT_ALLOWED_EXTENSIONS
        )
        self.ALLOWED_EXTENSIONS = {
            ext.strip().lower()
            for ext in allowed_extensions_raw.split(",")
            if ext.strip()
        }

# Crear instancia y log de configuración
settings = Settings()

if not settings.MICROSERVICES_API_KEY:
    raise EnvironmentError("MICROSERVICES_API_KEY environment variable is required for storage-service")

# Log de variables importantes para debugging
logger.info("=== STORAGE SERVICE CONFIGURATION ===")
masked_api_key = f"{settings.MICROSERVICES_API_KEY[:10]}... (masked)" if settings.MICROSERVICES_API_KEY else "NOT_SET"
logger.info(f"MICROSERVICES_API_KEY: {masked_api_key}")
logger.info(f"GCS_PROJECT_ID: {settings.GCS_PROJECT_ID}")
logger.info(f"GCS_CREDENTIALS: {settings.GCS_CREDENTIALS}")
logger.info(f"GCS_BUCKET_NAME: {settings.GCS_BUCKET_NAME}")
logger.info(f"DEBUG: {settings.DEBUG}")
logger.info(f"TESTING: {settings.TESTING}")
logger.info(f"REDIS_HOST: {settings.REDIS_HOST}")
logger.info(f"REDIS_PORT: {settings.REDIS_PORT}")
logger.info(f"ALLOWED_EXTENSIONS: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}")
logger.info("=== END CONFIGURATION ===")

# Log de variables de entorno raw
logger.info("=== RAW ENVIRONMENT VARIABLES ===")
for key in ["MICROSERVICES_API_KEY", "GCS_PROJECT_ID", "GCS_CREDENTIALS", "GCS_BUCKET_NAME", "DEBUG", "TESTING", "REDIS_HOST", "REDIS_PORT", "STORAGE_ALLOWED_EXTENSIONS"]:
    value = os.getenv(key, "NOT_SET")
    if key == "MICROSERVICES_API_KEY" and value not in ("NOT_SET", ""):
        value = f"{value[:10]}... (masked)"
    elif key == "MICROSERVICES_API_KEY":
        value = "NOT_SET"
    logger.info(f"ENV {key}: {value}")
logger.info("=== END RAW ENV VARS ===")
