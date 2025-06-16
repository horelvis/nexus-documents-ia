#!/usr/bin/env python3
"""
Script para verificar el estado de la base de datos y las migraciones
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from app.core.config import settings

def check_database():
    """Verificar el estado de la base de datos"""
    print("🔍 Verificando estado de la base de datos...")
    print(f"📍 Database URL: {settings.SQLALCHEMY_DATABASE_URI}")
    
    try:
        # Crear conexión
        engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
        
        # Verificar conexión
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Conexión a la base de datos exitosa")
            
            # Verificar si existe alembic_version
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'alembic_version'
                )
            """))
            
            table_exists = result.scalar()
            print(f"📋 Tabla alembic_version existe: {table_exists}")
            
            if table_exists:
                # Obtener versión actual
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                print(f"📌 Versión actual de Alembic: {version}")
            
            # Listar todas las tablas
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print(f"\n📊 Tablas existentes ({len(tables)}):")
            for table in sorted(tables):
                print(f"  - {table}")
                
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        return False
    
    return True

if __name__ == "__main__":
    check_database()