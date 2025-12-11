from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Configuration settings for Camunda service."""

    # Service info
    SERVICE_NAME: str = "camunda-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Camunda connection
    CAMUNDA_URL: str = "http://camunda:8080"
    CAMUNDA_ENGINE_REST: str = "/engine-rest"
    CAMUNDA_TIMEOUT: int = 30

    # API Security
    MICROSERVICES_API_KEY: str = ""

    # External services
    SIGNATURE_SERVICE_URL: str = "http://api:8000"

    @property
    def camunda_rest_url(self) -> str:
        """Full URL to Camunda REST API."""
        return f"{self.CAMUNDA_URL}{self.CAMUNDA_ENGINE_REST}"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
