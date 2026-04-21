"use client"

import { useApiClient } from '../api-client'

export interface LearningProfile {
  user_id: string
  response_style: 'balanced' | 'detailed' | 'concise'
  expertise_level: 'general' | 'technical' | 'expert'
  preferred_language: string
  preferred_document_types: string[]
  preferred_topics: string[]
  search_patterns: Record<string, unknown>
  total_queries: number
  total_document_views: number
  ranking_weights: RankingWeights
  frequent_document_ids: string[]
  frequent_queries: string[]
}

export interface RankingWeights {
  recency: number
  frequency: number
  relevance: number
}

export interface UserContext {
  name?: string
  language: string
  preferences: Record<string, string>
  visualization_preference?: string
  enable_suggestions: boolean
  frequent_queries: string[]
  frequent_documents: string[]
  favorite_tools: string[]
  custom_settings: Record<string, unknown>
  learning_enabled: boolean
  learning_applied: boolean
  learning?: Record<string, unknown>
  ranking_weights: RankingWeights
}

export interface LearningStats {
  user_id: string
  total_queries: number
  total_document_views: number
  frequent_queries_count: number
  frequent_documents_count: number
  search_patterns: Record<string, unknown>
  ranking_weights: RankingWeights
  learning_enabled: boolean
  profile_age_days: number
}

export interface UpdateProfileRequest {
  response_style?: 'balanced' | 'detailed' | 'concise'
  expertise_level?: 'general' | 'technical' | 'expert'
  preferred_language?: string
}

export function useLearningService() {
  const apiClient = useApiClient()
  const LEARNING_BASE = '/weaviate/learning'

  const getProfile = async () => {
    return apiClient.get<LearningProfile>(`${LEARNING_BASE}/profile`)
  }

  const updateProfile = async (updates: UpdateProfileRequest) => {
    return apiClient.put<LearningProfile>(`${LEARNING_BASE}/profile`, updates)
  }

  const getUserContext = async () => {
    return apiClient.get<UserContext>(`${LEARNING_BASE}/context`)
  }

  const getStats = async () => {
    return apiClient.get<LearningStats>(`${LEARNING_BASE}/stats`)
  }

  const getRankingWeights = async () => {
    return apiClient.get<{ user_id: string; weights: RankingWeights }>(
      `${LEARNING_BASE}/ranking-weights`
    )
  }

  const recordFeedback = async (
    sessionId: string,
    feedback: 'positive' | 'negative',
    feedbackText?: string
  ) => {
    const rating = feedback === 'positive' ? 5 : 1
    return apiClient.post<{ status: string; rating: number; message: string }>(
      `${LEARNING_BASE}/feedback`,
      {
        session_id: sessionId,
        rating,
        feedback_text: feedbackText
      }
    )
  }

  const recordDocumentView = async (
    documentId: string,
    dwellTimeSeconds?: number,
    scrollDepth?: number,
    actions?: string[]
  ) => {
    return apiClient.post<{ status: string; document_id: string; message: string }>(
      `${LEARNING_BASE}/document-view`,
      {
        document_id: documentId,
        dwell_time_seconds: dwellTimeSeconds,
        scroll_depth: scrollDepth,
        actions
      }
    )
  }

  const flushLearningData = async () => {
    return apiClient.post<{ status: string; message: string }>(
      `${LEARNING_BASE}/flush`,
      {}
    )
  }

  return {
    getProfile,
    updateProfile,
    getUserContext,
    getStats,
    getRankingWeights,
    recordFeedback,
    recordDocumentView,
    flushLearningData
  }
}
