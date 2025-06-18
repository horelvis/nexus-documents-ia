import { useMemo } from 'react'
import { useApiClient } from "@/lib/api-client"
import { ApiResponse } from "@/lib/types"

export interface SharedDocument {
  id: string
  document_id: string
  tenant_id: string
  created_by: string
  share_token: string
  share_url: string
  share_type: string
  expires_at: string | null
  max_access_count: number | null
  current_access_count: number
  is_active: boolean
  recipient_email: string | null
  recipient_name: string | null
  share_message: string | null
  permissions: Record<string, any> | null
  first_accessed_at: string | null
  last_accessed_at: string | null
  created_at: string
  updated_at: string
  revoked_at: string | null
  revoked_by: string | null
  // Document info
  document_title: string | null
  document_filename: string | null
}

export interface SharedDocumentsListResponse {
  shares: SharedDocument[]
  total: number
  page: number
  per_page: number
}

export interface DocumentShareCreate {
  document_id: string
  share_type?: string
  expires_at?: string | null
  max_access_count?: number | null
  password?: string | null
  recipient_email?: string | null
  recipient_name?: string | null
  share_message?: string | null
  permissions?: Record<string, any> | null
  recipients?: string[] | null
}

export interface DocumentShareUpdate {
  expires_at?: string | null
  max_access_count?: number | null
  is_active?: boolean | null
  permissions?: Record<string, any> | null
}

export interface ShareStatistics {
  total_shares: number
  active_shares: number
  expired_shares: number
  revoked_shares: number
  total_access_count: number
  unique_recipients: number
  most_accessed_documents: Array<{
    document_id: string
    title: string
    total_accesses: number
  }>
  recent_shares: SharedDocument[]
  access_by_date: Record<string, number>
  access_by_hour: Record<number, number>
}

export class SharedDocumentsService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async getSharedDocuments(params?: {
    page?: number
    per_page?: number
    document_id?: string
    is_active?: boolean
  }): Promise<ApiResponse<SharedDocumentsListResponse>> {
    const queryParams = new URLSearchParams()
    
    if (params?.page) queryParams.append('page', params.page.toString())
    if (params?.per_page) queryParams.append('per_page', params.per_page.toString())
    if (params?.document_id) queryParams.append('document_id', params.document_id)
    if (params?.is_active !== undefined) queryParams.append('is_active', params.is_active.toString())
    
    const query = queryParams.toString()
    const url = query ? `/shares?${query}` : '/shares'
    
    return this.apiClient.get<SharedDocumentsListResponse>(url)
  }

  async createShare(data: DocumentShareCreate): Promise<ApiResponse<SharedDocument>> {
    return this.apiClient.post<SharedDocument>('/shares', data)
  }

  async getShare(shareId: string): Promise<ApiResponse<SharedDocument>> {
    return this.apiClient.get<SharedDocument>(`/shares/${shareId}`)
  }

  async updateShare(shareId: string, data: DocumentShareUpdate): Promise<ApiResponse<SharedDocument>> {
    return this.apiClient.patch<SharedDocument>(`/shares/${shareId}`, data)
  }

  async revokeShare(shareId: string): Promise<ApiResponse<{ message: string }>> {
    return this.apiClient.delete<{ message: string }>(`/shares/${shareId}`)
  }

  async getShareStatistics(documentId?: string): Promise<ApiResponse<ShareStatistics>> {
    const params = documentId ? `?document_id=${documentId}` : ''
    return this.apiClient.get<ShareStatistics>(`/shares/statistics${params}`)
  }

  async getShareAccessLogs(shareId: string, params?: {
    page?: number
    per_page?: number
  }): Promise<ApiResponse<any>> {
    const queryParams = new URLSearchParams()
    if (params?.page) queryParams.append('page', params.page.toString())
    if (params?.per_page) queryParams.append('per_page', params.per_page.toString())
    
    const query = queryParams.toString()
    const url = query ? `/shares/${shareId}/logs?${query}` : `/shares/${shareId}/logs`
    
    return this.apiClient.get<any>(url)
  }
}

export function useSharedDocumentsService() {
  const apiClient = useApiClient()
  
  return useMemo(
    () => new SharedDocumentsService(apiClient),
    [apiClient]
  )
}