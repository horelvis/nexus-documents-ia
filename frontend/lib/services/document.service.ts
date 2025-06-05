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
  category: string
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
    const formData = new FormData()
    
    // Agregar archivos
    params.files.forEach((file, index) => {
      formData.append('files', file)
    })
    
    // Agregar metadatos
    formData.append('category', params.category)
    if (params.tags) {
      formData.append('tags', params.tags)
    }
    if (params.description) {
      formData.append('description', params.description)
    }

    return this.apiClient.upload<DocumentUploadResponse[]>(
      API_CONFIG.ENDPOINTS.DOCUMENTS,
      formData
    )
  }

  async deleteDocument(id: string) {
    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}/${id}`
    return this.apiClient.delete(endpoint)
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
  return new DocumentService(apiClient)
}