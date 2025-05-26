from fastapi import APIRouter, Depends, HTTPException, status
from prisma import Prisma

from app.api.dependencies import get_prisma_db, verify_api_key
from app.schemas.user import UserRead
from app.db.repositories import users as user_repo
from app.services.auth_service import AuthService # For get_current_user, if adapted

router = APIRouter()

# Note: The `get_current_user` from AuthService was refactored to take `db: Prisma` and `token: str`.
# For a `/users/me` endpoint that relies on a JWT, we'd need a new dependency 
# that extracts the token, validates it, and then uses AuthService.get_current_user.
# Since this task focuses on API Key auth for now, and Clerk will handle JWT later,
# the `/users/me` endpoint here will be simplified.
# It could, for instance, return a default user or a user associated with the API key
from app.schemas.general import ErrorResponse # Import the general error response schema

# if such a link existed. For now, it will just demonstrate API key protection
# and return a specific user or error if no clear "me" from API key.

@router.get(
    "/me", 
    response_model=UserRead, 
    dependencies=[Depends(verify_api_key)],
    summary="Get current user (placeholder)",
    description=(
        "Retrieves a placeholder user. This endpoint demonstrates API key protection. "
        "In a full JWT-based auth system (like with Clerk), this would return the "
        "currently authenticated user based on their token."
    ),
    responses={
        403: {"model": ErrorResponse, "description": "Not authenticated or Invalid API Key"},
        404: {"model": ErrorResponse, "description": "Default user for /me not found"}
    }
)
async def read_users_me(
    db: Prisma = Depends(get_prisma_db)
):
    # Placeholder logic: returns the first user found.
    # Replace with actual logic when JWT/Clerk auth is integrated.
    first_user = await db.user.find_first()
    if not first_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Default user for /me not found.")
    return UserRead.from_orm(first_user)


@router.get(
    "/{user_id}", 
    response_model=UserRead, 
    dependencies=[Depends(verify_api_key)],
    summary="Get user by ID",
    description="Retrieves a specific user by their unique ID. Requires API key authentication.",
    responses={
        200: {"description": "User data"},
        403: {"model": ErrorResponse, "description": "Not authenticated or Invalid API Key"},
        404: {"model": ErrorResponse, "description": "User not found"}
    }
)
async def read_user_by_id(
    user_id: str, 
    db: Prisma = Depends(get_prisma_db)
):
    user = await user_repo.get_user(db=db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.from_orm(user)
