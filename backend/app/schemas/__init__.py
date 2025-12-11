# Auth (minimal - Clerk handles authentication)
from .auth import TokenPayload

# Billing - Solo Subscription schemas
from .billing import (
    SubscriptionBase, SubscriptionCreate, SubscriptionUpdate, Subscription
)

# Document
from .document import (
    DocumentBase, DocumentCreate, DocumentUpdate, Document, DocumentDetail, DocumentBasic, DocumentWithMetrics,
    DocumentMetricsBase, DocumentMetricsCreate, DocumentMetrics,
    DocumentTagBase, DocumentTagCreate, DocumentTag,
    DocumentViewBase, DocumentViewCreate, DocumentView,
    TagBase, TagCreate, TagUpdate, Tag,
    SearchQuery, SearchResult, SearchResultMatch, ChatMessage,
    SignedUrlResponse, UploadRequest
)

# Enums
from .enums import IndexingStatus, ErrorCode

# General
from .general import Message, ErrorResponse, SuccessResponse, PaginatedResponse, ErrorDetail

# RBAC
from .rbac import (
    PermissionBase, PermissionCreate, PermissionUpdate, Permission,
    RoleBase, RoleCreate, RoleUpdate, Role
)

# Tenant
from .tenant import (
    TenantBase, TenantCreate, TenantUpdate, TenantResponse, TenantWithUsers, Tenant, TenantSettings
)

# User (UserCreate removed - users created via Clerk JIT)
from .user import (
    UserBase, UserUpdate, User, UserRead, UserResponse,
    UserImageBase, UserImageCreate, UserImageUpdate, UserImage
)

# Analysis Queue (Emma AI)
from .analysis import (
    AnalysisStatus, AnalysisType,
    AnalysisQueueRequest, AnalysisBatchRequest,
    AnalysisStepInfo, AnalysisFinding, AnalysisAnnotation,
    AnalysisJobBase, AnalysisJobCreate, AnalysisJobProgress, AnalysisJobResult, AnalysisJobListItem,
    AnalysisQueueStats, AnalysisQueueResponse,
    AnalysisStreamEvent, AnalysisProgressEvent, AnalysisStepEvent, AnalysisFindingEvent, AnalysisCompletedEvent
)

# Information Channels
from .channel import (
    ChannelType, ChannelVisibility, ChannelSyncStatus, SyncTriggerType,
    GmailConfig, GoogleDriveConfig, DatabaseType, ExternalDBConfig,
    ChannelBase, ChannelCreate, ChannelUpdate, ChannelResponse, ChannelListResponse,
    GmailChannelCreate, GoogleDriveChannelCreate, ExternalDBChannelCreate,
    SyncLogResponse, SyncHistoryResponse,
    ChannelDocumentResponse, ChannelDocumentsResponse,
    OAuthUrlResponse, OAuthCallbackRequest,
    SyncTriggerRequest, SyncTriggerResponse,
    DBCredentialsCreate, TestConnectionResponse,
)

# Document ACL
from .document_acl import (
    GranteeType, ACLAction, ACLSource, Permission,
    PermissionSet,
    DocumentACLBase, DocumentACLCreate, DocumentACLUpdate, DocumentACLResponse, DocumentACLListResponse,
    GrantPermissionRequest, GrantPermissionBatchRequest, RevokePermissionRequest,
    EffectivePermissions, CheckPermissionRequest, CheckPermissionResponse,
    DocumentACLAuditBase, DocumentACLAuditResponse, DocumentACLAuditListResponse,
    BulkACLUpdateRequest, BulkACLUpdateResponse,
    ShareLinkRequest, ShareLinkResponse,
)

__all__ = [
    # Auth (minimal - Clerk handles authentication)
    "TokenPayload",
    
    # Billing - Solo Subscriptions
    "SubscriptionBase",
    "SubscriptionCreate",
    "SubscriptionUpdate",
    "Subscription",
    
    # Document
    "DocumentBase",
    "DocumentCreate",
    "DocumentUpdate",
    "Document",
    "DocumentDetail",
    "DocumentBasic",
    "DocumentWithMetrics",
    "DocumentMetricsBase",
    "DocumentMetricsCreate",
    "DocumentMetrics",
    "DocumentTagBase",
    "DocumentTagCreate",
    "DocumentTag",
    "DocumentViewBase",
    "DocumentViewCreate",
    "DocumentView",
    "TagBase",
    "TagCreate",
    "TagUpdate",
    "Tag",
    "SearchQuery",
    "SearchResult", 
    "SearchResultMatch",
    "ChatMessage",
    "SignedUrlResponse",
    "UploadRequest",
    
    # Enums
    "IndexingStatus",
    "ErrorCode",
    
    # General
    "Message",
    "ErrorResponse",
    "SuccessResponse",
    "PaginatedResponse",
    "ErrorDetail",
    
    # RBAC
    "PermissionBase",
    "PermissionCreate",
    "PermissionUpdate",
    "Permission",
    "RoleBase",
    "RoleCreate",
    "RoleUpdate",
    "Role",
    
    # Tenant
    "TenantBase",
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    "TenantWithUsers",
    "Tenant",
    "TenantSettings",
    
    # User
    "UserBase",
    "UserUpdate",
    "User",
    "UserRead",
    "UserResponse",
    "UserImageBase",
    "UserImageCreate",
    "UserImageUpdate",
    "UserImage",

    # Analysis Queue (Emma AI)
    "AnalysisStatus",
    "AnalysisType",
    "AnalysisQueueRequest",
    "AnalysisBatchRequest",
    "AnalysisStepInfo",
    "AnalysisFinding",
    "AnalysisAnnotation",
    "AnalysisJobBase",
    "AnalysisJobCreate",
    "AnalysisJobProgress",
    "AnalysisJobResult",
    "AnalysisJobListItem",
    "AnalysisQueueStats",
    "AnalysisQueueResponse",
    "AnalysisStreamEvent",
    "AnalysisProgressEvent",
    "AnalysisStepEvent",
    "AnalysisFindingEvent",
    "AnalysisCompletedEvent",

    # Information Channels
    "ChannelType",
    "ChannelVisibility",
    "ChannelSyncStatus",
    "SyncTriggerType",
    "GmailConfig",
    "GoogleDriveConfig",
    "DatabaseType",
    "ExternalDBConfig",
    "ChannelBase",
    "ChannelCreate",
    "ChannelUpdate",
    "ChannelResponse",
    "ChannelListResponse",
    "GmailChannelCreate",
    "GoogleDriveChannelCreate",
    "ExternalDBChannelCreate",
    "SyncLogResponse",
    "SyncHistoryResponse",
    "ChannelDocumentResponse",
    "ChannelDocumentsResponse",
    "OAuthUrlResponse",
    "OAuthCallbackRequest",
    "SyncTriggerRequest",
    "SyncTriggerResponse",
    "DBCredentialsCreate",
    "TestConnectionResponse",

    # Document ACL
    "GranteeType",
    "ACLAction",
    "ACLSource",
    "Permission",
    "PermissionSet",
    "DocumentACLBase",
    "DocumentACLCreate",
    "DocumentACLUpdate",
    "DocumentACLResponse",
    "DocumentACLListResponse",
    "GrantPermissionRequest",
    "GrantPermissionBatchRequest",
    "RevokePermissionRequest",
    "EffectivePermissions",
    "CheckPermissionRequest",
    "CheckPermissionResponse",
    "DocumentACLAuditBase",
    "DocumentACLAuditResponse",
    "DocumentACLAuditListResponse",
    "BulkACLUpdateRequest",
    "BulkACLUpdateResponse",
    "ShareLinkRequest",
    "ShareLinkResponse",
]