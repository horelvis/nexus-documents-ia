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

# RBAC and Tenant schemas removed — replaced by role-based ACL (see app.core.auth.acl)

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

# Document ACL schemas removed — replaced by role-based ACL (see app.core.auth.acl)

# Site Guest (External Sharing)
from .site_guest import (
    SiteGuestBase, SiteGuestCreate, SiteGuestUpdate, SiteGuestResponse, SiteGuestListResponse,
    SiteGuestInviteRequest,
    OTPRequestPayload, OTPRequestResponse, OTPVerifyPayload, OTPVerifyResponse,
    SiteGuestSessionResponse, SiteGuestSessionListResponse,
    SiteGuestPermissionBase, SiteGuestDocumentPermissionCreate, SiteGuestFolderPermissionCreate,
    SiteGuestPermissionResponse, SiteGuestPermissionListResponse,
    SiteGuestAccessLogResponse, SiteGuestAccessLogListResponse,
    PortalDocumentInfo, PortalFolderInfo, PortalContentResponse, GuestMeResponse,
    TenantSiteInfo, TenantSiteSettingsUpdate, TenantSiteSettingsResponse,
    SiteGuestStatistics,
)

# NexusLM Notebooks
from .notebook import (
    AudioTone, AudioLength, AudioStatus,
    NotebookSettings, NotebookBase, NotebookCreate, NotebookUpdate, NotebookResponse, NotebookListResponse,
    KeyPoint, NotebookSourceBase, NotebookSourceAdd, NotebookSourceResponse,
    VoiceConfig, AudioConfig, AudioGenerateRequest, ScriptSegment, TranscriptSegment,
    NotebookAudioResponse, AudioStatusResponse,
    Citation, ChatMessage as NotebookChatMessage, NotebookChatCreate, NotebookChatMessage as NotebookChatMessageRequest,
    NotebookChatResponse, ChatCompletionResponse,
    NotebookDetailResponse, NotebookStatsResponse,
)

# Data Learning System
from .data_learning import (
    # Enums
    DiscoveryMethod, LevelSemanticType, RelationshipCategory, ChunkingType,
    DataLearningJobType, DataLearningJobStatus, JobTriggerType,
    # Content Model
    ContentTypeDefinition, AspectDefinition, PropertyDefinition,
    TypeSemantic, PropertySemantic, ConnectorContentModelResponse, ContentModelSummary,
    # Folder Patterns
    LevelSemantic, LearnedFolderPatternCreate, LearnedFolderPatternUpdate,
    LearnedFolderPatternResponse, FolderContext,
    # Property Mappings
    LearnedPropertyMappingCreate, LearnedPropertyMappingUpdate, LearnedPropertyMappingResponse,
    # Relationship Types
    LearnedRelationshipTypeCreate, LearnedRelationshipTypeUpdate, LearnedRelationshipTypeResponse,
    # Indexing Strategies
    ChunkingConfig, ConnectorIndexingStrategyCreate, ConnectorIndexingStrategyUpdate,
    ConnectorIndexingStrategyResponse,
    # Learning Jobs
    DataLearningJobCreate, DataLearningJobResponse, DataLearningJobListResponse,
    # Learned Context
    LearnedContext, TOONLearnedContext,
    # API Schemas
    TriggerLearningRequest, TriggerLearningResponse, ConnectorLearningStatusResponse,
    BulkPropertyMappingUpdate, ApplyFolderContextRequest,
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

    # Site Guest (External Sharing)
    "SiteGuestBase",
    "SiteGuestCreate",
    "SiteGuestUpdate",
    "SiteGuestResponse",
    "SiteGuestListResponse",
    "SiteGuestInviteRequest",
    "OTPRequestPayload",
    "OTPRequestResponse",
    "OTPVerifyPayload",
    "OTPVerifyResponse",
    "SiteGuestSessionResponse",
    "SiteGuestSessionListResponse",
    "SiteGuestPermissionBase",
    "SiteGuestDocumentPermissionCreate",
    "SiteGuestFolderPermissionCreate",
    "SiteGuestPermissionResponse",
    "SiteGuestPermissionListResponse",
    "SiteGuestAccessLogResponse",
    "SiteGuestAccessLogListResponse",
    "PortalDocumentInfo",
    "PortalFolderInfo",
    "PortalContentResponse",
    "GuestMeResponse",
    "TenantSiteInfo",
    "TenantSiteSettingsUpdate",
    "TenantSiteSettingsResponse",
    "SiteGuestStatistics",

    # NexusLM Notebooks
    "AudioTone",
    "AudioLength",
    "AudioStatus",
    "NotebookSettings",
    "NotebookBase",
    "NotebookCreate",
    "NotebookUpdate",
    "NotebookResponse",
    "NotebookListResponse",
    "KeyPoint",
    "NotebookSourceBase",
    "NotebookSourceAdd",
    "NotebookSourceResponse",
    "VoiceConfig",
    "AudioConfig",
    "AudioGenerateRequest",
    "ScriptSegment",
    "TranscriptSegment",
    "NotebookAudioResponse",
    "AudioStatusResponse",
    "Citation",
    "NotebookChatMessage",
    "NotebookChatCreate",
    "NotebookChatMessageRequest",
    "NotebookChatResponse",
    "ChatCompletionResponse",
    "NotebookDetailResponse",
    "NotebookStatsResponse",

    # Data Learning System - Enums
    "DiscoveryMethod",
    "LevelSemanticType",
    "RelationshipCategory",
    "ChunkingType",
    "DataLearningJobType",
    "DataLearningJobStatus",
    "JobTriggerType",
    # Data Learning System - Content Model
    "ContentTypeDefinition",
    "AspectDefinition",
    "PropertyDefinition",
    "TypeSemantic",
    "PropertySemantic",
    "ConnectorContentModelResponse",
    "ContentModelSummary",
    # Data Learning System - Folder Patterns
    "LevelSemantic",
    "LearnedFolderPatternCreate",
    "LearnedFolderPatternUpdate",
    "LearnedFolderPatternResponse",
    "FolderContext",
    # Data Learning System - Property Mappings
    "LearnedPropertyMappingCreate",
    "LearnedPropertyMappingUpdate",
    "LearnedPropertyMappingResponse",
    # Data Learning System - Relationship Types
    "LearnedRelationshipTypeCreate",
    "LearnedRelationshipTypeUpdate",
    "LearnedRelationshipTypeResponse",
    # Data Learning System - Indexing Strategies
    "ChunkingConfig",
    "ConnectorIndexingStrategyCreate",
    "ConnectorIndexingStrategyUpdate",
    "ConnectorIndexingStrategyResponse",
    # Data Learning System - Learning Jobs
    "DataLearningJobCreate",
    "DataLearningJobResponse",
    "DataLearningJobListResponse",
    # Data Learning System - Learned Context
    "LearnedContext",
    "TOONLearnedContext",
    # Data Learning System - API
    "TriggerLearningRequest",
    "TriggerLearningResponse",
    "ConnectorLearningStatusResponse",
    "BulkPropertyMappingUpdate",
    "ApplyFolderContextRequest",
]