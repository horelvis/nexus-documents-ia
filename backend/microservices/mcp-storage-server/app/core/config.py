"""
Configuration for MCP Storage Server.

Loads settings from environment variables.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """MCP Storage Server settings."""

    # Service configuration
    service_name: str = "mcp-storage-server"
    service_port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Storage Provider: "gcs" or "local"
    storage_provider: str = os.getenv("STORAGE_PROVIDER", "gcs")

    # GCS Configuration (when storage_provider=gcs)
    gcs_project_id: str = os.getenv("GCS_PROJECT_ID", "")
    gcs_credentials: str = os.getenv("GCS_CREDENTIALS", "")
    gcs_default_bucket: str = os.getenv("GCS_DEFAULT_BUCKET", "nexus-documents")
    gcs_location: str = os.getenv("GCS_LOCATION", "europe-west1")

    # Local Storage Configuration (when storage_provider=local)
    local_storage_path: str = os.getenv("LOCAL_STORAGE_PATH", "/app/storage")
    local_storage_base_url: str = os.getenv("LOCAL_STORAGE_BASE_URL", "http://localhost:8000")
    signed_url_secret: str = os.getenv("SIGNED_URL_SECRET", "local-storage-secret-change-me")

    # Signed URL settings
    signed_url_expiration: int = int(os.getenv("SIGNED_URL_EXPIRATION", "3600"))  # 1 hour

    # File size limits
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))

    # Allowed file extensions
    allowed_extensions: str = os.getenv(
        "ALLOWED_EXTENSIONS",
        "pdf,doc,docx,xls,xlsx,ppt,pptx,txt,csv,json,xml,png,jpg,jpeg,gif,webp"
    )

    # Security
    require_tenant_id: bool = os.getenv("REQUIRE_TENANT_ID", "true").lower() == "true"

    # Testing mode
    testing: bool = os.getenv("TESTING", "false").lower() == "true"

    @property
    def allowed_extensions_list(self) -> list:
        """Get allowed extensions as a list."""
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
