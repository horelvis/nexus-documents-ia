/**
 * Document Forge Service
 * Client for template-based document modification via Main API proxy.
 *
 * IMPORTANT: apiClient returns { data, error, status } — it never throws.
 * Always check response.error, never use try/catch around apiClient calls.
 */

import { apiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'
import type { ForgeMetadata, ForgeField, ForgeOutputInfo, ForgeSessionStatus } from '@/lib/types/emma'

export interface ForgeAnalyzeResponse {
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
}

export interface ForgeRenderResponse {
  session_id: string
  outputs: Record<string, ForgeOutputInfo>
  document_title: string
  fields_filled: number
}

export interface ForgePersistResponse {
  document_id: string
  gcs_paths: Record<string, string>
  weaviate_indexed: boolean
  indexed_document_id?: string
}

export interface ForgeSessionInfo {
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
  status: ForgeSessionStatus
  field_values?: Record<string, string>
  outputs?: Record<string, ForgeOutputInfo>
  created_at: string
  updated_at?: string
}

export async function analyzeDocument(
  documentId: string,
  userIntent: string = 'modification',
): Promise<{ data: ForgeAnalyzeResponse | null; error: string | null }> {
  const formData = new FormData()
  formData.append('document_id', documentId)
  formData.append('user_intent', userIntent)

  const response = await apiClient.post<ForgeAnalyzeResponse>(
    API_CONFIG.ENDPOINTS.FORGE_ANALYZE,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function renderDocument(
  sessionId: string,
  fieldValues: Record<string, string>,
  outputFormats: string[] = ['docx', 'pdf'],
  documentTitle?: string,
): Promise<{ data: ForgeRenderResponse | null; error: string | null }> {
  const body: Record<string, any> = {
    session_id: sessionId,
    field_values: fieldValues,
    output_formats: outputFormats,
  }
  if (documentTitle) body.document_title = documentTitle

  const response = await apiClient.post<ForgeRenderResponse>(
    API_CONFIG.ENDPOINTS.FORGE_RENDER,
    body,
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function persistDocument(
  sessionId: string,
  options?: {
    persist_formats?: string[]
    folder_path?: string
    index_in_weaviate?: boolean
  },
): Promise<{ data: ForgePersistResponse | null; error: string | null }> {
  const body: Record<string, any> = { session_id: sessionId, ...options }
  const response = await apiClient.post<ForgePersistResponse>(
    API_CONFIG.ENDPOINTS.FORGE_PERSIST,
    body,
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function getSessionInfo(
  sessionId: string,
): Promise<{ data: ForgeSessionInfo | null; error: string | null }> {
  const response = await apiClient.get<ForgeSessionInfo>(
    API_CONFIG.ENDPOINTS.FORGE_SESSION_INFO(sessionId),
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function downloadDocument(
  sessionId: string,
  format: 'docx' | 'pdf' = 'docx',
): Promise<void> {
  const response = await apiClient.get(
    API_CONFIG.ENDPOINTS.FORGE_SESSION_DOWNLOAD(sessionId, format),
    { responseType: 'blob' },
  )
  if (response.error || !response.data) {
    console.error('Download failed:', response.error)
    return
  }
  const blob = new Blob([response.data as BlobPart])
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `document.${format}`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

export function cacheForgeSession(sessionId: string, data: ForgeMetadata): void {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(`forge_session_${sessionId}`, JSON.stringify(data))
}

export function getCachedForgeSession(sessionId: string): ForgeMetadata | null {
  if (typeof window === 'undefined') return null
  const cached = sessionStorage.getItem(`forge_session_${sessionId}`)
  if (!cached) return null
  try {
    return JSON.parse(cached)
  } catch {
    return null
  }
}
