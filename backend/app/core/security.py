from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_tenant_collection_name(tenant_id: str, collection_type: str = "documents") -> str:
    """Generate tenant-specific collection name for Weaviate"""
    return f"nexus_{tenant_id}_{collection_type}".lower().replace("-", "_")