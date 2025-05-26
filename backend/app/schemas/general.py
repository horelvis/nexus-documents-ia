from typing import Optional
from pydantic import BaseModel, Field

class ErrorDetail(BaseModel):
    loc: Optional[list[str]] = Field(None, title="Location", description="Location of the error in the request (e.g., body, path, query).")
    msg: str = Field(..., title="Message", description="A human-readable message providing specific information about the error.")
    type: Optional[str] = Field(None, title="Error Type", description="A short, machine-readable string indicating the error type.")

class ErrorResponse(BaseModel):
    detail: str | list[ErrorDetail] = Field(..., title="Error Detail", description="A human-readable message or a list of detailed error messages.")

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
