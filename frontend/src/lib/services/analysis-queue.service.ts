/**
 * Analysis Queue Service
 *
 * Client for the Analysis Queue API endpoints.
 * Handles queuing documents for analysis, checking status, and retrieving results.
 */

import { useAuth } from '@clerk/nextjs'
import { useCallback, useMemo } from 'react'
import { API_CONFIG } from '../config'

// Types
export type AnalysisStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type AnalysisType = 'legal' | 'contract' | 'compliance' | 'general'

export interface AnalysisFinding {
  type: string
  severity?: string
  title: string
  description: string
  agent?: string
  location?: Record<string, unknown>
  references?: string[]
}

export interface AnalysisAnnotation {
  page: number
  x: number
  y: number
  width: number
  height: number
  type: string
  color?: string
  text?: string
  finding_id?: string
}

export interface AnalysisJobCreate {
  id: string
  document_id: string
  status: AnalysisStatus
  created_at: string
}

export interface AnalysisJobProgress {
  id: string
  document_id: string
  status: AnalysisStatus
  progress: number
  analysis_type: string
  current_step?: string
  plan_title?: string
  total_steps: number
  steps_completed: number
  detected_document_type?: string
  detected_document_type_display?: string
  detection_confidence?: number
  started_at?: string
  error_message?: string
}

export interface AnalysisJobResult extends AnalysisJobProgress {
  summary?: string
  risks: AnalysisFinding[]
  recommendations: AnalysisFinding[]
  findings: AnalysisFinding[]
  annotations: AnalysisAnnotation[]
  annotated_pdf_url?: string
  confidence_score?: number
  execution_time_ms?: number
  completed_at?: string
  created_at: string
}

export interface AnalysisJobListItem {
  id: string
  document_id: string
  document_filename?: string
  status: AnalysisStatus
  progress: number
  analysis_type: string
  current_step?: string
  started_at?: string
  completed_at?: string
  created_at: string
  error_message?: string
}

export interface AnalysisQueueStats {
  pending_count: number
  processing_count: number
  completed_count: number
  failed_count: number
  total_count: number
  avg_execution_time_ms?: number
}

export interface AnalysisQueueResponse {
  jobs: AnalysisJobListItem[]
  stats: AnalysisQueueStats
  total: number
  page: number
  page_size: number
}

// API Configuration
const normalizedBaseUrl = (API_CONFIG.BASE_URL || '').replace(/\/$/, '')
const BASE_API_URL = `${normalizedBaseUrl}${API_CONFIG.API_V1}`
const ANALYSIS_QUEUE_PATH = '/analysis'

/**
 * Fetch with timeout helper
 */
const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeoutMs: number = 30000) => {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (error) {
    const errorName = (error as { name?: string })?.name
    if (errorName === 'AbortError') {
      throw new Error(`Request timed out after ${Math.ceil(timeoutMs / 1000)}s`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Parse API response
 */
const parseResponse = async <T>(response: Response, defaultErrorPrefix: string): Promise<T> => {
  const rawPayload = await response.text()
  let data: unknown = null

  if (rawPayload) {
    try {
      data = JSON.parse(rawPayload)
    } catch {
      data = rawPayload
    }
  }

  if (!response.ok) {
    const dataObj = data as Record<string, unknown> | null
    const detail =
      typeof data === 'string'
        ? data
        : dataObj?.detail || dataObj?.message || dataObj?.error || ''
    const message = detail
      ? `${defaultErrorPrefix}: ${detail}`
      : `${defaultErrorPrefix} (status ${response.status})`
    throw new Error(String(message))
  }

  return data as T
}

/**
 * Analysis Queue Service Hook
 */
export function useAnalysisQueueService() {
  const { getToken } = useAuth()
  const apiBase = BASE_API_URL

  /**
   * Queue a document for analysis
   */
  const queueAnalysis = useCallback(async (
    documentId: string,
    analysisType: AnalysisType = 'legal',
    priority: number = 0
  ): Promise<AnalysisJobCreate> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify({
          document_id: documentId,
          analysis_type: analysisType,
          priority
        })
      }
    )

    return parseResponse<AnalysisJobCreate>(response, 'Failed to queue analysis')
  }, [getToken, apiBase])

  /**
   * Queue multiple documents for analysis
   */
  const queueBatchAnalysis = useCallback(async (
    documentIds: string[],
    analysisType: AnalysisType = 'legal',
    priority: number = 0
  ): Promise<AnalysisJobCreate[]> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}/batch`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify({
          document_ids: documentIds,
          analysis_type: analysisType,
          priority
        })
      }
    )

    return parseResponse<AnalysisJobCreate[]>(response, 'Failed to queue batch analysis')
  }, [getToken, apiBase])

  /**
   * Get analysis job status
   */
  const getJobStatus = useCallback(async (jobId: string): Promise<AnalysisJobProgress> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}/${jobId}`,
      {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      }
    )

    return parseResponse<AnalysisJobProgress>(response, 'Failed to get job status')
  }, [getToken, apiBase])

  /**
   * Get complete analysis result
   */
  const getJobResult = useCallback(async (jobId: string): Promise<AnalysisJobResult> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}/${jobId}/result`,
      {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      }
    )

    return parseResponse<AnalysisJobResult>(response, 'Failed to get job result')
  }, [getToken, apiBase])

  /**
   * Cancel an analysis job
   */
  const cancelJob = useCallback(async (jobId: string): Promise<{ message: string; job_id: string }> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}/${jobId}`,
      {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      }
    )

    return parseResponse<{ message: string; job_id: string }>(response, 'Failed to cancel job')
  }, [getToken, apiBase])

  /**
   * List all analysis jobs
   */
  const listJobs = useCallback(async (
    options?: {
      status?: AnalysisStatus
      documentId?: string
      page?: number
      pageSize?: number
    }
  ): Promise<AnalysisQueueResponse> => {
    const token = await getToken()

    const params = new URLSearchParams()
    if (options?.status) params.append('status', options.status)
    if (options?.documentId) params.append('document_id', options.documentId)
    if (options?.page) params.append('page', String(options.page))
    if (options?.pageSize) params.append('page_size', String(options.pageSize))

    const url = `${apiBase}${ANALYSIS_QUEUE_PATH}${params.toString() ? `?${params}` : ''}`

    const response = await fetchWithTimeout(url, {
      headers: {
        'Authorization': `Bearer ${token || ''}`
      }
    })

    return parseResponse<AnalysisQueueResponse>(response, 'Failed to list jobs')
  }, [getToken, apiBase])

  /**
   * Get analysis history for a document
   */
  const getDocumentHistory = useCallback(async (
    documentId: string,
    limit: number = 10
  ): Promise<AnalysisJobListItem[]> => {
    const token = await getToken()

    const response = await fetchWithTimeout(
      `${apiBase}${ANALYSIS_QUEUE_PATH}/document/${documentId}/history?limit=${limit}`,
      {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      }
    )

    return parseResponse<AnalysisJobListItem[]>(response, 'Failed to get document history')
  }, [getToken, apiBase])

  return useMemo(() => ({
    queueAnalysis,
    queueBatchAnalysis,
    getJobStatus,
    getJobResult,
    cancelJob,
    listJobs,
    getDocumentHistory
  }), [queueAnalysis, queueBatchAnalysis, getJobStatus, getJobResult, cancelJob, listJobs, getDocumentHistory])
}
