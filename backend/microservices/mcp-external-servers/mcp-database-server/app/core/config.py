"""
Configuration for MCP Database Server.

Database connections are configured via environment or YAML.
"""

import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import yaml


class DatabaseConfig(BaseModel):
    """Configuration for a single database connection."""
    name: str
    db_type: str = "postgresql"  # postgresql, mysql, mongodb
    host: str
    port: int
    database: str
    username: str
    password: str

    # Access control
    tenant_whitelist: Optional[List[str]] = None
    tenant_blacklist: List[str] = Field(default_factory=list)

    # Query limits (security)
    max_rows: int = 1000
    timeout_seconds: int = 30
    read_only: bool = True  # ALWAYS true for security

    @property
    def connection_url(self) -> str:
        """Build connection URL."""
        if self.db_type == "postgresql":
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "mysql":
            return f"mysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "mongodb":
            return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        return ""

    def is_accessible_by_tenant(self, tenant_id: str) -> bool:
        if tenant_id in self.tenant_blacklist:
            return False
        if self.tenant_whitelist is not None:
            return tenant_id in self.tenant_whitelist
        return True


class Settings(BaseSettings):
    """MCP Database Server settings."""

    service_name: str = "mcp-database-server"
    service_port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    config_file: str = os.getenv("DB_CONFIG_FILE", "/app/config/databases.yaml")

    # Security: Blocked SQL keywords
    blocked_keywords: str = "INSERT,UPDATE,DELETE,DROP,TRUNCATE,ALTER,CREATE,GRANT,REVOKE"

    @property
    def blocked_keywords_list(self) -> List[str]:
        return [k.strip().upper() for k in self.blocked_keywords.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()


def load_databases() -> Dict[str, DatabaseConfig]:
    """Load database configurations."""
    databases = {}

    if os.path.exists(settings.config_file):
        try:
            with open(settings.config_file, 'r') as f:
                config = yaml.safe_load(f)

            if config and 'databases' in config:
                for db in config['databases']:
                    # Expand environment variables
                    for key in ['password', 'username']:
                        if key in db and isinstance(db[key], str):
                            if db[key].startswith("${") and db[key].endswith("}"):
                                env_var = db[key][2:-1]
                                db[key] = os.getenv(env_var, "")

                    database = DatabaseConfig(**db)
                    databases[database.name] = database

        except Exception as e:
            import logging
            logging.error(f"Failed to load DB config: {e}")

    return databases


_databases: Optional[Dict[str, DatabaseConfig]] = None


def get_databases() -> Dict[str, DatabaseConfig]:
    global _databases
    if _databases is None:
        _databases = load_databases()
    return _databases
