import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "storage-service"
    service_port: int = int(os.getenv("SERVICE_PORT", "8010"))

    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_root_user: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    minio_root_password: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "nexus-storage")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    class Config:
        env_file = ".env"


settings = Settings()
