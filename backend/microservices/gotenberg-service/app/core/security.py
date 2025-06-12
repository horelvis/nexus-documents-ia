"""
Security module for Gotenberg Service
"""
import sys
import os

# Add the parent directory to Python path to import common_security
sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from common_security import create_security_dependency
from app.core.config import settings

# Create the security dependency using the common module
validate_service_access = create_security_dependency(settings.API_KEY)