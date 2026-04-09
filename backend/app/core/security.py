from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_collection_name(collection_type: str = "documents") -> str:
    """Generate the Weaviate collection name for the deployment.

    In single-tenant mode the collection namespace collapses to a single
    deployment-wide name keyed only by the collection type.
    """
    return f"nouxcube_{collection_type}".lower()