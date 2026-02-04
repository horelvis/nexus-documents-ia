"""Pydantic schemas for the Prompt Management system.

Defines schemas for:
- Prompt Rules (dynamic injection based on context)
- Few-Shot Examples (Q&A with embeddings for similarity search)
- Guardrails (post-processing validation)
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════════════════════

class RuleActionType(str, Enum):
    """Actions that can be performed when a rule matches."""
    INJECT_BLOCK = "inject_block"      # Add content to prompt
    SKIP_BLOCK = "skip_block"          # Remove/skip a section
    MODIFY_CONTEXT = "modify_context"  # Modify template context variables
    SET_VARIABLE = "set_variable"      # Set a specific variable value


class GuardrailType(str, Enum):
    """Types of guardrails for output validation."""
    REGEX = "regex"                # Pattern matching
    KEYWORD = "keyword"            # Blocked/required word lists
    SEMANTIC = "semantic"          # Embedding-based topic detection
    LLM_VALIDATOR = "llm_validator"  # LLM-based content validation
    LENGTH = "length"              # Character/word count limits
    FORMAT = "format"              # Structural requirements


class GuardrailAction(str, Enum):
    """Actions when guardrail matches."""
    BLOCK = "block"    # Reject the response entirely
    WARN = "warn"      # Log warning but allow response
    REDACT = "redact"  # Remove matched content


class FewShotDomain(str, Enum):
    """Valid domains for few-shot examples."""
    LEGAL = "legal"
    MEDICAL = "medical"
    DOCUMENTAL = "documental"
    GENERAL = "general"


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT RULES
# ══════════════════════════════════════════════════════════════════════════════

class PromptRuleConditions(BaseModel):
    """Conditions for rule matching. All specified conditions must match (AND logic)."""
    document_type: Optional[str] = Field(None, description="Match specific document type")
    action: Optional[str] = Field(None, description="Match action intent (analyze, generate, retrieve)")
    sector: Optional[str] = Field(None, description="Match active sector (legal, medical, documental)")
    domain: Optional[str] = Field(None, description="Match detected domain (labor, fiscal, etc.)")
    has_docs: Optional[bool] = Field(None, description="Match based on retrieved documents presence")
    user_role: Optional[str] = Field(None, description="Match user role (admin, user)")
    locale: Optional[str] = Field(None, description="Match locale (es, en)")
    custom: Optional[Dict[str, Any]] = Field(None, description="Custom condition key-value pairs")


class PromptRuleActionConfig(BaseModel):
    """Configuration for rule action."""
    # For inject_block
    block_key: Optional[str] = Field(None, description="Key/name for the injected block")
    content: Optional[str] = Field(None, description="Content to inject (supports Jinja2)")
    position: Optional[str] = Field("prepend", description="Where to inject: prepend, append, replace")

    # For skip_block
    skip_key: Optional[str] = Field(None, description="Key of block to skip")

    # For modify_context / set_variable
    variable_name: Optional[str] = Field(None, description="Variable name to set/modify")
    variable_value: Optional[Any] = Field(None, description="Value to set")


class PromptRuleCreate(BaseModel):
    """Create a new prompt rule."""
    rule_name: str = Field(..., max_length=255, description="Human-readable rule name")
    description: Optional[str] = Field(None, description="Description of what this rule does")
    conditions: PromptRuleConditions = Field(..., description="Conditions to match")
    action_type: RuleActionType = Field(..., description="Action to perform when matched")
    action_config: PromptRuleActionConfig = Field(..., description="Action configuration")
    priority: int = Field(default=100, ge=1, le=1000, description="Rule priority (lower = higher)")
    is_active: bool = Field(default=True)

    @field_validator("conditions", mode="before")
    @classmethod
    def validate_conditions(cls, v):
        if isinstance(v, dict):
            return PromptRuleConditions(**v)
        return v


class PromptRuleUpdate(BaseModel):
    """Update an existing prompt rule."""
    rule_name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[PromptRuleConditions] = None
    action_type: Optional[RuleActionType] = None
    action_config: Optional[PromptRuleActionConfig] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    is_active: Optional[bool] = None


class PromptRuleResponse(BaseModel):
    """Prompt rule response."""
    id: UUID
    tenant_id: Optional[UUID] = None
    rule_name: str
    description: Optional[str] = None
    conditions: Dict[str, Any]
    action_type: RuleActionType
    action_config: Dict[str, Any]
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromptRuleListResponse(BaseModel):
    """List of prompt rules."""
    rules: List[PromptRuleResponse]
    total: int


class RuleEvaluationRequest(BaseModel):
    """Request to evaluate rules against a mock context."""
    document_type: Optional[str] = None
    action: Optional[str] = None
    sector: Optional[str] = None
    domain: Optional[str] = None
    has_docs: Optional[bool] = None
    user_role: Optional[str] = None
    locale: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class RuleEvaluationResult(BaseModel):
    """Result of rule evaluation."""
    matched_rules: List[PromptRuleResponse]
    actions_to_apply: List[Dict[str, Any]]
    context_modifications: Dict[str, Any]


# ══════════════════════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLES
# ══════════════════════════════════════════════════════════════════════════════

class FewShotExampleCreate(BaseModel):
    """Create a new few-shot example."""
    question: str = Field(..., min_length=10, description="Example question")
    answer: str = Field(..., min_length=10, description="Example answer")
    category: Optional[str] = Field(None, max_length=100, description="Category for grouping")
    domain: Optional[FewShotDomain] = Field(None, description="Applicable domain")
    tags: Optional[List[str]] = Field(None, description="Tags for filtering")
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Quality rating")


class FewShotExampleUpdate(BaseModel):
    """Update an existing few-shot example."""
    question: Optional[str] = Field(None, min_length=10)
    answer: Optional[str] = Field(None, min_length=10)
    category: Optional[str] = Field(None, max_length=100)
    domain: Optional[FewShotDomain] = None
    tags: Optional[List[str]] = None
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None


class FewShotExampleResponse(BaseModel):
    """Few-shot example response."""
    id: UUID
    tenant_id: Optional[UUID] = None
    question: str
    answer: str
    category: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[List[str]] = None
    quality_score: float
    usage_count: int
    positive_feedback: int
    negative_feedback: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # Similarity score when returned from search
    similarity_score: Optional[float] = None

    class Config:
        from_attributes = True


class FewShotExampleListResponse(BaseModel):
    """List of few-shot examples."""
    examples: List[FewShotExampleResponse]
    total: int


class FewShotSearchRequest(BaseModel):
    """Search for similar few-shot examples."""
    query: str = Field(..., min_length=3, description="Query to find similar examples")
    limit: int = Field(default=3, ge=1, le=10, description="Maximum examples to return")
    domain: Optional[FewShotDomain] = Field(None, description="Filter by domain")
    category: Optional[str] = Field(None, description="Filter by category")
    min_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)


class FewShotSearchResponse(BaseModel):
    """Search results for few-shot examples."""
    examples: List[FewShotExampleResponse]
    query: str
    search_time_ms: float


class FewShotFeedbackRequest(BaseModel):
    """Submit feedback for a few-shot example."""
    example_id: UUID
    is_positive: bool
    comment: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# GUARDRAILS
# ══════════════════════════════════════════════════════════════════════════════

class GuardrailConfig(BaseModel):
    """Configuration for guardrails based on type."""
    # For regex
    pattern: Optional[str] = Field(None, description="Regex pattern to match")
    flags: Optional[str] = Field(None, description="Regex flags (e.g., 'i' for case-insensitive)")

    # For keyword
    blocked_words: Optional[List[str]] = Field(None, description="Words that must not appear")
    required_words: Optional[List[str]] = Field(None, description="Words that must appear")

    # For semantic
    forbidden_topics: Optional[List[str]] = Field(None, description="Topics to block")
    required_topics: Optional[List[str]] = Field(None, description="Topics that must be covered")
    similarity_threshold: Optional[float] = Field(0.8, ge=0.0, le=1.0)

    # For llm_validator
    validation_prompt: Optional[str] = Field(None, description="Prompt for LLM validation")
    model: Optional[str] = Field(None, description="Model to use for validation")
    threshold: Optional[float] = Field(0.9, ge=0.0, le=1.0)

    # For length
    min_chars: Optional[int] = Field(None, ge=0)
    max_chars: Optional[int] = Field(None, ge=0)
    min_words: Optional[int] = Field(None, ge=0)
    max_words: Optional[int] = Field(None, ge=0)

    # For format
    must_contain_sources: Optional[bool] = Field(None, description="Must include source citations")
    require_spanish: Optional[bool] = Field(None, description="Response must be in Spanish")
    require_structure: Optional[List[str]] = Field(None, description="Required sections/headers")


class GuardrailCreate(BaseModel):
    """Create a new guardrail."""
    guardrail_name: str = Field(..., max_length=255)
    description: Optional[str] = None
    guardrail_type: GuardrailType
    config: GuardrailConfig
    action_on_match: GuardrailAction
    applies_to: Optional[List[str]] = Field(
        None,
        description="Agent/prompt names this applies to. Empty = all."
    )
    priority: int = Field(default=100, ge=1, le=1000)
    is_active: bool = True


class GuardrailUpdate(BaseModel):
    """Update an existing guardrail."""
    guardrail_name: Optional[str] = None
    description: Optional[str] = None
    guardrail_type: Optional[GuardrailType] = None
    config: Optional[GuardrailConfig] = None
    action_on_match: Optional[GuardrailAction] = None
    applies_to: Optional[List[str]] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    is_active: Optional[bool] = None


class GuardrailResponse(BaseModel):
    """Guardrail response."""
    id: UUID
    tenant_id: Optional[UUID] = None
    guardrail_name: str
    description: Optional[str] = None
    guardrail_type: GuardrailType
    config: Dict[str, Any]
    action_on_match: GuardrailAction
    applies_to: Optional[List[str]] = None
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GuardrailListResponse(BaseModel):
    """List of guardrails."""
    guardrails: List[GuardrailResponse]
    total: int


class GuardrailTestRequest(BaseModel):
    """Test a guardrail against sample input."""
    content: str = Field(..., min_length=1, description="Content to test")
    agent_name: Optional[str] = Field(None, description="Agent context for testing")


class GuardrailTestResult(BaseModel):
    """Result of guardrail testing."""
    guardrail_id: UUID
    guardrail_name: str
    matched: bool
    action: GuardrailAction
    details: Optional[str] = None
    matched_content: Optional[str] = None


class GuardrailTestResponse(BaseModel):
    """Response from guardrail testing."""
    results: List[GuardrailTestResult]
    overall_action: GuardrailAction
    would_block: bool
    processing_time_ms: float


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class CacheInvalidateRequest(BaseModel):
    """Request to invalidate prompt cache."""
    prompt_names: Optional[List[str]] = Field(
        None,
        description="Specific prompts to invalidate. Empty = all."
    )


class CacheInvalidateResponse(BaseModel):
    """Response from cache invalidation."""
    invalidated_count: int
    message: str


class PromptHealthResponse(BaseModel):
    """Health status of prompt management system."""
    langfuse_connected: bool
    langfuse_host: Optional[str] = None
    database_connected: bool
    use_langfuse_prompts: bool
    cached_prompt_count: int
    rules_count: int
    few_shot_count: int
    guardrails_count: int
    last_sync: Optional[datetime] = None


class LangfuseSyncRequest(BaseModel):
    """Request to sync prompts from Langfuse."""
    force: bool = Field(default=False, description="Force sync even if cache is fresh")


class LangfuseSyncResponse(BaseModel):
    """Response from Langfuse sync."""
    synced_prompts: List[str]
    sync_time_ms: float
    errors: Optional[List[str]] = None
