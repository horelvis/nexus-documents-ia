"""
Configuration for the Text Extraction microservice.
Supports pluggable backends: Apache Tika (default) and IBM Docling.
"""
from typing import List
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    service_name: str = "textextract-service"
    service_version: str = "2.1.0"  # Docling backend support
    service_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("TEXT_EXTRACTION_SERVICE_PORT", "SERVICE_PORT"),
    )

    MICROSERVICES_API_KEY: str = Field(
        validation_alias=AliasChoices("MICROSERVICES_API_KEY")
    )

    # Extraction backend: "tika" (default) or "docling"
    extraction_backend: str = Field(
        default="tika",
        validation_alias=AliasChoices("EXTRACTION_BACKEND"),
    )
    # Fallback to Tika if primary backend (Docling) fails
    extraction_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXTRACTION_FALLBACK_ENABLED"),
    )

    # Apache Tika configuration
    tika_url: str = Field(
        default="http://tika:9998",
        validation_alias=AliasChoices("TIKA_URL"),
    )
    tika_timeout: int = 120  # seconds

    # IBM Docling configuration
    docling_url: str = Field(
        default="http://docling:5001",
        validation_alias=AliasChoices("DOCLING_URL"),
    )
    docling_timeout: int = 300  # 3.1 sec/page × ~100 pages max

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
        ".json",
        # Images - Tika will attempt OCR if configured
        ".jpg",
        ".jpeg",
        ".png",
        ".tiff",
        ".tif",
        ".bmp",
        ".gif",
    ]

    max_file_size_mb: int = 50
    enable_language_detection: bool = True
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
