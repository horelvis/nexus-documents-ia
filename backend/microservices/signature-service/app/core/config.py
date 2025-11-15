"""
Configuration for Signature Microservice
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Service Info
    SERVICE_NAME: str = "signature-service"
    SERVICE_VERSION: str = "1.0.0"
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str
    MICROSERVICES_API_KEY: str
    
    # Encryption for credentials
    SIGNATURE_ENCRYPTION_KEY: Optional[str] = os.getenv("SIGNATURE_ENCRYPTION_KEY")
    
    # Redis Configuration (for caching)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    
    # Main API URL (for callbacks)
    MAIN_API_URL: str = os.getenv("MAIN_API_URL", "http://backend:8000")
    
    # Provider specific settings
    DOCUSIGN_OAUTH_BASE_URL: str = "https://account-d.docusign.com"  # Sandbox
    DOCUSIGN_API_BASE_URL: str = "https://demo.docusign.net/restapi"  # Sandbox
    
    YOUSIGN_SANDBOX_URL: str = "https://api-sandbox.yousign.app/v3"
    YOUSIGN_PRODUCTION_URL: str = "https://api.yousign.app/v3"
    
    SIGNATURIT_SANDBOX_URL: str = "https://api.sandbox.signaturit.com/v3"
    SIGNATURIT_PRODUCTION_URL: str = "https://api.signaturit.com/v3"
    
    # Webhook settings
    WEBHOOK_TIMEOUT: int = 30
    WEBHOOK_MAX_RETRIES: int = 3
    
    # Request limits
    MAX_SIGNERS_PER_REQUEST: int = 10
    MAX_DOCUMENT_SIZE_MB: int = 25
    
    # Development
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
