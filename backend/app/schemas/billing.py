from typing import Optional
from datetime import datetime
import uuid
from pydantic import BaseModel, Field

# --- Subscription Schemas ---
class SubscriptionBase(BaseModel):
    status: str = Field(..., example="active") # e.g., 'active', 'canceled', 'past_due'
    current_period_start: datetime = Field(..., example=datetime.now())
    current_period_end: datetime = Field(..., example=datetime.now())
    cancel_at_period_end: bool = Field(False, example=False)
    stripe_plan_id: Optional[str] = Field(None, example="pro")
    interval: str = Field("month", example="month")

class SubscriptionCreate(SubscriptionBase):
    user_id: uuid.UUID = Field(..., example=uuid.uuid4())

class SubscriptionUpdate(SubscriptionBase):
    pass # Typically status changes or cancel_at_period_end

class Subscription(SubscriptionBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    user_id: uuid.UUID = Field(..., example=uuid.uuid4())
    stripe_customer_id: Optional[str] = Field(None, example="cus_1234567890")
    stripe_subscription_id: Optional[str] = Field(None, example="sub_1234567890")
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True
