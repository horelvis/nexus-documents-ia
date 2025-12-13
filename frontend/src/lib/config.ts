const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""

export const API_CONFIG = {
  BASE_URL: baseUrl,
  API_V1: '/api/v1',
  TIMEOUT: 30000, // 30 seconds (default)
  EMMA_TIMEOUT: 180000, // 3 minutes for Emma AI (PlanningFlow with multiple agents)
  
  // Microservice URLs (different ports)
  WEAVIATE_SERVICE_URL: process.env.NEXT_PUBLIC_WEAVIATE_SERVICE_URL || 'http://192.168.1.58:8007',
  
  // Endpoints
  ENDPOINTS: {
    // Auth
    LOGIN: '/auth/login/access-token',
    REGISTER: '/auth/register',
    ME: '/auth/me',
    
    // Documents
    DOCUMENTS: '/documents',
    DOCUMENT_SUMMARY: (id: string) => `/documents/${id}/summary`,
    DOCUMENT_STREAM: (id: string) => `/documents/${id}/stream`,
    DOCUMENT_CONTENT: (id: string) => `/documents/${id}/content`,
    
    // Search
    SEARCH: '/search',
    SEARCH_ASK: '/search/ask',
    
    // Admin
    ADMIN_USERS: '/admin/users',
    ADMIN_STATS: '/admin/stats',
    ADMIN: '/admin',
    
    // Tenants
    TENANTS: '/tenants',
    TENANTS_CURRENT: '/tenants/current',
    
    // Chat
    CHAT: '/chat',
    
    // Agents
    AGENTS: '/agents',
    
    // Digital Signatures
    SIGNATURES: '/signatures',
    
    // Dashboard
    DASHBOARD: '/dashboard',
    
    // Assistant (Legacy)
    ASSISTANT_CHAT: '/assistant/chat',
    ASSISTANT_CHAT_STREAM: '/assistant/chat/stream',
    ASSISTANT_CONVERSATION: (id: string) => `/assistant/conversation/${id}`,
    ASSISTANT_WELCOME: '/assistant/welcome',
    
    // Emma AI (AutoGen Multi-Agent)
    EMMA_QUERY: '/weaviate/emma/query',
    EMMA_TOOLS: '/weaviate/emma/tools',
    EMMA_HEALTH: '/weaviate/emma/health',
    EMMA_FEEDBACK: '/weaviate/emma/feedback',

    // Folders (Document Organization)
    FOLDERS: '/folders',
    FOLDERS_TREE: '/folders/tree',
    FOLDERS_STATS: '/folders/stats',
    FOLDER_DOCUMENTS: (path: string) => `/folders/${encodeURIComponent(path)}/documents`,
    FOLDER_MOVE: (documentId: string) => `/folders/${documentId}/move`,
    FOLDERS_BULK_MOVE: '/folders/bulk-move',

    // Classification (RAG + LLM Auto-Classification)
    CLASSIFICATION_STATUS: '/classification/status',
    CLASSIFICATION_SETTINGS: '/classification/settings',
    CLASSIFICATION_ACTIVATE: '/classification/activate',
    CLASSIFICATION_DEACTIVATE: '/classification/deactivate',
    CLASSIFICATION_PREVIEW: '/classification/preview',
    CLASSIFICATION_CLASSIFY: (documentId: string) => `/classification/classify/${documentId}`,

    // TTS (Text-to-Speech)
    TTS_SYNTHESIZE: '/tts/synthesize',
    TTS_VOICES: '/tts/voices',
    TTS_HEALTH: '/tts/health',
    TTS_WEBSOCKET_INFO: '/tts/websocket-info',

    // Site Guests (External Sharing)
    SITE_GUESTS: '/site-guests',
    SITE_GUESTS_SETTINGS: '/site-guests/site/settings',
    SITE_GUESTS_STATISTICS: '/site-guests/site/statistics',
    SITE_GUEST_BY_ID: (guestId: string) => `/site-guests/${guestId}`,
    SITE_GUEST_INVITE: (guestId: string) => `/site-guests/${guestId}/invite`,
    SITE_GUEST_PERMISSIONS: (guestId: string) => `/site-guests/${guestId}/permissions`,
    SITE_GUEST_PERMISSION_DOCUMENT: (guestId: string) => `/site-guests/${guestId}/permissions/document`,
    SITE_GUEST_PERMISSION_FOLDER: (guestId: string) => `/site-guests/${guestId}/permissions/folder`,
    SITE_GUEST_REVOKE_PERMISSION: (guestId: string, permissionId: string) => `/site-guests/${guestId}/permissions/${permissionId}`,
    SITE_GUEST_ACCESS_LOGS: (guestId: string) => `/site-guests/${guestId}/access-logs`,

    // Site Portal (Public Guest Access)
    SITE_PORTAL_TENANT: (slug: string) => `/site-portal/t/${slug}`,
    SITE_PORTAL_REQUEST_OTP: (slug: string) => `/site-portal/t/${slug}/request-otp`,
    SITE_PORTAL_VERIFY_OTP: (slug: string) => `/site-portal/t/${slug}/verify-otp`,
    SITE_PORTAL_LOGOUT: '/site-portal/logout',
    SITE_PORTAL_ME: '/site-portal/me',
    SITE_PORTAL_CONTENT: '/site-portal/content',
    SITE_PORTAL_DOCUMENT: (documentId: string) => `/site-portal/documents/${documentId}`,
    SITE_PORTAL_DOCUMENT_DOWNLOAD: (documentId: string) => `/site-portal/documents/${documentId}/download`,
    SITE_PORTAL_DOCUMENT_VIEW: (documentId: string) => `/site-portal/documents/${documentId}/view`,
  }
} as const

export type ApiEndpoint = keyof typeof API_CONFIG.ENDPOINTS
