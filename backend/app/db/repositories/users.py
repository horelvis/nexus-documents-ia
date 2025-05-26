from typing import Optional, Dict, Any
from prisma import Prisma
from prisma.models import User as PrismaUser # To avoid Pydantic model collision
from prisma.errors import RecordNotFoundError
# Assuming Pydantic schemas exist, e.g., from app.schemas.user import UserCreate, UserUpdate
# For now, we'll use Dict[str, Any] for data payloads

# Prisma client instance
# In a full FastAPI application, manage connect/disconnect via lifespan events
# or a dependency system.
# prisma_client = Prisma()

async def get_user(db: Prisma, user_id: str) -> Optional[PrismaUser]:
    """
    Get a user by their ID.
    """
    try:
        # Example: await prisma_client.connect() if not connected
        user = await db.user.find_unique(where={"id": user_id})
        return user
    except Exception as e:
        print(f"Error fetching user by ID: {e}")
        return None
    # finally:
        # Example: await prisma_client.disconnect() if connected by this function

async def get_user_by_email(db: Prisma, email: str) -> Optional[PrismaUser]:
    """
    Get a user by their email.
    """
    try:
        user = await db.user.find_unique(where={"email": email})
        return user
    except Exception as e:
        print(f"Error fetching user by email: {e}")
        return None

async def get_user_by_clerk_id(db: Prisma, clerk_user_id: str) -> Optional[PrismaUser]:
    """
    Get a user by their Clerk User ID.
    """
    if not clerk_user_id:
        return None
    try:
        user = await db.user.find_unique(where={"clerkUserId": clerk_user_id})
        return user
    except Exception as e:
        print(f"Error fetching user by Clerk ID: {e}")
        return None

async def create_user(db: Prisma, user_data: Dict[str, Any]) -> PrismaUser:
    """
    Create a new user.
    user_data should conform to Prisma's UserCreateInput,
    e.g., {"email": "a@b.com", "hashedPassword": "...", "tenantId": "...", "clerkUserId": "..."}
    """
    # Ensure required fields are present if not using Pydantic validation here
    if not all(k in user_data for k in ["email", "tenantId"]):
        raise ValueError("Email and tenantId are required to create a user.")
        
    try:
        user = await db.user.create(data=user_data)
        return user
    except Exception as e:
        # More specific error handling can be added here (e.g., unique constraint violations)
        print(f"Error creating user: {e}")
        raise

async def update_user(db: Prisma, user_id: str, user_data: Dict[str, Any]) -> Optional[PrismaUser]:
    """
    Update an existing user.
    user_data should conform to Prisma's UserUpdateInput.
    """
    try:
        user = await db.user.update(where={"id": user_id}, data=user_data)
        return user
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error updating user: {e}")
        raise

async def delete_user(db: Prisma, user_id: str) -> Optional[PrismaUser]:
    """
    Delete a user by their ID.
    """
    try:
        user = await db.user.delete(where={"id": user_id})
        return user
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error deleting user: {e}")
        raise

# Example usage (for testing purposes, remove in production)
# async def main():
#     db = Prisma()
#     await db.connect()
#     try:
#         # Create a tenant first (assuming tenants repository and schema exist)
#         # new_tenant = await create_tenant(db, {"name": "Test Tenant Inc."})
#         # if not new_tenant:
#         #     print("Failed to create tenant for user example.")
#         #     return
#
#         # user_to_create = {
#         #     "email": "test2@example.com",
#         #     "hashedPassword": "securepassword123",
#         #     "fullName": "Test User Two",
#         #     "tenantId": new_tenant.id, # Use actual tenant ID
#         #     "clerkUserId": "clerk_test_user_002"
#         # }
#         # new_user = await create_user(db, user_to_create)
#         # print(f"Created user: {new_user.id if new_user else 'Failed'}")
#
#         # if new_user:
#         #     fetched_user = await get_user(db, new_user.id)
#         #     print(f"Fetched user: {fetched_user.email if fetched_user else 'Not found'}")
#
#         #     updated_user = await update_user(db, new_user.id, {"fullName": "Test User Two Updated"})
#         #     print(f"Updated user: {updated_user.fullName if updated_user else 'Failed to update'}")
#
#         #     # deleted_user = await delete_user(db, new_user.id)
#         #     # print(f"Deleted user: {deleted_user.id if deleted_user else 'Failed to delete'}")
#         pass
#     finally:
#         await db.disconnect()

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
