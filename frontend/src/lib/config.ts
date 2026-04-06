/**
 * API Configuration for Emma On-Premise
 */

const rawBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  ""

const isProxyBase = !rawBaseUrl || rawBaseUrl.startsWith("/")
const cleanedRawBaseUrl = rawBaseUrl.replace(/\/+$/, '')
const alreadyHasApiV1 = /\/api\/v1$/i.test(cleanedRawBaseUrl)
const baseUrl = isProxyBase ? "/api" : (alreadyHasApiV1 ? cleanedRawBaseUrl.replace(/\/api\/v1$/i, '') : cleanedRawBaseUrl)

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
    DOCUMENT_CONVERTED_PDF: (id: string) => `/documents/${id}/converted-pdf`,
    DOCUMENT_CONTENT: (id: string) => `/documents/${id}/content`,

    // Search
    SEARCH: '/search',

    // Tenants
    TENANTS: '/tenants',
    TENANTS_CURRENT: '/tenants/current',

    // Emma AI
    EMMA_QUERY: '/emma/query',
    EMMA_TOOLS: '/emma/tools',
    EMMA_HEALTH: '/emma/health',
    EMMA_UPLOAD_TEMP: '/emma/uploads/temp',
    EMMA_VERIFIED_STREAM: '/emma/verified/generate/stream',
    EMMA_VERIFIED_CLAIMS: '/emma/verified/session',
    EMMA_VERIFIED_SESSION_PDF: (sessionId: string) => `/emma/verified/session/${sessionId}/pdf`,
    EMMA_VERIFIED_SESSION_DOCX: (sessionId: string) => `/emma/verified/session/${sessionId}/docx`,
    EMMA_VERIFIED_RESUME_STREAM: (sessionId: string) => `/emma/verified/session/${sessionId}/resume/stream`,
    EMMA_GENERATED_DOWNLOAD: (docId: string) => `/emma/generated/${docId}/download`,
    EMMA_PREDICTIVE_STREAM: '/emma/predictive/analyze/stream',
    EMMA_MEMORY_FACTS: '/emma/memory/facts',
    EMMA_WELCOME: '/emma/welcome',
    EMMA_NOTIFICATIONS: '/emma/notifications',
    EMMA_NOTIFICATION_READ: (id: string) => `/emma/notifications/${id}/read`,
    EMMA_NOTIFICATIONS_READ_ALL: '/emma/notifications/read-all',

    // Document Forge
    FORGE_ANALYZE: '/forge/analyze',
    FORGE_RENDER: '/forge/render',
    FORGE_PERSIST: '/forge/persist',
    FORGE_SESSION_INFO: (id: string) => `/forge/sessions/${id}/info`,
    FORGE_SESSION_DOWNLOAD: (id: string, format: string) => `/forge/sessions/${id}/download?format=${format}`,

    // Connectors
    CONNECTORS: '/connectors',
    CONNECTORS_ADMIN: '/connectors/admin',
    CONNECTOR_SYNC: (connectorId: string) => `/connectors/${connectorId}/sync`,

    // TTS (placeholder)
    TTS_VOICES: '/tts/voices',
    TTS_SYNTHESIZE: '/tts/synthesize',

    // Explainability
    EXPLAINABILITY_GRAPH: '/emma/explainability/graph',
    EXPLAINABILITY_TRACE: (threadId: string, messageIndex: number) =>
      `/emma/explainability/trace/${threadId}/${messageIndex}`,
  },
} as const

export type ApiEndpoints = typeof API_CONFIG.ENDPOINTS
