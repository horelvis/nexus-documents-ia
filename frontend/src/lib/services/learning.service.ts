"use client"

import { useApiClient } from '../api-client'

// ============================================================================
// Types
// ============================================================================

export interface LearningProfile {
  user_id: string
  tenant_id: string
  response_style: 'balanced' | 'detailed' | 'concise'
  expertise_level: 'general' | 'technical' | 'expert'
  preferred_language: string
  preferred_document_types: string[]
  preferred_topics: string[]
  search_patterns: Record<string, any>
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
  custom_settings: Record<string, any>
  learning_enabled: boolean
  learning_applied: boolean
  learning?: Record<string, any>
  ranking_weights: RankingWeights
}

export interface LearningStats {
  user_id: string
  tenant_id: string
  total_queries: number
  total_document_views: number
  frequent_queries_count: number
  frequent_documents_count: number
  search_patterns: Record<string, any>
  ranking_weights: RankingWeights
  learning_enabled: boolean
  profile_age_days: number
}

export interface FeedbackRequest {
  session_id: string
  rating: 1 | 2 | 3 | 4 | 5
  feedback_text?: string
}

export interface DocumentViewRequest {
  document_id: string
  dwell_time_seconds?: number
  scroll_depth?: number
  actions?: string[]
}

export interface UpdateProfileRequest {
  response_style?: 'balanced' | 'detailed' | 'concise'
  expertise_level?: 'general' | 'technical' | 'expert'
  preferred_language?: string
}

// ============================================================================
// Service Hook
// ============================================================================

export function useLearningService() {
  const apiClient = useApiClient()

  // Learning endpoints are proxied through main API at /weaviate/learning
  const LEARNING_BASE = '/weaviate/learning'
  // Note: api-client automatically prepends tenant_id to base URL

  /**
   * Get user learning profile
   * Note: user_id is automatically extracted from auth token by backend
   */
  const getProfile = async () => {
    return apiClient.get<LearningProfile>(`${LEARNING_BASE}/profile`)
  }

  /**
   * Update user profile preferences
   */
  const updateProfile = async (updates: UpdateProfileRequest) => {
    return apiClient.put<LearningProfile>(`${LEARNING_BASE}/profile`, updates)
  }

  /**
   * Get user context for Emma (includes learning data)
   */
  const getUserContext = async () => {
    return apiClient.get<UserContext>(`${LEARNING_BASE}/context`)
  }

  /**
   * Get learning statistics
   */
  const getStats = async () => {
    return apiClient.get<LearningStats>(`${LEARNING_BASE}/stats`)
  }

  /**
   * Get personalized ranking weights for search
   */
  const getRankingWeights = async () => {
    return apiClient.get<{ user_id: string; tenant_id: string; weights: RankingWeights }>(
      `${LEARNING_BASE}/ranking-weights`
    )
  }

  /**
   * Record user feedback on Emma responses
   * Maps thumbs up/down to 5-point scale:
   * - positive (thumbs up) = 5
   * - negative (thumbs down) = 1
   */
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

  /**
   * Record document view for learning
   * Call when user opens/views a document
   */
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

  /**
   * Flush pending learning data
   * Call when user session ends
   */
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
