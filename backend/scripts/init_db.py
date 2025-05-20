import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import uuid

from app.db.database import SessionLocal
from app.db.models import Base, User, Tenant
from app.core.security import get_password_hash
from app.core.config import settings
from app.db.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db() -> None:
    db = SessionLocal()
    try:
        # Crear tablas
        Base.metadata.create_all(bind=engine)
        logger.info("Tablas creadas exitosamente")
        
        # Verificar si ya existe el tenant default
        tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
        if not tenant:
            # Crear tenant default
            tenant_id = uuid.uuid4()
            tenant = Tenant(
                id=tenant_id,
                name=settings.DEFAULT_TENANT,
                description="Default tenant",
                bucket_name=f"{settings.GCS_BUCKET_NAME}-{settings.DEFAULT_TENANT}"
            )
            db.add(tenant)
            db.flush()
            logger.info(f"Tenant default creado con ID: {tenant_id}")
        else:
            tenant_id = tenant.id
            logger.info(f"Tenant default ya existe con ID: {tenant_id}")
        
        # Verificar si ya existe un usuario administrador
        admin_user = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin_user:
            # Crear usuario administrador
            admin_id = uuid.uuid4()
            admin_user = User(
                id=admin_id,
                email="admin@example.com",
                hashed_password=get_password_hash("admin"),
                full_name="Admin User",
                is_superuser=True,
                tenant_id=tenant_id
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
    logger.info("Creando tablas iniciales y datos de la base de datos")
    init_db()
    logger.info("Inicialización completada")