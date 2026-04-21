import logging
import sys
import uuid
from pathlib import Path

import yaml
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.database import SessionLocal, engine
from app.db.models import Base, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLE_MAPPING_PATH = Path(__file__).parent.parent / "app" / "config" / "role_mapping.yaml"


def validate_role_mapping() -> dict:
    """Ensure role_mapping.yaml exists and is valid before init runs.

    The application cannot function without this file because it is the
    only source of translation between KeyCloak group names and the
    canonical application role identifiers used throughout the codebase.
    """
    if not ROLE_MAPPING_PATH.exists():
        print(
            f"FATAL: role_mapping.yaml not found at {ROLE_MAPPING_PATH}",
            file=sys.stderr,
        )
        print(
            "Create it before running init_db. See "
            "docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(ROLE_MAPPING_PATH) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict) or "group_to_role" not in config:
        print(
            "FATAL: role_mapping.yaml is missing the 'group_to_role' key",
            file=sys.stderr,
        )
        sys.exit(1)

    mapping = config["group_to_role"]
    if not isinstance(mapping, dict) or len(mapping) == 0:
        print(
            "FATAL: role_mapping.yaml has empty group_to_role mapping",
            file=sys.stderr,
        )
        sys.exit(1)

    # EVERYONE is a reserved wildcard for documents — it must NEVER appear
    # as a group mapping target.
    for group, role in mapping.items():
        if role == "EVERYONE":
            print(
                f"FATAL: group '{group}' maps to reserved literal EVERYONE. "
                "EVERYONE is a wildcard for documents only, not a regular role.",
                file=sys.stderr,
            )
            sys.exit(1)

    logger.info("role_mapping.yaml validated: %d groups configured", len(mapping))
    return mapping


def init_db() -> None:
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tablas creadas exitosamente")

        # Verificar si ya existe un usuario administrador
        admin_user = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin_user:
            admin_id = uuid.uuid4()
            admin_user = User(
                id=admin_id,
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                full_name="Admin User",
                is_superuser=True,
            )
            db.add(admin_user)
            logger.info(f"Usuario administrador creado con ID: {admin_id}")
        else:
            logger.info(f"Usuario administrador ya existe con ID: {admin_user.id}")

        db.commit()
        logger.info("Inicialización de la base de datos completada")
    except SQLAlchemyError as e:
        logger.error(f"Error durante la inicialización de la base de datos: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Validando role_mapping.yaml antes de inicializar la base de datos")
    validate_role_mapping()
    logger.info("Creando tablas iniciales y datos de la base de datos")
    init_db()
    logger.info("Inicialización completada")
