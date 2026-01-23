"""
Centralized enumerations for validation and type safety.

This module contains all enums used across schemas and services,
providing a single source of truth for valid values.

Usage:
    from app.core.enums import SignerRole, AuthMethod, UserRole

    # In Pydantic schemas
    role: SignerRole = Field(default=SignerRole.SIGNER)

    # For validation
    if role in SignerRole:
        print("Valid role")
"""

from enum import Enum, unique


# =============================================================================
# User & Team Roles
# =============================================================================

@unique
class UserRole(str, Enum):
    """User roles within the system."""
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"

    @classmethod
    def default(cls) -> "UserRole":
        return cls.USER


@unique
class TeamRole(str, Enum):
    """Roles within a team/organization."""
    ADMIN = "admin"
    MEMBER = "member"

    @classmethod
    def default(cls) -> "TeamRole":
        return cls.MEMBER


# =============================================================================
# Digital Signature Enums
# =============================================================================

@unique
class SignerRole(str, Enum):
    """Roles for document signers."""
    SIGNER = "signer"
    VIEWER = "viewer"
    APPROVER = "approver"

    @classmethod
    def default(cls) -> "SignerRole":
        return cls.SIGNER


@unique
class AuthenticationMethod(str, Enum):
    """Authentication methods for signature verification."""
    EMAIL = "email"
    SMS = "sms"
    CODE = "code"

    @classmethod
    def default(cls) -> "AuthenticationMethod":
        return cls.EMAIL


@unique
class SignatureStatus(str, Enum):
    """Status of a signature request."""
    PENDING = "pending"
    SENT = "sent"
    VIEWED = "viewed"
    SIGNED = "signed"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# =============================================================================
# Language & Localization
# =============================================================================

@unique
class SupportedLanguage(str, Enum):
    """Languages supported by the system."""
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    DUTCH = "nl"

    @classmethod
    def default(cls) -> "SupportedLanguage":
        return cls.SPANISH  # Default for this project


# =============================================================================
# Permission Enums
# =============================================================================

@unique
class PermissionType(str, Enum):
    """Types of permissions for documents/folders."""
    VIEW = "view"
    DOWNLOAD = "download"
    UPLOAD = "upload"
    EDIT = "edit"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"


@unique
class AccessLevel(str, Enum):
    """Access levels for resources."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    FULL = "full"


# =============================================================================
# Document Enums
# =============================================================================

@unique
class DocumentStatus(str, Enum):
    """Status of a document in the system."""
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    ARCHIVED = "archived"
    DELETED = "deleted"
    ERROR = "error"


@unique
class DocumentType(str, Enum):
    """Types of documents recognized by the system."""
    CONTRACT = "contract"
    INVOICE = "invoice"
    REPORT = "report"
    MEMO = "memo"
    POLICY = "policy"
    PROCEDURE = "procedure"
    LETTER = "letter"
    FORM = "form"
    PRESENTATION = "presentation"
    SPREADSHEET = "spreadsheet"
    OTHER = "other"


# =============================================================================
# Subscription & Billing Enums
# =============================================================================

@unique
class SubscriptionPlan(str, Enum):
    """Available subscription plans."""
    TRIAL = "trial"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@unique
class SubscriptionStatus(str, Enum):
    """Status of a subscription."""
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    UNPAID = "unpaid"


# =============================================================================
# Connector & Integration Enums
# =============================================================================

@unique
class ConnectorType(str, Enum):
    """Types of external connectors."""
    ALFRESCO = "alfresco"
    GOOGLE_DRIVE = "google_drive"
    SHAREPOINT = "sharepoint"
    DROPBOX = "dropbox"
    S3 = "s3"
    FTP = "ftp"
    SFTP = "sftp"


@unique
class ChannelType(str, Enum):
    """Types of information channels."""
    EMAIL = "email"
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    SLACK = "slack"
    TEAMS = "teams"
    WEBHOOK = "webhook"


# =============================================================================
# AI/LLM Enums
# =============================================================================

@unique
class LLMProvider(str, Enum):
    """Supported LLM providers."""
    VLLM = "vllm"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


@unique
class AgentType(str, Enum):
    """Types of AI agents in the system."""
    SEARCH = "search"
    ANALYST = "analyst"
    CONTRACT = "contract"
    COMPLIANCE = "compliance"
    SUMMARIZER = "summarizer"
    ROUTER = "router"


# =============================================================================
# Utility Functions
# =============================================================================

def get_enum_values(enum_class: type) -> list:
    """Get all values from an enum class."""
    return [e.value for e in enum_class]


def is_valid_enum_value(enum_class: type, value: str) -> bool:
    """Check if a value is valid for an enum class."""
    return value in get_enum_values(enum_class)


def get_enum_choices(enum_class: type) -> str:
    """Get a formatted string of enum choices for error messages."""
    values = get_enum_values(enum_class)
    return ", ".join(f"'{v}'" for v in values)
