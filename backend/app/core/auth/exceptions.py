"""
Custom authentication exceptions with typed errors.

These exceptions provide specific error types for authentication failures,
allowing for better error handling and consistent responses.
"""
from typing import Optional


class AuthError(Exception):
    """Base authentication error."""

    def __init__(
        self,
        message: str,
        status_code: int = 401,
        error_code: str = "auth_error"
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class TokenMissingError(AuthError):
    """Raised when no token is provided."""

    def __init__(self, message: str = "Missing Authorization header"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="token_missing"
        )


class TokenExpiredError(AuthError):
    """Raised when the token has expired."""

    def __init__(self, message: str = "Token expired"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="token_expired"
        )


class TokenInvalidError(AuthError):
    """Raised when the token is malformed or invalid."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="token_invalid"
        )


class UserNotFoundError(AuthError):
    """Raised when user is not found in database."""

    def __init__(self, message: str = "User not registered. Please sign up first."):
        super().__init__(
            message=message,
            status_code=401,
            error_code="user_not_found"
        )


class UserInactiveError(AuthError):
    """Raised when user account is inactive."""

    def __init__(self, message: str = "User account is inactive"):
        super().__init__(
            message=message,
            status_code=400,
            error_code="user_inactive"
        )


class InsufficientPermissionsError(AuthError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="insufficient_permissions"
        )


class ClerkConfigError(AuthError):
    """Raised when Clerk is not properly configured."""

    def __init__(self, message: str = "Clerk not configured"):
        super().__init__(
            message=message,
            status_code=500,
            error_code="clerk_config_error"
        )
