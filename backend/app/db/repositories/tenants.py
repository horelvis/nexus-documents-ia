from typing import Optional, Dict, Any, List
from prisma import Prisma
from prisma.models import Tenant as PrismaTenant # To avoid Pydantic model collision
from prisma.errors import RecordNotFoundError
# Assuming Pydantic schemas exist, e.g., from app.schemas.tenant import TenantCreate, TenantUpdate
# For now, we'll use Dict[str, Any] for data payloads

async def get_tenant(db: Prisma, tenant_id: str) -> Optional[PrismaTenant]:
    """
    Get a tenant by their ID.
    """
    try:
        tenant = await db.tenant.find_unique(where={"id": tenant_id})
        return tenant
    except Exception as e:
        print(f"Error fetching tenant by ID: {e}")
        return None

async def get_tenant_by_name(db: Prisma, name: str) -> Optional[PrismaTenant]:
    """
    Get a tenant by their name.
    """
    try:
        tenant = await db.tenant.find_unique(where={"name": name})
        return tenant
    except Exception as e:
        print(f"Error fetching tenant by name: {e}")
        return None

async def list_tenants(db: Prisma, skip: int = 0, limit: int = 100) -> List[PrismaTenant]:
    """
    List tenants with pagination.
    """
    try:
        tenants = await db.tenant.find_many(skip=skip, take=limit)
        return tenants
    except Exception as e:
        print(f"Error listing tenants: {e}")
        return []

async def create_tenant(db: Prisma, tenant_data: Dict[str, Any]) -> PrismaTenant:
    """
    Create a new tenant.
    tenant_data should conform to Prisma's TenantCreateInput,
    e.g., {"name": "Awesome Corp", "description": "Details..."}
    """
    if "name" not in tenant_data:
        raise ValueError("Name is required to create a tenant.")
        
    try:
        tenant = await db.tenant.create(data=tenant_data)
        return tenant
    except Exception as e:
        print(f"Error creating tenant: {e}")
        raise

async def update_tenant(db: Prisma, tenant_id: str, tenant_data: Dict[str, Any]) -> Optional[PrismaTenant]:
    """
    Update an existing tenant.
    tenant_data should conform to Prisma's TenantUpdateInput.
    """
    try:
        tenant = await db.tenant.update(where={"id": tenant_id}, data=tenant_data)
        return tenant
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error updating tenant: {e}")
        raise

async def delete_tenant(db: Prisma, tenant_id: str) -> Optional[PrismaTenant]:
    """
    Delete a tenant by their ID.
    """
    try:
        # Note: Deleting a tenant might have cascading effects or restrictions
        # if other models (like User) depend on it.
        # Prisma's default behavior depends on the relation definitions (e.g., onDelete).
        # Ensure your schema handles this as intended.
        tenant = await db.tenant.delete(where={"id": tenant_id})
        return tenant
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error deleting tenant: {e}")
        raise

# Example usage (for testing purposes, remove in production)
# async def main():
#     db = Prisma()
#     await db.connect()
#     try:
#         # tenant_to_create = {
#         #     "name": f"My Test Tenant {random.randint(1, 1000)}",
#         #     "description": "This is a test tenant from script."
#         # }
#         # new_tenant = await create_tenant(db, tenant_to_create)
#         # print(f"Created tenant: {new_tenant.name if new_tenant else 'Failed'}")

#         # if new_tenant:
#         #     fetched_tenant = await get_tenant(db, new_tenant.id)
#         #     print(f"Fetched tenant: {fetched_tenant.name if fetched_tenant else 'Not found'}")

#         #     updated_tenant = await update_tenant(db, new_tenant.id, {"description": "Updated description."})
#         #     print(f"Updated tenant desc: {updated_tenant.description if updated_tenant else 'Failed to update'}")
        
#         #     # List tenants
#         #     all_tenants = await list_tenants(db, limit=5)
#         #     print(f"Found {len(all_tenants)} tenants:")
#         #     for t in all_tenants:
#         #         print(f"- {t.name} ({t.id})")

#         #     # deleted_tenant = await delete_tenant(db, new_tenant.id)
#         #     # print(f"Deleted tenant: {deleted_tenant.name if deleted_tenant else 'Failed to delete'}")
#         pass
#     finally:
#         await db.disconnect()

# if __name__ == "__main__":
#     import asyncio
#     import random
#     asyncio.run(main())
