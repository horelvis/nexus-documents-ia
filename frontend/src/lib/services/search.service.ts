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

export function useSearchService() {
  const apiClient = useApiClient()

  const searchDocuments = async (params: SearchParams) => {
    const queryParams = new URLSearchParams({
      query: params.query,
      ...(params.limit && { limit: params.limit.toString() }),
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

  return {
    searchDocuments,
    askDocuments
  }
}