"use client"

import { useApiClient } from '../api-client'

export interface SearchResult {
  document: {
    id: string
    filename: string
    title?: string
    description?: string
    file_type: string
    mime_type: string
    file_size: number
    tags?: string[]
    created_at: string
    updated_at?: string
    indexed: string
  }
  score: number
  matches: Array<{
    text: string
    score: number
  }>
}

export interface SearchParams {
  query: string
  limit?: number
  search_type?: 'semantic' | 'hybrid' | 'keyword'
  tags?: string[]
  date_from?: string
  date_to?: string
}

export interface AskDocumentsParams {
  question: string
  doc_ids?: string[]
}

export interface AskDocumentsResponse {
  answer: string
  sources: Array<{
    document_id: string
    filename: string
    relevance_score: number
    excerpt: string
  }>
  context_used: boolean
}

export interface ReindexStatusResponse {
  tenant_id: string
  total_documents: number
  indexed_documents: number
  indexing_documents: number
  error_documents: number
  pending_documents: number
  missing_from_vector_store: number
  needs_reindexing: boolean
}

export interface ReindexResponse {
  total_documents: number
  success_count: number
  error_count: number
  message: string
}

export function useSearchService() {
  const apiClient = useApiClient()

  const searchDocuments = async (params: SearchParams) => {
    const queryParams = new URLSearchParams({
      query: params.query,
      ...(params.limit && { limit: params.limit.toString() }),
      ...(params.search_type && { search_type: params.search_type }),
      ...(params.tags && params.tags.length > 0 && { tags: params.tags.join(',') }),
      ...(params.date_from && { date_from: params.date_from }),
      ...(params.date_to && { date_to: params.date_to })
    })

    return apiClient.get<SearchResult[]>(`/search/?${queryParams.toString()}`)
  }

  const askDocuments = async (params: AskDocumentsParams) => {
    return apiClient.post<AskDocumentsResponse>('/search/ask', {
      question: params.question,
      doc_ids: params.doc_ids || []
    })
  }

  const getReindexStatus = async () => {
    return apiClient.get<ReindexStatusResponse>('/search/reindex/status')
  }

  const reindexAllDocuments = async () => {
    return apiClient.post<ReindexResponse>('/search/reindex/all')
  }

  const reindexSpecificDocuments = async (documentIds: string[]) => {
    return apiClient.post<ReindexResponse>('/search/reindex/documents', documentIds)
  }

  const fixAndReindex = async () => {
    return apiClient.post<{ message: string; status: string; success: boolean }>('/search/fix-and-reindex')
  }

  const autoReindexFailedDocuments = async () => {
    return apiClient.post<ReindexResponse>('/search/auto-reindex')
  }

  const runAutoReindexOnce = async () => {
    return apiClient.post<{ message: string; tenant_id: string; result: ReindexResponse }>('/search/auto-reindex/run-once')
  }

  const startGlobalAutoReindex = async () => {
    return apiClient.post<{ message: string; status: string; interval_seconds: number }>('/search/auto-reindex/start-global')
  }

  const getSearchAnalytics = async (dateFrom?: string, dateTo?: string) => {
    const queryParams = new URLSearchParams()
    if (dateFrom) queryParams.append('date_from', dateFrom)
    if (dateTo) queryParams.append('date_to', dateTo)
    
    return apiClient.get<{
      success: boolean
      analytics: {
        total_documents: number
        by_file_type: Array<{ key: string; count: number }>
        by_category: Array<{ key: string; count: number }>
        popular_tags: Array<{ tag: string; count: number }>
        documents_timeline: Array<{ date: string; count: number }>
        search_engines: {
          weaviate: { status: string; role: string }
          elasticsearch: { status: string; role: string }
        }
      }
      error?: string
    }>(`/search/analytics?${queryParams.toString()}`)
  }

  const suggestSearchType = async (query: string) => {
    return apiClient.get<{
      success: boolean
      query: string
      suggested_type: 'semantic' | 'hybrid' | 'keyword'
      description: string
      error?: string
    }>(`/search/suggest-type?query=${encodeURIComponent(query)}`)
  }

  return {
    searchDocuments,
    askDocuments,
    getReindexStatus,
    reindexAllDocuments,
    reindexSpecificDocuments,
    fixAndReindex,
    autoReindexFailedDocuments,
    runAutoReindexOnce,
    startGlobalAutoReindex,
    getSearchAnalytics,
    suggestSearchType
  }
}