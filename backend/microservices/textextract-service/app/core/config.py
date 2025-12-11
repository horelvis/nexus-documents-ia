"""
Configuration for the Text Extraction microservice.
Uses Apache Tika for document text extraction.
"""
from typing import List
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    service_name: str = "textextract-service"
    service_version: str = "2.0.0"  # Major version bump for Tika migration
    service_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("TEXT_EXTRACTION_SERVICE_PORT", "SERVICE_PORT"),
    )

    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )

    # Apache Tika configuration
    tika_url: str = Field(
        default="http://tika:9998",
        validation_alias=AliasChoices("TIKA_URL"),
    )
    tika_timeout: int = 120  # seconds

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
        ".odt",
        ".rtf",
        ".epub",
        ".xml",
        ".json"
    ]

    max_file_size_mb: int = 50
    enable_language_detection: bool = True
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
