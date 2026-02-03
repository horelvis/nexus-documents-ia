"use client"

/**
 * Predictive Analysis Service
 *
 * SSE streaming client for the predictive analysis pipeline.
 * Each factor is extracted, verified against evidence, and weighted before
 * the final prediction is synthesized.
 */

import { API_CONFIG } from '../config'

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return null
  try {
    const tokens = JSON.parse(stored)
    return tokens.access_token || null
  } catch {
    return null
  }
}

// Direct backend URL for SSE (bypasses Next.js proxy buffering)
const STREAMING_API_URL = `${API_CONFIG.STREAMING_BASE_URL}/api/v1`

export type PredictiveEventType =
  | 'factor_extracted'
  | 'factor_verification_started'
  | 'factor_weighted'
  | 'factor_rejected'
  | 'synthesis_started'
  | 'prediction_complete'
  | 'error'
  | 'progress'

export interface PredictiveStreamEvent {
  event_type: PredictiveEventType
  factor_id: string | null
  data: Record<string, any>
  timestamp: string
  progress_percent: number | null
}

export interface PredictiveAnalyzeParams {
  case_description: string
  tenant_id: string
  session_id?: string
  max_factors?: number
  sector_override?: string
  context_document_ids?: string[]
  uploaded_file_ids?: string[]
}

/**
 * Stream predictive analysis via SSE.
 * Yields parsed events as they arrive from the backend.
 */
export async function* queryPredictiveStream(
  params: PredictiveAnalyzeParams
): AsyncGenerator<PredictiveStreamEvent, void, unknown> {
  const token = getAccessToken()
  const streamUrl = `${STREAMING_API_URL}${API_CONFIG.ENDPOINTS.EMMA_PREDICTIVE_STREAM}`

  const response = await fetch(streamUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token || ''}`,
    },
    body: JSON.stringify(params),
  })

  if (!response.ok) {
    let errorDetail = ''
    try {
      const errorBody = await response.json()
      errorDetail = errorBody?.detail || errorBody?.message || ''
    } catch {
      // not JSON
    }
    throw new Error(errorDetail || `Predictive stream request failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) {
        buffer += decoder.decode(value, { stream: !done })
      }

      const parts = buffer.split('\n\n')
      if (done) {
        buffer = ''
        for (const part of parts) {
          const evt = parseSsePart(part)
          if (evt) {
            console.log('[Predictive] SSE parsed event:', evt.event_type, evt.factor_id)
            yield evt
          }
        }
        break
      } else {
        buffer = parts.pop() || ''
        for (const part of parts) {
          const evt = parseSsePart(part)
          if (evt) {
            console.log('[Predictive] SSE parsed event:', evt.event_type, evt.factor_id)
            yield evt
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseSsePart(part: string): PredictiveStreamEvent | null {
  const trimmed = part.trim()
  if (!trimmed || !trimmed.startsWith('data:')) return null
  const jsonStr = trimmed.slice('data:'.length).trim()
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as PredictiveStreamEvent
  } catch {
    console.warn('[Predictive] Failed to parse SSE:', jsonStr.slice(0, 100))
    return null
  }
}

/**
 * Download prediction PDF report.
 */
export async function downloadPredictivePdf(sessionId: string, tenantId: string): Promise<Blob> {
  const token = getAccessToken()
  const url = `${STREAMING_API_URL}/emma/predictive/analysis/${sessionId}/pdf?tenant_id=${encodeURIComponent(tenantId)}`

  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token || ''}`,
    },
  })

  if (!response.ok) {
    throw new Error(`PDF download failed: ${response.status}`)
  }

  return response.blob()
}

/**
 * Download prediction DOCX report.
 */
export async function downloadPredictiveDocx(sessionId: string, tenantId: string): Promise<Blob> {
  const token = getAccessToken()
  const url = `${STREAMING_API_URL}/emma/predictive/analysis/${sessionId}/docx?tenant_id=${encodeURIComponent(tenantId)}`

  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token || ''}`,
    },
  })

  if (!response.ok) {
    throw new Error(`DOCX download failed: ${response.status}`)
  }

  return response.blob()
}
