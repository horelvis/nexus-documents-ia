"use client"

/**
 * Entity Search Service
 *
 * Search TrustGraph entities by text similarity via Weaviate TrustGraphEntities.
 * Proxied through /api/v1/weaviate → weaviate-service.
 */

import { apiClient } from '@/lib/api-client'

export interface EntityMatch {
  entity_uri: string
  label: string
  definition: string
  entity_type: string
  score: number
}

export interface EntitySearchResponse {
  entities: EntityMatch[]
  count: number
}

class EntitySearchService {
  async search(
    query: string,
    limit: number = 10,
  ): Promise<EntityMatch[]> {
    try {
      const response = await apiClient.post<EntitySearchResponse>(
        '/api/v1/weaviate/entities/search',
        { query, limit },
      )
      return response.data?.entities ?? []
    } catch (error) {
      console.error('Entity search failed:', error)
      return []
    }
  }
}

export const entitySearchService = new EntitySearchService()
