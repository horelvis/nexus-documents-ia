import { useMemo } from 'react'
import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

export interface DashboardStats {
  total_documents: number
  processed_documents: number
  processing_documents: number
  error_documents: number
  total_storage_bytes: number
  active_users: number
  recent_uploads: number
  trends: {
    documents: number
    storage: number
    active_users: number
    processed: number
    recent_uploads: number
    error_rate: number
  }
}

export interface ActivityLog {
  id: string
  type: string
  title: string
  description: string
  user_name: string
  user_email: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface RecentActivityResponse {
  activities: ActivityLog[]
  total: number
}

export interface AnalyticsTrends {
  period: string
  uploads_by_date: Record<string, number>
  views_by_date: Record<string, number>
  storage_by_date: Record<string, number>
  most_accessed_documents: Array<{
    document_id: string
    filename: string
    views: number
  }>
  total_uploads: number
  total_views: number
  total_storage_added: number
}

export interface AIInsight {
  type: string
  priority: string
  title: string
  description: string
  action_url?: string
  action_text?: string
}

export interface AIInsightsResponse {
  insights: AIInsight[]
  generated_at: string
}

export class DashboardService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async getDashboardStats() {
    return this.apiClient.get<DashboardStats>(`${API_CONFIG.ENDPOINTS.DASHBOARD}/stats`)
  }

  async getRecentActivity(limit: number = 10) {
    return this.apiClient.get<RecentActivityResponse>(
      `${API_CONFIG.ENDPOINTS.DASHBOARD}/activity/recent?limit=${limit}`
    )
  }

  async getAnalyticsTrends(period: '7d' | '30d' | '90d' = '7d') {
    return this.apiClient.get<AnalyticsTrends>(
      `${API_CONFIG.ENDPOINTS.DASHBOARD}/analytics/trends?period=${period}`
    )
  }

  async getAIInsights() {
    return this.apiClient.get<AIInsightsResponse>(
      `${API_CONFIG.ENDPOINTS.DASHBOARD}/insights/ai`
    )
  }
}

export function useDashboardService() {
  const apiClient = useApiClient()
  return useMemo(() => new DashboardService(apiClient), [apiClient])
}