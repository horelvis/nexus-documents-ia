"use client"

import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

export interface Document {
  id: string
  title: string
  file_type: string
  file_size: number
  created_at: string
  updated_at: string
  status: string
  category?: string
  tags?: string[]
  description?: string
  content_preview?: string
  source_type?: string
  external_url?: string
}

export interface DocumentListParams {
  page?: number
  per_page?: number
  category?: string
  tags?: string[]
  status?: string
  search?: string
  folder?: string
}

export interface DocumentUploadResponse {
  id: string
  title: string
  status: string
  message: string
}

export interface SingleDocumentParams {
  category?: string
  tags?: string
  description?: string
  folder_path?: string
}

export class DocumentService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async getDocuments(params: DocumentListParams = {}) {
    const searchParams = new URLSearchParams()
    if (params.page) searchParams.append('page', params.page.toString())
    if (params.per_page) searchParams.append('per_page', params.per_page.toString())
    if (params.category) searchParams.append('category', params.category)
    if (params.status) searchParams.append('status', params.status)
    if (params.search) searchParams.append('search', params.search)

    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}?${searchParams.toString()}`
    return this.apiClient.get<{
      items: Document[]
      total: number
      page: number
      per_page: number
      pages: number
    }>(endpoint)
  }

  async getDocument(id: string) {
    return this.apiClient.get<Document>(`${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`)
  }

  async uploadSingleDocument(
    file: File,
    params: SingleDocumentParams,
    onProgress?: (progress: number) => void
  ) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('title', file.name)
    if (params.tags) formData.append('tags', params.tags)
    if (params.description) formData.append('description', params.description)
    if (params.category) formData.append('category', params.category)
    if (params.folder_path) formData.append('folder_path', params.folder_path)

    return this.apiClient.upload<DocumentUploadResponse>(
      API_CONFIG.ENDPOINTS.DOCUMENTS,
      formData,
      onProgress
    )
  }

  async deleteDocument(id: string) {
    return this.apiClient.delete(`${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`)
  }

  /**
   * Get document stream URL for viewing/downloading
   */
  getDocumentStreamUrl(id: string): string {
    // Avoid duplicating /api/v1 if BASE_URL already contains it
    const base = API_CONFIG.BASE_URL
    const apiPrefix = base.includes('/api/v1') ? '' : API_CONFIG.API_V1
    const baseUrl = base + apiPrefix
    return `${baseUrl}${API_CONFIG.ENDPOINTS.DOCUMENT_STREAM(id)}`
  }

  /**
   * Search documents by query
   */
  async searchDocuments(query: string, limit: number = 10) {
    const searchParams = new URLSearchParams()
    searchParams.append('q', query)
    searchParams.append('limit', limit.toString())

    return this.apiClient.get<{
      results: Document[]
      total: number
    }>(`${API_CONFIG.ENDPOINTS.SEARCH}?${searchParams.toString()}`)
  }

  /**
   * Download document as blob with authentication.
   * Uses the streaming proxy endpoint to avoid CORS issues.
   * Returns blob and filename for display/download purposes.
   */
  async downloadDocument(id: string): Promise<{ blob: Blob; filename: string } | { error: string }> {
    try {
      const endpoint = API_CONFIG.ENDPOINTS.DOCUMENT_STREAM(id)
      const { blob, error } = await this.apiClient.downloadBlob(endpoint)

      if (error || !blob) {
        return { error: error || 'Download failed' }
      }

      // Get document info for filename
      const docResponse = await this.getDocument(id)
      const filename = docResponse.data?.title || 'document'

      return { blob, filename }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Download failed' }
    }
  }

  /**
   * Download a Gotenberg-converted PDF for non-PDF documents (DOCX, etc.).
   * Falls back to the raw stream if conversion is not available.
   */
  async downloadConvertedPdf(id: string): Promise<{ blob: Blob; filename: string } | { error: string }> {
    try {
      const endpoint = API_CONFIG.ENDPOINTS.DOCUMENT_CONVERTED_PDF(id)
      const { blob, error } = await this.apiClient.downloadBlob(endpoint)

      if (error || !blob) {
        return { error: error || 'Converted PDF not available' }
      }

      const docResponse = await this.getDocument(id)
      const filename = (docResponse.data?.title || 'document').replace(/\.[^.]+$/, '.pdf')

      return { blob, filename }
    } catch {
      return { error: 'Converted PDF not available' }
    }
  }
}

/**
 * Hook to get document service instance (memoized to prevent infinite loops)
 */
export function useDocumentService() {
  const apiClient = useApiClient()
  return useMemo(() => new DocumentService(apiClient), [apiClient])
}
