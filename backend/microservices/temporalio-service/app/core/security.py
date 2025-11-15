"""Security utilities for Temporalio Service"""
import hashlib
import hmac
from typing import Optional

from app.core.config import settings


def verify_api_key(api_key: str) -> bool:
    """
    Verify API key against the configured microservices API key
    
    Args:
        api_key: API key to verify
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not api_key:
        return False
    
    # For development, use simple string comparison
    if settings.debug:
        return api_key == settings.MICROSERVICES_API_KEY
    
    # For production, use secure comparison
    expected_key = settings.MICROSERVICES_API_KEY
    return hmac.compare_digest(api_key, expected_key)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash password with salt
    
    Args:
        password: Plain text password
        salt: Optional salt, generates one if not provided
        
    Returns:
        Tuple of (hashed_password, salt)
    """
    if salt is None:
        salt = hashlib.sha256(password.encode()).hexdigest()[:16]
    
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """
    Verify password against hash
    
    Args:
        password: Plain text password
        hashed_password: Hashed password to compare against
        salt: Salt used for hashing
        
    Returns:
        bool: True if password matches, False otherwise
    """
    test_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(test_hash, hashed_password)


def generate_api_key() -> str:
    """
    Generate a new API key
    
    Returns:
        str: Generated API key
    """
    import secrets
    return f"nxs_temp_{secrets.token_urlsafe(32)}"
