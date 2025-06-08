from typing import Optional, List
from datetime import datetime
import uuid
from pydantic import BaseModel, Field

# --- Plan Schemas ---
class PlanBase(BaseModel):
    name: str = Field(..., example="Premium Plan")
    description: Optional[str] = Field(None, example="Full access to all features.")

class PlanCreate(PlanBase):
    pass

class PlanUpdate(PlanBase):
    pass

class Plan(PlanBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())
    # prices: List['Price'] = [] # If you want to show prices related to the plan

    class Config:
        from_attributes = True

# --- Price Schemas ---
class PriceBase(BaseModel):
    amount: int = Field(..., example=2999, description="Amount in cents") # e.g., 2999 for $29.99
    currency: str = Field(..., example="usd")
    interval: str = Field(..., example="month", description="e.g., 'month', 'year'")
    plan_id: uuid.UUID = Field(..., example=uuid.uuid4())

class PriceCreate(PriceBase):
    pass

class PriceUpdate(PriceBase):
    pass

class Price(PriceBase):
    id: uuid.UUID = Field(..., example=uuid.uuid4())
    plan: Optional[Plan] = None # Relation to Plan
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True

# --- Subscription Schemas ---
class SubscriptionBase(BaseModel):
    status: str = Field(..., example="active") # e.g., 'active', 'canceled', 'past_due'
    current_period_start: datetime = Field(..., example=datetime.now())
    current_period_end: datetime = Field(..., example=datetime.now())
    cancel_at_period_end: bool = Field(False, example=False)
    plan_id: Optional[uuid.UUID] = Field(None, example=uuid.uuid4())
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
    plan: Optional[Plan] = None # Relation to Plan (legacy)
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())

    class Config:
        from_attributes = True

# Update forward references
# This is crucial if models refer to each other and are defined in the same file or need to resolve circular dependencies.
Plan.update_forward_refs()
Price.update_forward_refs()
Subscription.update_forward_refs()
