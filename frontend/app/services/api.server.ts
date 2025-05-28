// frontend/app/services/api.server.ts
import { redirect } from '@remix-run/node'

export interface ApiConfig {
  baseUrl: string
  getToken: () => Promise<string | null>
}

export class ApiService {
  private baseUrl: string
  private getToken: () => Promise<string | null>

  constructor(config: ApiConfig) {
    this.baseUrl = config.baseUrl
    this.getToken = config.getToken
  }

  private async makeRequest<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = await this.getToken()
    
    const url = `${this.baseUrl}/api/v1${endpoint}`
    
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    }

    const response = await fetch(url, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      // Token inválido o expirado, redirigir al login
      throw redirect('/auth/sign-in')
    }

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`API Error: ${response.status} - ${error}`)
    }

    return response.json()
  }

  // Métodos para documentos
  async getDocuments(params?: {
    page?: number
    per_page?: number
    tags?: string[]
    date_from?: string
    date_to?: string
  }) {
    const searchParams = new URLSearchParams()
    
    if (params?.page) searchParams.append('page', params.page.toString())
    if (params?.per_page) searchParams.append('per_page', params.per_page.toString())
    if (params?.tags) params.tags.forEach(tag => searchParams.append('tags', tag))
    if (params?.date_from) searchParams.append('date_from', params.date_from)
    if (params?.date_to) searchParams.append('date_to', params.date_to)

    const queryString = searchParams.toString()
    const endpoint = `/documents${queryString ? `?${queryString}` : ''}`
    
    return this.makeRequest(endpoint)
  }

  async getDocument(docId: string) {
    return this.makeRequest(`/documents/${docId}`)
  }

  async createDocument(formData: FormData) {
    const token = await this.getToken()
    
    const response = await fetch(`${this.baseUrl}/api/v1/documents/`, {
      method: 'POST',
      headers: {
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: formData,
    })

    if (response.status === 401) {
      throw redirect('/auth/sign-in')
    }

    if (!response.ok) {
      const error = await response.text()
      throw new Error(`API Error: ${response.status} - ${error}`)
    }

    return response.json()
  }

  async deleteDocument(docId: string) {
    return this.makeRequest(`/documents/${docId}`, {
      method: 'DELETE',
    })
  }

  async getDocumentSummary(docId: string) {
    return this.makeRequest(`/documents/${docId}/summary`)
  }

  // Métodos para búsqueda
  async searchDocuments(query: string, options?: {
    limit?: number
    tags?: string[]
    date_from?: string
    date_to?: string
  }) {
    const searchParams = new URLSearchParams({ query })
    
    if (options?.limit) searchParams.append('limit', options.limit.toString())
    if (options?.tags) options.tags.forEach(tag => searchParams.append('tags', tag))
    if (options?.date_from) searchParams.append('date_from', options.date_from)
    if (options?.date_to) searchParams.append('date_to', options.date_to)

    return this.makeRequest(`/search/?${searchParams.toString()}`)
  }

  async askDocuments(question: string, docIds?: string[]) {
    return this.makeRequest('/search/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        doc_ids: docIds,
      }),
    })
  }

  // Métodos para estadísticas (admin)
  async getSystemStats() {
    return this.makeRequest('/admin/stats')
  }

  async getDocumentActivityStats(timePeriodDays = 30) {
    return this.makeRequest(`/admin/stats/document-activity?time_period_days=${timePeriodDays}`)
  }

  // Métodos para usuarios
  async getCurrentUser() {
    return this.makeRequest('/auth/me')
  }

  async getUserProfile() {
    return this.makeRequest('/users/me')
  }

  // Método para obtener tenant actual
  async getCurrentTenant() {
    return this.makeRequest('/tenants/current')
  }
}