from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
import logging

# Añadir el directorio padre al path para importar modelos
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.models import Base
# Domain model imports — ensure their tables are in Base.metadata for autogenerate.
from app.db.agent_models import Agent  # noqa: F401
from app.core.config import settings

logger = logging.getLogger("alembic.env")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def get_version_locations():
    """
    Get migration version locations based on deployment mode.

    This supports module-aware migrations:
        - Core migrations (always applied)
        - SaaS-specific migrations (only in saas mode)
        - On-Premise-specific migrations (only in on_premise mode)

    Directory structure (future):
        alembic/versions/          <- default (all migrations for now)
        alembic/versions/core/     <- shared migrations
        alembic/versions/saas/     <- SaaS-only migrations
        alembic/versions/on_premise/ <- On-premise-only migrations

    Returns:
        List of version location paths
    """
    base_dir = os.path.dirname(__file__)
    default_location = os.path.join(base_dir, "versions")
    # NOTE: `versions/_archived/` holds the pre-nouxcube migration history for
    # reference only. Alembic only scans the top-level of each location path,
    # so _archived is invisible to autogenerate/upgrade. DO NOT add it to the
    # returned list below without first checking the multi-tenancy removal plan
    # (docs/superpowers/plans/2026-04-06-remove-tenancy-01-foundation.md).

    # Check for module-specific migration folders
    core_dir = os.path.join(base_dir, "versions", "core")
    saas_dir = os.path.join(base_dir, "versions", "saas")
    on_premise_dir = os.path.join(base_dir, "versions", "on_premise")

    # Get deployment mode
    deployment_mode = os.getenv("DEPLOYMENT_MODE", "on_premise").lower()

    # If module-specific directories don't exist, use default
    if not any(os.path.isdir(d) for d in [core_dir, saas_dir, on_premise_dir]):
        return [default_location]

    # Build version locations based on deployment mode
    locations = []

    # Core migrations are always included
    if os.path.isdir(core_dir):
        locations.append(core_dir)

    # Add deployment-specific migrations
    if deployment_mode == "saas" and os.path.isdir(saas_dir):
        locations.append(saas_dir)
    elif deployment_mode == "on_premise" and os.path.isdir(on_premise_dir):
        locations.append(on_premise_dir)
    elif deployment_mode == "custom":
        # Custom mode: include both (developer can control via env vars)
        if os.path.isdir(saas_dir):
            locations.append(saas_dir)
        if os.path.isdir(on_premise_dir):
            locations.append(on_premise_dir)

    # If no specific locations found, fallback to default
    if not locations:
        locations = [default_location]

    logger.info(f"Migration version locations for {deployment_mode} mode: {locations}")
    return locations

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def get_url():
    """Get database URL from settings or config"""
    # Primero intentar desde settings
    if hasattr(settings, 'SQLALCHEMY_DATABASE_URI') and settings.SQLALCHEMY_DATABASE_URI:
        return settings.SQLALCHEMY_DATABASE_URI
    
    # Fallback a config de alembic
    return config.get_main_option("sqlalchemy.url")

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Override the sqlalchemy.url in the config
    configuration = config.get_section(config.config_ini_section)
    configuration['sqlalchemy.url'] = get_url()
    
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()