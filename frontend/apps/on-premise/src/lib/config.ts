/**
 * API Configuration for Emma On-Premise
 */

const rawBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""

const isProxyBase = !rawBaseUrl || rawBaseUrl.startsWith("/")
const baseUrl = isProxyBase ? "/api" : rawBaseUrl

// For SSE streaming, we MUST bypass Next.js proxy (rewrites buffer responses)
// Use direct backend URL for streaming endpoints
const getStreamingBaseUrl = () => {
  // If explicit streaming URL is set, use it
  if (process.env.NEXT_PUBLIC_API_STREAMING_URL) {
    return process.env.NEXT_PUBLIC_API_STREAMING_URL
  }
  // If we have a direct API URL (not proxy), use it
  if (rawBaseUrl && !rawBaseUrl.startsWith("/")) {
    return rawBaseUrl
  }
  // Fallback: construct from window.location (same host, port 8000)
  if (typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`
  }
  // Server-side fallback
  return 'http://localhost:8000'
}

export const API_CONFIG = {
  BASE_URL: baseUrl,
  API_V1: isProxyBase ? "/v1" : "/api/v1",
  // Direct URL for streaming (bypasses Next.js proxy)
  STREAMING_BASE_URL: getStreamingBaseUrl(),
  TIMEOUT: 30000,
  EMMA_TIMEOUT: 180000,

  WEAVIATE_SERVICE_URL: process.env.NEXT_PUBLIC_WEAVIATE_SERVICE_URL || 'http://localhost:8007',

  ENDPOINTS: {
    // Auth
    LOGIN: '/auth/login/access-token',
    ME: '/auth/me',

    // Documents
    DOCUMENTS: '/documents',
    DOCUMENT_SUMMARY: (id: string) => `/documents/${id}/summary`,
    DOCUMENT_STREAM: (id: string) => `/documents/${id}/stream`,
    DOCUMENT_CONTENT: (id: string) => `/documents/${id}/content`,

    // Search
    SEARCH: '/search',

    // Tenants
    TENANTS: '/tenants',
    TENANTS_CURRENT: '/tenants/current',

    // Emma AI
    EMMA_QUERY: '/weaviate/emma/query',
    EMMA_TOOLS: '/weaviate/emma/tools',
    EMMA_HEALTH: '/weaviate/emma/health',
    EMMA_FEEDBACK: '/weaviate/emma/feedback',

    // Connectors
    CONNECTORS: '/connectors',
    CONNECTORS_ADMIN: '/connectors/admin',
    CONNECTOR_SYNC: (connectorId: string) => `/connectors/${connectorId}/sync`,

    // TTS (placeholder)
    TTS_VOICES: '/tts/voices',
    TTS_SYNTHESIZE: '/tts/synthesize',
  },
} as const

export type ApiEndpoints = typeof API_CONFIG.ENDPOINTS
