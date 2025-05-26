from typing import Optional, Dict, Any, List
from prisma import Prisma
from prisma.models import Subscription as PrismaSubscription
from prisma.errors import RecordNotFoundError
# Assuming Pydantic schemas exist for subscription creation/update if needed.
# For now, using Dict[str, Any].

async def get_subscription(db: Prisma, subscription_id: str) -> Optional[PrismaSubscription]:
    """
    Get a subscription by its ID.
    """
    try:
        subscription = await db.subscription.find_unique(where={"id": subscription_id})
        return subscription
    except Exception as e:
        print(f"Error fetching subscription by ID: {e}")
        return None

async def get_subscription_by_user_id(db: Prisma, user_id: str) -> Optional[PrismaSubscription]:
    """
    Get a subscription by user ID.
    Assumes a one-to-one relation where User has a subscriptionId field.
    Or, if Prisma schema defines `user User @relation(fields: [userId], references: [id])` on Subscription.
    The current schema has `user User` on Subscription and `subscription Subscription? @relation(fields: [subscriptionId], references: [id])` on User.
    So, we'd typically fetch the User and include the Subscription, or fetch Subscription by its own ID
    if known. If we want to fetch by user_id directly on the Subscription table, the schema would need
    a direct userId field on Subscription.
    
    For the current schema (`prisma/schema.prisma` dated 2024-07-08), the User model has `subscriptionId`.
    So, to get a subscription for a user, you'd typically query the user and include their subscription,
    or if you have the subscriptionId, query it directly.
    
    This function demonstrates finding a subscription if it *had* a direct `userId` field.
    Alternatively, to fit the current schema, this function might be better named
    `get_user_with_subscription(db: Prisma, user_id: str)` and live in `users.py`.
    Or, if you have `subscriptionId` from the user object: `get_subscription(db, user.subscriptionId)`.

    Let's assume for this example, you want to find a subscription directly linked via a `userId` on the subscription table,
    which is NOT the current schema setup but common. If this is not intended, this function needs adjustment.
    For the current schema, you'd likely use:
    user_with_sub = await db.user.find_unique(where={"id": user_id}, include={"subscription": True})
    return user_with_sub.subscription if user_with_sub else None
    
    Given the current schema, a direct query on Subscription by `userId` isn't standard unless `userId` is a field on `Subscription`.
    Let's provide a placeholder that would work if `userId` was a direct, indexed field on `Subscription`.
    """
    # This is a placeholder. The actual implementation depends on how you want to query.
    # If Subscription has a `userId` field:
    # subscriptions = await db.subscription.find_many(where={"userId": user_id})
    # return subscriptions[0] if subscriptions else None
    # For now, returning None as it requires schema modification or a different approach.
    print(f"Note: Querying Subscription directly by user_id ('{user_id}') is not standard with current schema. Consider fetching User and including Subscription.")
    return None


async def create_subscription(db: Prisma, subscription_data: Dict[str, Any]) -> PrismaSubscription:
    """
    Create a new subscription.
    subscription_data should conform to Prisma's SubscriptionCreateInput,
    e.g., {"planId": "pro", "status": "active", "userId": "user_id_value_if_direct_link"}
    or if linked via User: {"planId": "pro", "status": "active", "user": {"connect": {"id": "user_id_value"}}}
    The current schema implies the latter or managing `subscriptionId` on `User`.
    """
    if not all(k in subscription_data for k in ["planId", "status"]): # Add "userId" if it's a direct link
        raise ValueError("planId and status are required to create a subscription.")
        
    try:
        # Example: data={"planId": "pro", "status": "active", "user": {"connect": {"id": "some_user_id"}}}
        subscription = await db.subscription.create(data=subscription_data)
        return subscription
    except Exception as e:
        print(f"Error creating subscription: {e}")
        raise

async def update_subscription(db: Prisma, subscription_id: str, subscription_data: Dict[str, Any]) -> Optional[PrismaSubscription]:
    """
    Update an existing subscription.
    subscription_data should conform to Prisma's SubscriptionUpdateInput.
    """
    try:
        subscription = await db.subscription.update(where={"id": subscription_id}, data=subscription_data)
        return subscription
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error updating subscription: {e}")
        raise

async def delete_subscription(db: Prisma, subscription_id: str) -> Optional[PrismaSubscription]:
    """
    Delete a subscription by its ID.
    """
    try:
        subscription = await db.subscription.delete(where={"id": subscription_id})
        return subscription
    except RecordNotFoundError:
        return None
    except Exception as e:
        print(f"Error deleting subscription: {e}")
        raise

# Example usage (for testing purposes, remove in production)
# async def main():
#     db = Prisma()
#     await db.connect()
#     try:
#         # First, ensure a user exists to link the subscription to.
#         # This assumes you have a user repository and a way to create/get a user.
#         # Example: user = await user_repo.get_user_by_email(db, "test@example.com")
#         # if not user:
#         #     print("User not found, cannot create subscription.")
#         #     return
#
#         # sub_to_create = {
#         #     "planId": "premium",
#         #     "status": "active",
#         #     "user": { "connect": { "id": user.id } } # Link to existing user
#         # }
#         # new_sub = await create_subscription(db, sub_to_create)
#         # print(f"Created subscription: {new_sub.id if new_sub else 'Failed'}")
#
#         # if new_sub:
#         #     fetched_sub = await get_subscription(db, new_sub.id)
#         #     print(f"Fetched subscription: Plan {fetched_sub.planId}, Status {fetched_sub.status if fetched_sub else 'Not found'}")
#
#         #     updated_sub = await update_subscription(db, new_sub.id, {"status": "past_due"})
#         #     print(f"Updated subscription status: {updated_sub.status if updated_sub else 'Failed to update'}")
#
#         #     # deleted_sub = await delete_subscription(db, new_sub.id)
#         #     # print(f"Deleted subscription: {deleted_sub.id if deleted_sub else 'Failed to delete'}")
#         pass
#     finally:
#         await db.disconnect()

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
