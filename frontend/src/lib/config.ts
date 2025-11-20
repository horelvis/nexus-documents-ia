const baseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""

export const API_CONFIG = {
  BASE_URL: baseUrl,
  API_V1: '/api/v1',
  TIMEOUT: 30000, // 30 seconds
  
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
    
    // Elysia (New GAP Architecture)
    ELYSIA_QUERY: '/elysia/query',
    ELYSIA_TOOLS: '/elysia/tools',
  }
} as const

export type ApiEndpoint = keyof typeof API_CONFIG.ENDPOINTS
