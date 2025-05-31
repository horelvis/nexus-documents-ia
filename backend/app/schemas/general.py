from typing import Optional, Any, List, Generic, TypeVar
from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    loc: Optional[List[str]] = Field(None, title="Location", description="Location of the error in the request (e.g., body, path, query).")
    msg: str = Field(..., title="Message", description="A human-readable message providing specific information about the error.")
    type: Optional[str] = Field(None, title="Error Type", description="A short, machine-readable string indicating the error type.")

class ErrorResponse(BaseModel):
    detail: str | List[ErrorDetail] = Field(..., title="Error Detail", description="A human-readable message or a list of detailed error messages.")

    class Config:
        schema_extra = {
            "example_single": {
                "detail": "Incorrect email or password"
            },
            "example_multiple": {
                "detail": [
                    {
                        "loc": ["body", "email"],
                        "msg": "value is not a valid email address",
                        "type": "value_error.email"
                    },
                    {
                        "loc": ["body", "password"],
                        "msg": "ensure this value has at least 8 characters",
                        "type": "value_error.any_str.min_length"
                    }
                ]
            }
        }

class Message(BaseModel):
    message: str = Field(..., example="Operation completed successfully")

class SuccessResponse(BaseModel):
    success: bool = Field(True, example=True)
    message: str = Field(..., example="Operation completed successfully")
    data: Optional[Any] = Field(None, example={})

# Generic type for paginated responses
T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T] = Field(..., description="List of items for current page")
    total: int = Field(..., description="Total number of items", example=100)
    page: int = Field(..., description="Current page number", example=1)
    per_page: int = Field(..., description="Items per page", example=10)
    pages: int = Field(..., description="Total number of pages", example=10)
    
    class Config:
        arbitrary_types_allowed = True