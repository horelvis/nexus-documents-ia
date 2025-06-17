import sys
from pathlib import Path

# Add parent directory to path to import common_security
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from common_security import (
    create_security_dependency,
    create_tenant_validator,
    get_api_key_from_header,
    get_tenant_id_from_header,
    get_user_id_from_header
)
from .config import settings

# Create security dependency with service API key
validate_service_access = create_security_dependency(settings.service_api_key)
validate_tenant_access = create_tenant_validator()