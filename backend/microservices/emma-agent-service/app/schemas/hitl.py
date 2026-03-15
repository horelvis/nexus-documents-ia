"""
Pydantic schemas for Human-in-the-Loop (HITL) protocol.

Defines the interrupt values emitted by LangGraph interrupt() calls
and the decision values sent back via Command(resume=value).

Three interrupt types:
- hitl_review: Action requires user approval (approve/edit/reject)
- clarification: Agent needs more information from user
- confirmation: Simple yes/no confirmation

Frontend dispatches SSE events by the `type` field to render
the appropriate UI component (HITLReviewCard, ClarificationCard, etc.).
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional, Union


# =============================================================================
# Interrupt values (graph → frontend)
# =============================================================================

class ActionRequest(BaseModel):
    """Describes the action the agent wants to perform."""
    name: str = Field(..., description="Tool/action name (e.g. 'send_email')")
    args: Dict[str, Any] = Field(default_factory=dict, description="Action arguments")
    description: str = Field("", description="Human-readable description of the action")


class ReviewConfig(BaseModel):
    """Configuration for the review UI."""
    allowed_decisions: List[str] = Field(
        default=["approve", "reject"],
        description="Decision types the user can make",
    )
    editable_fields: List[str] = Field(
        default_factory=list,
        description="Fields the user can edit before approving",
    )


class HITLReviewRequest(BaseModel):
    """Interrupt value for actions requiring user review (approve/edit/reject)."""
    type: Literal["hitl_review"] = "hitl_review"
    action_request: ActionRequest
    review_config: ReviewConfig = Field(default_factory=ReviewConfig)


class ClarificationRequest(BaseModel):
    """Interrupt value when the agent needs more information."""
    type: Literal["clarification"] = "clarification"
    question: str = Field(..., description="Question to ask the user")
    options: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional structured options for the user",
    )


class ConfirmationRequest(BaseModel):
    """Interrupt value for simple yes/no confirmations."""
    type: Literal["confirmation"] = "confirmation"
    question: str = Field(..., description="What to confirm")
    options: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Confirmation options (e.g. confirm/cancel)",
    )


# Union of all interrupt value types
InterruptValue = Union[HITLReviewRequest, ClarificationRequest, ConfirmationRequest]


# =============================================================================
# Decision values (frontend → graph via Command(resume=value))
# =============================================================================

class ApproveDecision(BaseModel):
    """User approves the action as-is."""
    type: Literal["approve"] = "approve"
    message: str = Field("", description="Optional approval message")


class EditDecision(BaseModel):
    """User approves with modifications."""
    type: Literal["edit"] = "edit"
    edited_args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Modified action arguments",
    )
    message: str = Field("", description="Optional edit rationale")


class RejectDecision(BaseModel):
    """User rejects the action."""
    type: Literal["reject"] = "reject"
    message: str = Field("", description="Optional rejection reason")


# Union of all decision types
HITLDecision = Union[ApproveDecision, EditDecision, RejectDecision]
