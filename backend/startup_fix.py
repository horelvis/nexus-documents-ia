#!/usr/bin/env python3
"""
Script de arranque que maneja errores de SQLAlchemy y ejecuta migraciones
"""
import os
import sys
import logging
from sqlalchemy import create_engine, text, inspect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_database_schema():
    """Fix database schema issues before starting the app"""
    try:
        from app.core.config import settings
        
        # Create engine
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check existing tables
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            logger.info(f"Existing tables: {tables}")
            
            # Remove problematic foreign keys
            if 'subscriptions' in tables:
                try:
                    conn.execute(text("ALTER TABLE subscriptions DROP CONSTRAINT IF EXISTS subscriptions_plan_id_fkey"))
                    conn.commit()
                    logger.info("Dropped foreign key constraint")
                except Exception as e:
                    logger.info(f"No foreign key to drop: {e}")
            
            # Drop problematic tables
            for table in ['prices', 'plans']:
                if table in tables:
                    try:
                        conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                        conn.commit()
                        logger.info(f"Dropped table: {table}")
                    except Exception as e:
                        logger.info(f"Could not drop {table}: {e}")
        
        logger.info("Database cleanup completed")
        return True
        
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting database fix...")
    success = fix_database_schema()
    
    if success:
        logger.info("Database fixed, now running migrations...")
        os.system("alembic upgrade head")
        logger.info("Starting application...")
        os.system("uvicorn app.main:app --host 0.0.0.0 --port 8000")
    else:
        logger.error("Could not fix database, exiting...")
        sys.exit(1)