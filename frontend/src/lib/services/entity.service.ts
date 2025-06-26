import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

export interface Entity {
  id: string
  name: string
  email: string
  type: 'contact' | 'organization' | 'user' | 'agent'
  role?: string
  metadata?: Record<string, any>
}

export interface SearchEntitiesParams {
  query: string
  documentId?: string
  limit?: number
  types?: string[]
}

export class EntityService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async searchEntities(params: SearchEntitiesParams) {
    const searchParams = new URLSearchParams()
    
    searchParams.append('q', params.query)
    if (params.documentId) searchParams.append('document_id', params.documentId)
    if (params.limit) searchParams.append('limit', params.limit.toString())
    if (params.types) {
      params.types.forEach(type => searchParams.append('types', type))
    }

    const endpoint = `/search/entities?${searchParams.toString()}`
    console.log('Entity search endpoint:', endpoint)
    const response = await this.apiClient.get<{
      entities: Entity[]
      total: number
    }>(endpoint)
    console.log('Entity search API response:', response)
    return response
  }

  async getDocumentEntities(documentId: string) {
    const endpoint = `${API_CONFIG.ENDPOINTS.DOCUMENTS}/${documentId}/entities`
    return this.apiClient.get<{
      entities: Entity[]
    }>(endpoint)
  }

  async getRecentEntities(limit: number = 10) {
    const endpoint = `${API_CONFIG.ENDPOINTS.SEARCH}/entities/recent?limit=${limit}`
    return this.apiClient.get<{
      entities: Entity[]
    }>(endpoint)
  }
}

// Hook para usar el servicio de entidades
export function useEntityService() {
  const apiClient = useApiClient()
  return useMemo(() => new EntityService(apiClient), [apiClient])
}