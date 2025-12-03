"""
Configuration for the Text Extraction microservice.
"""
from typing import List
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    service_name: str = "textextract-service"
    service_version: str = "1.0.0"
    service_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("TEXT_EXTRACTION_SERVICE_PORT", "SERVICE_PORT"),
    )

    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )

    allowed_extensions: List[str] = [
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".md",
        ".csv",
        ".ppt",
        ".pptx",
        ".xlsx",
        ".xls",
        ".html",
        ".odt"
    ]

    max_file_size_mb: int = 50
    default_strategy: str = "auto"  # auto, fast, hi_res
    enable_language_detection: bool = True
    log_level: str = "INFO"
    nltk_data_dir: str = "/app/nltk_data"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
