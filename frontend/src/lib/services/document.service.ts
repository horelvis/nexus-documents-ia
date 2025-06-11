import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'
import { Document, DocumentUploadResponse, SearchResponse } from '../types'

export interface DocumentListParams {
  page?: number
  per_page?: number
  category?: string
  tags?: string[]
  status?: string
  search?: string
}

export interface UploadDocumentParams {
  files: File[]
  category?: string
  tags?: string
  description?: string
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
    if (params.tags) {
      params.tags.forEach(tag => searchParams.append('tags', tag))
    }

    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}?${searchParams.toString()}`
    return this.apiClient.get<Document[]>(endpoint)
  }

  async getDocument(id: string) {
    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`
    return this.apiClient.get<Document>(endpoint)
  }

  async uploadDocuments(params: UploadDocumentParams) {
    const results = []
    let hasError = false
    
    // Upload each file individually
    for (const file of params.files) {
      try {
        const formData = new FormData()
        
        // Add single file
        formData.append('file', file)
        
        // Add metadata - use filename as title if no title provided
        formData.append('title', file.name)
        if (params.tags) {
          formData.append('tags', params.tags)
        }
        if (params.description) {
          formData.append('description', params.description)
        }

        const result = await this.apiClient.upload<DocumentUploadResponse>(
          API_CONFIG.ENDPOINTS.DOCUMENTS,
          formData
        )
        
        if (result.error) {
          hasError = true
        }
        
        results.push(result)
      } catch (error) {
        hasError = true
        results.push({
          error: error instanceof Error ? error.message : 'Upload failed',
          status: 500,
          data: null
        })
      }
    }
    
    return { 
      data: results, 
      error: hasError ? 'Some files failed to upload' : null, 
      status: hasError ? 207 : 200 // 207 = Multi-Status
    }
  }

  async deleteDocument(id: string) {
    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`
    return this.apiClient.delete(endpoint)
  }

  async updateDocument(id: string, updates: Partial<Pick<Document, 'title' | 'description' | 'tags' | 'category'>>) {
    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`
    return this.apiClient.put<Document>(endpoint, updates)
  }

  async getDocumentContent(id: string) {
    const endpoint = API_CONFIG.ENDPOINTS.DOCUMENT_CONTENT(id)
    return this.apiClient.get<{ content: string }>(endpoint)
  }

  async downloadDocument(id: string): Promise<{ blob: Blob; filename: string } | { error: string }> {
    try {
      // First get the download URL
      const urlResponse = await this.getDocumentDownloadUrl(id)
      if (urlResponse.error || !urlResponse.data?.download_url) {
        return { error: urlResponse.error || 'Failed to get download URL' }
      }

      // Download the file using the signed URL
      const response = await fetch(urlResponse.data.download_url)
      if (!response.ok) {
        return { error: `Download failed: ${response.statusText}` }
      }

      const blob = await response.blob()
      
      // Try to get filename from headers or fall back to document info
      let filename = 'document'
      const disposition = response.headers.get('content-disposition')
      if (disposition && disposition.includes('filename=')) {
        filename = disposition.split('filename=')[1].replace(/"/g, '')
      } else {
        // Get document info to get the filename
        const docResponse = await this.getDocument(id)
        if (docResponse.data?.filename) {
          filename = docResponse.data.filename
        }
      }

      return { blob, filename }
    } catch (error) {
      return { error: error instanceof Error ? error.message : 'Download failed' }
    }
  }

  async getDocumentSummary(id: string) {
    const endpoint = API_CONFIG.ENDPOINTS.DOCUMENT_SUMMARY(id)
    return this.apiClient.get<{ summary: string }>(endpoint)
  }

  async getDocumentDownloadUrl(id: string) {
    const endpoint = API_CONFIG.ENDPOINTS.DOCUMENT_DOWNLOAD(id)
    return this.apiClient.get<{ download_url: string }>(endpoint)
  }

  async searchDocuments(query: string, limit: number = 10) {
    const searchParams = new URLSearchParams({
      q: query,
      limit: limit.toString()
    })
    
    const endpoint = `${API_CONFIG.ENDPOINTS.SEARCH}?${searchParams.toString()}`
    return this.apiClient.get<SearchResponse>(endpoint)
  }

  async askQuestion(question: string, documentIds?: string[]) {
    const payload: any = { question }
    if (documentIds && documentIds.length > 0) {
      payload.document_ids = documentIds
    }
    
    return this.apiClient.post<{
      answer: string
      sources: Document[]
    }>(API_CONFIG.ENDPOINTS.SEARCH_ASK, payload)
  }
}

// Hook para usar el servicio de documentos
export function useDocumentService() {
  const apiClient = useApiClient()
  return useMemo(() => new DocumentService(apiClient), [apiClient])
}