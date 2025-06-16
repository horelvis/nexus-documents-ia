#!/usr/bin/env python3
"""
Script para inicializar la base de datos creando todas las tablas
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.base_class import Base
from app.db.database import engine
from app.db.models import *  # Importar todos los modelos
from app.core.config import settings

def init_database():
    """Crear todas las tablas en la base de datos"""
    print(f"🔧 Inicializando base de datos...")
    print(f"📍 Database URL: {settings.SQLALCHEMY_DATABASE_URI}")
    
    try:
        # Crear todas las tablas
        Base.metadata.create_all(bind=engine)
        print("✅ Tablas creadas exitosamente")
        
        # Verificar tablas creadas
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        print(f"\n📊 Tablas creadas ({len(tables)}):")
        for table in sorted(tables):
            print(f"  - {table}")
            
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")
        raise

if __name__ == "__main__":
    init_database()