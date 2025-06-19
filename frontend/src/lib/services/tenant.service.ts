import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

export interface ReindexStatus {
  total_documents: number
  indexed_documents: number
  missing_documents: number
  status: 'ready' | 'processing' | 'error'
}

export interface ReindexResult {
  total_documents: number
  documents_to_reindex: number
  successful: number
  failed: number
  details: any
}

export interface TenantInfo {
  id: string
  name: string
  display_name: string
  created_at: string
  user_count: number
  document_count: number
  storage_used: number
  max_storage_bytes: number
  max_users: number
  max_documents: number
  settings: Record<string, any>
}

export interface TenantStats {
  total_documents: number
  total_users: number
  storage_used_bytes: number
  storage_limit_bytes: number
  documents_by_type: Record<string, number>
  documents_by_status: Record<string, number>
}

export class TenantService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  // Get current tenant info
  async getCurrentTenant() {
    const endpoint = `${API_CONFIG.ENDPOINTS.TENANTS}/current`
    return this.apiClient.get<TenantInfo>(endpoint)
  }

  // Get tenant statistics
  async getTenantStats() {
    const endpoint = `${API_CONFIG.ENDPOINTS.TENANTS}/stats`
    return this.apiClient.get<TenantStats>(endpoint)
  }

  // Update tenant settings
  async updateTenant(tenantId: string, updates: Partial<TenantInfo>) {
    const endpoint = `${API_CONFIG.ENDPOINTS.TENANTS}/${tenantId}`
    return this.apiClient.put<TenantInfo>(endpoint, updates)
  }

  // Reindexing operations
  async getReindexStatus() {
    const endpoint = `${API_CONFIG.ENDPOINTS.SEARCH}/reindex/status`
    return this.apiClient.get<ReindexStatus>(endpoint)
  }

  async reindexMissingDocuments() {
    const endpoint = `${API_CONFIG.ENDPOINTS.SEARCH}/reindex/all`
    return this.apiClient.post<ReindexResult>(endpoint, {})
  }

  async forceReindexAll() {
    const endpoint = `${API_CONFIG.ENDPOINTS.SEARCH}/reindex/force`
    return this.apiClient.post<{ message: string; status: string; tenant_id: string }>(endpoint, {})
  }

  // Data deletion operations (admin only)
  async deleteAllDocuments() {
    const endpoint = `${API_CONFIG.ENDPOINTS.ADMIN}/delete-all-documents`
    return this.apiClient.post<{ deleted_count: number; message: string }>(endpoint, {
      confirm: true
    })
  }

  async deleteTenantData(tenantId: string) {
    const endpoint = `${API_CONFIG.ENDPOINTS.ADMIN}/tenants/${tenantId}/delete-data`
    return this.apiClient.post<{ message: string; deleted: Record<string, number> }>(endpoint, {
      confirm: true,
      delete_documents: true,
      delete_users: false, // Keep users by default
      delete_vectors: true
    })
  }

  // Clear vector database
  async clearVectorDatabase() {
    const endpoint = `${API_CONFIG.ENDPOINTS.ADMIN}/clear-vector-db`
    return this.apiClient.post<{ message: string; collections_cleared: string[] }>(endpoint, {
      confirm: true
    })
  }

  // Backup operations
  async createBackup() {
    const endpoint = `${API_CONFIG.ENDPOINTS.ADMIN}/backup`
    return this.apiClient.post<{ backup_id: string; message: string }>(endpoint, {})
  }

  // Maintenance operations
  async runMaintenance() {
    const endpoint = `${API_CONFIG.ENDPOINTS.ADMIN}/maintenance`
    return this.apiClient.post<{ 
      message: string
      operations_performed: string[]
      duration_seconds: number 
    }>(endpoint, {
      optimize_database: true,
      clean_orphaned_files: true,
      rebuild_search_index: false
    })
  }
}

// Hook para usar el servicio
export function useTenantService() {
  const apiClient = useApiClient()
  return useMemo(() => new TenantService(apiClient), [apiClient])
}