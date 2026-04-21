/**
 * Document Share Service
 * Handles document sharing operations with secure links and time-based expiration
 */

import { useApiClient } from '../api-client'

export interface DocumentShareRequest {
  document_id: string
  share_type?: 'view' | 'download' | 'edit'
  expires_at?: string // ISO date string
  max_access_count?: number
  password?: string
  recipient_email?: string
  recipient_name?: string
  share_message?: string
  permissions?: Record<string, any>
  recipients?: string[] // For bulk sharing
}

export interface DocumentShare {
  id: string
  document_id: string
  created_by: string
  share_token: string
  share_url: string
  share_type: string
  current_access_count: number
  max_access_count?: number
  expires_at?: string
  recipient_email?: string
  recipient_name?: string
  share_message?: string
  created_at: string
  is_active: boolean
  permissions?: Record<string, any>
}

export interface ShareStatistics {
  total_shares: number
  active_shares: number
  expired_shares: number
  total_access_count: number
  unique_visitors: number
}

export interface DocumentShareListResponse {
  shares: DocumentShare[]
  total: number
  page: number
  per_page: number
}

export function useDocumentShareService() {
  const client = useApiClient()

  const createShare = async (data: DocumentShareRequest) => {
    try {
      if (!client) {
        return { error: 'API client not available. Please try again.' }
      }
      
      const response = await client.post<DocumentShare>('/shares', data)
      return response
    } catch (error) {
      console.error('Failed to create document share:', error)
      return { error: error instanceof Error ? error.message : 'Failed to create share link' }
    }
  }

  const createBulkShares = async (data: DocumentShareRequest) => {
    try {
      const response = await client.post<any>('/shares/bulk', data)
      return response
    } catch (error) {
      console.error('Failed to create bulk shares:', error)
      return { error: error instanceof Error ? error.message : 'Failed to create bulk shares' }
    }
  }

  const listShares = async (params?: {
    document_id?: string
    is_active?: boolean
    page?: number
    per_page?: number
  }) => {
    try {
      const response = await client.get<DocumentShareListResponse>('/shares', params)
      return response
    } catch (error) {
      console.error('Failed to list document shares:', error)
      return { error: error instanceof Error ? error.message : 'Failed to list shares' }
    }
  }

  const getShare = async (shareId: string) => {
    try {
      const response = await client.get<DocumentShare>(`/shares/${shareId}`)
      return response
    } catch (error) {
      console.error('Failed to get document share:', error)
      return { error: error instanceof Error ? error.message : 'Failed to get share details' }
    }
  }

  const updateShare = async (shareId: string, data: Partial<DocumentShareRequest>) => {
    try {
      const response = await client.patch<DocumentShare>(`/shares/${shareId}`, data)
      return response
    } catch (error) {
      console.error('Failed to update document share:', error)
      return { error: error instanceof Error ? error.message : 'Failed to update share' }
    }
  }

  const revokeShare = async (shareId: string) => {
    try {
      const response = await client.delete<{ message: string }>(`/shares/${shareId}`)
      return response
    } catch (error) {
      console.error('Failed to revoke document share:', error)
      return { error: error instanceof Error ? error.message : 'Failed to revoke share' }
    }
  }

  const getStatistics = async (documentId?: string) => {
    try {
      const params = documentId ? { document_id: documentId } : undefined
      const response = await client.get<ShareStatistics>('/shares/statistics', params)
      return response
    } catch (error) {
      console.error('Failed to get share statistics:', error)
      return { error: error instanceof Error ? error.message : 'Failed to get statistics' }
    }
  }

  const getAccessLogs = async (shareId: string, params?: {
    page?: number
    per_page?: number
  }) => {
    try {
      const response = await client.get<any>(`/shares/${shareId}/logs`, params)
      return response
    } catch (error) {
      console.error('Failed to get access logs:', error)
      return { error: error instanceof Error ? error.message : 'Failed to get access logs' }
    }
  }

  const createQuickShare = async (documentId: string, shareType: 'view' | 'download' = 'view') => {
    const expiresAt = new Date()
    expiresAt.setHours(expiresAt.getHours() + 24) // 24 hours from now

    return createShare({
      document_id: documentId,
      share_type: shareType,
      expires_at: expiresAt.toISOString()
    })
  }

  const createSecureShare = async (data: {
    documentId: string
    password: string
    maxAccessCount?: number
    expirationHours?: number
    recipientEmail?: string
    recipientName?: string
    message?: string
  }) => {
    const expiresAt = new Date()
    expiresAt.setHours(expiresAt.getHours() + (data.expirationHours || 72)) // Default 3 days

    return createShare({
      document_id: data.documentId,
      share_type: 'view',
      password: data.password,
      max_access_count: data.maxAccessCount,
      expires_at: expiresAt.toISOString(),
      recipient_email: data.recipientEmail,
      recipient_name: data.recipientName,
      share_message: data.message
    })
  }

  return {
    createShare,
    createBulkShares,
    listShares,
    getShare,
    updateShare,
    revokeShare,
    getStatistics,
    getAccessLogs,
    createQuickShare,
    createSecureShare
  }
}