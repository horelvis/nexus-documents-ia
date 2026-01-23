"use client"

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
    const baseUrl = API_CONFIG.BASE_URL + API_CONFIG.API_V1
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
}

/**
 * Hook to get document service instance
 */
export function useDocumentService() {
  const apiClient = useApiClient()
  return new DocumentService(apiClient)
}
