export const API_CONFIG = {
  BASE_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
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
    DOCUMENT_DOWNLOAD: (id: string) => `/documents/${id}/download-url`,
    
    // Search
    SEARCH: '/search',
    SEARCH_ASK: '/search/ask',
    
    // Admin
    ADMIN_USERS: '/admin/users',
    ADMIN_STATS: '/admin/stats',
    
    // Tenants
    TENANTS: '/tenants',
    TENANTS_CURRENT: '/tenants/current',
    
    // Chat
    CHAT: '/chat',
    
    // Agents
    AGENTS: '/agents',
    
    // Digital Signatures
    SIGNATURES: '/signatures',
  }
} as const

export type ApiEndpoint = keyof typeof API_CONFIG.ENDPOINTS