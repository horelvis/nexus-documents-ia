from fastapi import APIRouter, Depends, HTTPException, status
from prisma import Prisma

from app.api.dependencies import get_prisma_db # verify_api_key can be added if needed for specific auth endpoints
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreateInput, UserRead
from app.services.auth_service import AuthService
# Assuming user_repo is needed for direct user fetching if not done by AuthService
# from app.db.repositories import users as user_repo 
from app.schemas.general import ErrorResponse # Assuming a general error response schema

router = APIRouter()

@router.post(
    "/login", 
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticates a user and returns an access token along with user information.",
    responses={
        401: {"model": ErrorResponse, "description": "Incorrect email or password"},
        400: {"model": ErrorResponse, "description": "Invalid request data (e.g., malformed email)"}
    }
)
async def login_for_access_token(
    form_data: LoginRequest, # Changed to expect JSON body by default for FastAPI
    db: Prisma = Depends(get_prisma_db)
):
    # Note: If form_data is expected (application/x-www-form-urlencoded), 
    # then LoginRequest should inherit from a base class or be used with Depends(LoginRequest.as_form)
    # For this example, assuming JSON body as it's common for modern APIs.
    # If using form_data: LoginRequest = Depends() is for when LoginRequest fields are parameters of the endpoint.
    # If LoginRequest is a Pydantic model for the request body, just `form_data: LoginRequest` is fine for JSON.
    
    user = await AuthService.authenticate_user(
        db=db, email=form_data.email, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Ensure user.id and user.tenantId are strings for the token
    user_id_str = str(user.id)
    tenant_id_str = str(user.tenantId)

    access_token = AuthService.create_access_token(
        subject=user_id_str, tenant_id=tenant_id_str
    )
    
    user_read_data = UserRead.from_orm(user) # Ensure UserRead can handle Prisma model
    return TokenResponse(access_token=access_token, token_type="bearer", user=user_read_data)

@router.post(
    "/register", 
    response_model=UserRead, 
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new user in the system. Requires a valid `tenantId`. "
        "If `clerkUserId` is provided, it will be associated with the user."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input, email already registered, or tenant not found"},
        500: {"model": ErrorResponse, "description": "An unexpected error occurred"}
    }
)
async def register_user(
    user_in: UserCreateInput, 
    db: Prisma = Depends(get_prisma_db)
):
    try:
        created_user = await AuthService.create_user(
            db=db,
            email=user_in.email,
            password=user_in.password,
            full_name=user_in.fullName,
            tenant_id=user_in.tenantId,
            is_superuser=user_in.isSuperuser,
            clerk_user_id=user_in.clerkUserId
        )
    except HTTPException as e:
        raise e # Re-raise known HTTP exceptions from AuthService
    except ValueError as e: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Log the exception here for server-side details
        # logger.error(f"Unexpected error during user registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during user registration."
        )

    return UserRead.from_orm(created_user) # Ensure UserRead can handle Prisma model
