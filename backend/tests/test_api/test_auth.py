import pytest

def test_basic_import():
    """Test basic imports work"""
    from app.main import app
    from app.db.models import User, Tenant
    from app.core.security import get_password_hash
    assert app is not None
    assert User is not None
    assert Tenant is not None
    assert callable(get_password_hash)

def test_database_connection():
    """Test database connection works"""
    from app.db.database import get_db
    from sqlalchemy.orm import Session

    # Get a database session
    db_generator = get_db()
    db = next(db_generator)

    assert isinstance(db, Session)
    assert db is not None

    # Test basic query
    from app.db.models import Tenant
    tenants = db.query(Tenant).all()
    assert isinstance(tenants, list)

def test_app_startup():
    """Test that the FastAPI app can start up"""
    from app.main import app
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    assert len(app.routes) > 0  # Should have some routes registered

def test_core_modules():
    """Test core modules can be imported"""
    from app.core.config import settings
    from app.core.security import get_password_hash

    assert settings is not None
    assert callable(get_password_hash)

    # Test password hashing
    hashed = get_password_hash("test_password")
    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert hashed != "test_password"  # Should be hashed