#!/usr/bin/env python3
"""
Script para configurar la base de datos completa:
1. Crear todas las tablas usando SQLAlchemy
2. Ejecutar migraciones de Alembic
3. Crear datos iniciales
"""

import logging
import sys
import os
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Agregar el directorio raíz al path para imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import engine, SessionLocal
from app.db.models import Base
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_all_tables():
    """Crear todas las tablas usando SQLAlchemy"""
    try:
        logger.info("🗄️ Creating all database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✅ All tables created successfully")
    except Exception as e:
        logger.error(f"❌ Error creating tables: {e}")
        raise

def create_initial_data():
    """Crear datos iniciales"""
    db = SessionLocal()
    try:
        from app.db.models import Tenant, User
        from app.services.auth_service import AuthService
        import uuid
        
        logger.info("🏢 Creating initial tenant...")
        
        # Verificar si ya existe el tenant default
        tenant = db.query(Tenant).filter(Tenant.name == settings.DEFAULT_TENANT).first()
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(),
                name=settings.DEFAULT_TENANT,
                description="Default tenant for development",
                bucket_name=f"nexus-{settings.DEFAULT_TENANT}"
            )
            db.add(tenant)
            db.flush()
            logger.info(f"✅ Default tenant created: {tenant.id}")
        else:
            logger.info(f"ℹ️ Default tenant already exists: {tenant.id}")
        
        # Verificar si ya existe un usuario admin
        admin_user = db.query(User).filter(User.email == "admin@example.com").first()
        if not admin_user:
            logger.info("👤 Creating admin user...")
            admin_user = User(
                id=uuid.uuid4(),
                email="admin@example.com",
                hashed_password=AuthService.get_password_hash("admin123"),
                full_name="Admin User",
                is_superuser=True,
                is_active=True,
                tenant_id=tenant.id
            )
            db.add(admin_user)
            logger.info(f"✅ Admin user created: {admin_user.id}")
        else:
            logger.info(f"ℹ️ Admin user already exists: {admin_user.id}")
        
        db.commit()
        logger.info("✅ Initial data created successfully")
        
    except Exception as e:
        logger.error(f"❌ Error creating initial data: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def main():
    """Función principal"""
    logger.info("🚀 Starting database setup...")
    
    try:
        # 1. Crear todas las tablas
        create_all_tables()
        
        # 2. Crear datos iniciales
        create_initial_data()
        
        logger.info("🎉 Database setup completed successfully!")
        
    except Exception as e:
        logger.error(f"💥 Database setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()