from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

# Convert sync URL to async URL
def get_async_database_url():
    """Convert postgresql:// to postgresql+asyncpg://"""
    url = settings.SQLALCHEMY_DATABASE_URI
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

# Create async engine
async_engine = create_async_engine(
    get_async_database_url(),
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Dependency for FastAPI
async def get_async_db():
    """Dependency to get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def async_session_context() -> AsyncSession:
    """
    AsyncSession context manager for non-FastAPI/Depends code paths.

    Use this in background jobs, webhooks, utilities, etc.
    """
    async with AsyncSessionLocal() as session:
        yield session
