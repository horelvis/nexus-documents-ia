#!/usr/bin/env python3
"""
Script to make a user a superuser by email
Usage: python scripts/make_superuser.py user@email.com
"""
import sys
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.db.models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def make_superuser(email: str) -> None:
    """Make a user a superuser by email"""
    db = SessionLocal()
    try:
        # Find user by email
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            logger.error(f"User with email '{email}' not found")
            return
        
        if user.is_superuser:
            logger.info(f"User '{email}' is already a superuser")
            return
        
        # Make user a superuser
        user.is_superuser = True
        db.commit()
        
        logger.info(f"✅ User '{email}' is now a superuser!")
        logger.info(f"User ID: {user.id}")
        logger.info(f"Tenant ID: {user.tenant_id}")
        
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def list_users() -> None:
    """List all users and their superuser status"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        if not users:
            logger.info("No users found in database")
            return
        
        logger.info("\nCurrent users:")
        logger.info("-" * 60)
        for user in users:
            status = "SUPERUSER" if user.is_superuser else "Regular"
            logger.info(f"{user.email} - {status} - Tenant: {user.tenant_id}")
        logger.info("-" * 60)
        
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("Usage: python scripts/make_superuser.py <email>")
        logger.info("Or: python scripts/make_superuser.py --list")
        logger.info("\nListing all users...")
        list_users()
        sys.exit(1)
    
    if sys.argv[1] == "--list":
        list_users()
    else:
        email = sys.argv[1]
        logger.info(f"Making user '{email}' a superuser...")
        make_superuser(email)