"use client"

import { useApiClient } from '../api-client'

export interface RecentDocument {
  id: string
  filename: string
  title: string
  description?: string
  file_type: string
  mime_type: string
  file_size: number
  tags: string[]
  created_at: string
  updated_at?: string
  indexed: boolean
  category?: string
  created_by: string
  last_viewed_at?: string
}

export interface DocumentViewStats {
  total_views: number
  unique_documents: number
  this_week: number
  this_month: number
}

export function useDocumentInsightsService() {
  const apiClient = useApiClient()

  const getRecentlyViewedDocuments = async (limit: number = 10, userSpecific: boolean = true) => {
    return apiClient.get<RecentDocument[]>(
      `/document-insights/recently-viewed?limit=${limit}&user_specific=${userSpecific}`
    )
  }

  const getViewStatistics = async (timeframe: 'week' | 'month' | 'all' = 'week') => {
    return apiClient.get<DocumentViewStats>(
      `/document-insights/view-stats?timeframe=${timeframe}`
    )
  }

  const getMostViewedDocuments = async (limit: number = 10, timeframe: 'week' | 'month' | 'all' = 'week') => {
    return apiClient.get<Array<RecentDocument & { view_count: number }>>(
      `/document-insights/most-viewed?limit=${limit}&timeframe=${timeframe}`
    )
  }

  const getDocumentViewHistory = async (documentId: string) => {
    return apiClient.get<Array<{
      id: string
      viewed_at: string
      view_duration_seconds?: number
      scroll_percentage?: number
      user: {
        id: string
        full_name?: string
        email: string
      }
    }>>(
      `/document-insights/document/${documentId}/views`
    )
  }

  // Mark document as viewed - call when user opens/views a document
  const markDocumentAsViewed = async (documentId: string, viewDurationSeconds?: number, scrollPercentage?: number) => {
    return apiClient.post<{ success: boolean; view_id: string }>(
      `/document-insights/mark-viewed`,
      {
        document_id: documentId,
        view_duration_seconds: viewDurationSeconds,
        scroll_percentage: scrollPercentage
      }
    )
  }

  return {
    getRecentlyViewedDocuments,
    getViewStatistics,
    getMostViewedDocuments,
    getDocumentViewHistory,
    markDocumentAsViewed
  }
}