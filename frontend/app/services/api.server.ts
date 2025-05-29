// frontend/app/services/api.server.ts - TIMEOUT FIX
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
    options: RequestInit = {},
    timeoutMs: number = 5000 // ✅ FIX: Timeout por defecto muy corto
  ): Promise<T> {
    const token = await this.getToken()
    
    const url = `${this.baseUrl}/api/v1${endpoint}`
    
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    }

    // ✅ FIX: Timeout agresivo para evitar requests largos
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      console.warn(`⏰ Request timeout after ${timeoutMs}ms: ${endpoint}`)
    }, timeoutMs)

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (response.status === 401) {
        // Token inválido o expirado, redirigir al login
        throw redirect('/auth/sign-in')
      }

      if (!response.ok) {
        const error = await response.text().catch(() => 'Unknown error')
        throw new Error(`API Error: ${response.status} - ${error}`)
      }

      return response.json()
    } catch (error) {
      clearTimeout(timeoutId)
      
      // ✅ FIX: Manejo específico de errores con mensajes claros
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error(`Timeout: Backend no responde en ${timeoutMs}ms`)
        }
        if (error.message.includes('fetch') || error.message.includes('network')) {
          throw new Error('Error de red: No se puede conectar al backend')
        }
        if (error.message.includes('ECONNREFUSED')) {
          throw new Error('Backend no disponible: Servidor apagado')
        }
      }
      
      throw error
    }
  }

  // ✅ FIX: Métodos con timeouts específicos según operación

  // Health check - muy rápido
  async healthCheck(): Promise<boolean> {
    try {
      await this.makeRequest('/health', {}, 2000) // Solo 2 segundos
      return true
    } catch {
      return false
    }
  }

  // Operaciones de usuario - rápidas
  async getCurrentUser() {
    return this.makeRequest('/auth/me', {}, 3000) // 3 segundos
  }

  async updateUser(userData: { username?: string; [key: string]: any }) {
    return this.makeRequest('/auth/me', {
      method: 'PUT',
      body: JSON.stringify(userData),
    }, 5000) // 5 segundos para updates
  }

  async deleteAccount() {
    return this.makeRequest('/auth/me', {
      method: 'DELETE',
    }, 10000) // 10 segundos para deletes críticos
  }

  // Documentos - pueden ser más lentos
  async getDocuments(params?: {
    page?: number
    per_page?: number
    limit?: number
    tags?: string[]
    date_from?: string
    date_to?: string
  }) {
    const searchParams = new URLSearchParams()
    
    if (params?.page) searchParams.append('page', params.page.toString())
    if (params?.per_page) searchParams.append('per_page', params.per_page.toString())
    if (params?.limit) searchParams.append('limit', params.limit.toString())
    if (params?.tags) params.tags.forEach(tag => searchParams.append('tags', tag))
    if (params?.date_from) searchParams.append('date_from', params.date_from)
    if (params?.date_to) searchParams.append('date_to', params.date_to)

    const queryString = searchParams.toString()
    const endpoint = `/documents${queryString ? `?${queryString}` : ''}`
    
    return this.makeRequest(endpoint, {}, 8000) // 8 segundos para listas
  }

  async getDocument(docId: string) {
    return this.makeRequest(`/documents/${docId}`, {}, 5000)
  }

  // ✅ FIX: Upload con timeout largo pero no infinito
  async createDocument(formData: FormData) {
    const token = await this.getToken()
    
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      console.warn('⏰ Upload timeout after 30 seconds')
    }, 30000) // 30 segundos para uploads

    try {
      const response = await fetch(`${this.baseUrl}/api/v1/documents/`, {
        method: 'POST',
        headers: {
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: formData,
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (response.status === 401) {
        throw redirect('/auth/sign-in')
      }

      if (!response.ok) {
        const error = await response.text().catch(() => 'Upload failed')
        throw new Error(`Upload Error: ${response.status} - ${error}`)
      }

      return response.json()
    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Upload timeout - Archivo muy grande o conexión lenta')
      }
      
      throw error
    }
  }

  async deleteDocument(docId: string) {
    return this.makeRequest(`/documents/${docId}`, {
      method: 'DELETE',
    }, 5000)
  }

  // Analytics - timeout corto, no crítico
  async getAnalytics() {
    return this.makeRequest('/analytics/dashboard', {}, 3000)
  }

  async getRecentActivity(params?: { limit?: number }) {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.append('limit', params.limit.toString())
    
    const queryString = searchParams.toString()
    const endpoint = `/activity/recent${queryString ? `?${queryString}` : ''}`
    
    return this.makeRequest(endpoint, {}, 3000)
  }

  // Búsqueda - puede tomar tiempo
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

    return this.makeRequest(`/search/?${searchParams.toString()}`, {}, 10000) // 10 segundos para búsquedas
  }

  async askDocuments(question: string, docIds?: string[]) {
    return this.makeRequest('/search/ask', {
      method: 'POST',
      body: JSON.stringify({
        question,
        doc_ids: docIds,
      }),
    }, 15000) // 15 segundos para IA
  }

  // Admin - timeout medio
  async getSystemStats() {
    return this.makeRequest('/admin/stats', {}, 5000)
  }

  async getDocumentActivityStats(timePeriodDays = 30) {
    return this.makeRequest(`/admin/stats/document-activity?time_period_days=${timePeriodDays}`, {}, 8000)
  }

  // Tenant info - rápido
  async getCurrentTenant() {
    return this.makeRequest('/tenants/current', {}, 3000)
  }

  // ✅ FIX: Utilidad para hacer múltiples requests con timeout global
  async makeMultipleRequests<T>(
    requests: (() => Promise<T>)[],
    globalTimeoutMs: number = 10000
  ): Promise<PromiseSettledResult<T>[]> {
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Global timeout exceeded')), globalTimeoutMs)
    })

    try {
      return await Promise.race([
        Promise.allSettled(requests.map(req => req())),
        timeoutPromise
      ])
    } catch (error) {
      console.warn('Multiple requests timed out after', globalTimeoutMs, 'ms')
      // Retornar resultados parciales como rejections
      return requests.map(() => ({
        status: 'rejected' as const,
        reason: new Error('Global timeout')
      }))
    }
  }
}