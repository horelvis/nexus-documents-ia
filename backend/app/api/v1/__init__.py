from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router
from app.api.v1.tenants import router as tenants_router

# Optional: Define __all__ to specify what gets imported with 'from app.api.v1 import *'
# For clarity, it's often better to rely on specific imports as done in main.py,
# but __all__ can be good practice.
__all__ = [
    "admin_router",
    "auth_router",
    "documents_router",
    "search_router",
    "tenants_router",
]