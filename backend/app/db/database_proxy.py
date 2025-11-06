"""
Database Proxy - Environment-aware database connection management
"""

import os
import logging
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseProxy:
    """
    Database proxy that automatically detects environment and configures 
    the appropriate database connection (local, Docker, Cloud SQL, etc.)
    """
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialized = False
        
    def detect_environment(self) -> str:
        """Detect the current environment"""
        # Cloud Run detection
        if os.getenv("K_SERVICE"):
            return "cloud_run"
        
        # Docker detection  
        if os.path.exists("/.dockerenv"):
            return "docker"
            
        # Local development
        return "local"
    
    def get_cloud_sql_uri(self) -> str:
        """Build Cloud SQL connection URI"""
        db_user = os.getenv("POSTGRES_USER", "postgres")
        db_password = os.getenv("POSTGRES_PASSWORD", "")
        db_name = os.getenv("POSTGRES_DB", "nexusdocuments360db")
        db_socket_dir = "/cloudsql"
        cloud_sql_connection_name = "nexusdocs360-pre:europe-west1:nexusdocuments360db"
        
        return f"postgresql://{db_user}:{db_password}@/{db_name}?host={db_socket_dir}/{cloud_sql_connection_name}"
    
    def get_local_uri(self) -> str:
        """Build local/Docker connection URI"""
        # Use existing settings configuration
        return settings.SQLALCHEMY_DATABASE_URI
    
    def create_engine_for_environment(self, env: str):
        """Create appropriate engine for environment"""
        
        if env == "cloud_run":
            logger.info("🌩️ Configuring for Cloud Run + Cloud SQL")
            db_uri = self.get_cloud_sql_uri()
            
            # Cloud SQL optimizations
            engine = create_engine(
                db_uri,
                poolclass=NullPool,  # No connection pooling for Cloud SQL
                pool_pre_ping=True,
                pool_recycle=300,
                echo=settings.DEBUG,
                connect_args={
                    "connect_timeout": 10,
                    "application_name": "nexus-backend-cloud-run"
                }
            )
            
        elif env == "docker":
            logger.info("🐳 Configuring for Docker environment")
            db_uri = self.get_local_uri()
            
            # Docker optimizations
            engine = create_engine(
                db_uri,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=settings.DEBUG
            )
            
        else:  # local
            logger.info("💻 Configuring for local development")
            db_uri = self.get_local_uri()
            
            # Local development optimizations
            engine = create_engine(
                db_uri,
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=settings.DEBUG
            )
        
        return engine
    
    def initialize(self) -> bool:
        """Initialize database connection based on environment"""
        if self._initialized:
            return True
            
        try:
            # Detect environment
            env = self.detect_environment()
            logger.info(f"🔍 Detected environment: {env}")
            
            # Create appropriate engine
            self.engine = self.create_engine_for_environment(env)
            
            # Test connection
            logger.info("🧪 Testing database connection...")
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("✅ Database connection successful")
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False, 
                autoflush=False, 
                bind=self.engine
            )
            
            self._initialized = True
            logger.info("✅ Database proxy initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database proxy initialization failed: {e}")
            return False
    
    def get_engine(self):
        """Get database engine (initialize if needed)"""
        if not self._initialized:
            self.initialize()
        return self.engine
    
    def get_session_local(self):
        """Get session factory (initialize if needed)"""
        if not self._initialized:
            self.initialize()
        return self.SessionLocal
    
    def create_tables(self):
        """Create database tables"""
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("Cannot create tables - database not initialized")
        
        try:
            logger.info("🏗️ Creating database tables...")
            from app.db.base_class import Base
            import app.db.models  # Import to register models
            
            Base.metadata.create_all(bind=self.engine)
            logger.info("✅ Database tables created successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if database is healthy"""
        try:
            if not self.engine:
                return False
                
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
            
        except Exception:
            return False

# Global database proxy instance
db_proxy = DatabaseProxy()

# Compatibility functions for existing code
def get_engine():
    """Get database engine"""
    return db_proxy.get_engine()

def get_db():
    """Get database session"""
    SessionLocal = db_proxy.get_session_local()
    if SessionLocal is None:
        raise RuntimeError("Database not initialized")
        
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Legacy compatibility
engine = property(lambda self: db_proxy.get_engine())
SessionLocal = property(lambda self: db_proxy.get_session_local())