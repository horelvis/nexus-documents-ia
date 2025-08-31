export const API_CONFIG = {
  BASE_URL: process.env.NEXT_PUBLIC_API_URL,
  API_V1: '/api/v1',
  TIMEOUT: 30000, // 30 seconds
  
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
    
    // Assistant
    ASSISTANT_CHAT: '/assistant/chat',
    ASSISTANT_CHAT_STREAM: '/assistant/chat/stream',
    ASSISTANT_CONVERSATION: (id: string) => `/assistant/conversation/${id}`,
    ASSISTANT_WELCOME: '/assistant/welcome',
  }
} as const

export type ApiEndpoint = keyof typeof API_CONFIG.ENDPOINTS