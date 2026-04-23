"use client"

/**
 * Emma Service for On-Premise Emma App
 *
 * Simplified version that works with SSO authentication instead of Clerk.
 */

import { API_CONFIG } from '../config'

// Error types for better UX
export type EmmaErrorType = 'network' | 'timeout' | 'server' | 'auth' | 'serviceUnavailable' | 'unknown'

export interface EmmaError {
  type: EmmaErrorType
  message: string
  titleKey: string
  messageKey: string
  canRetry: boolean
  originalError?: Error
}

export function classifyError(error: unknown): EmmaError {
  const err = error instanceof Error ? error : new Error(String(error))
  const message = err.message.toLowerCase()

  if (
    message.includes('failed to fetch') ||
    message.includes('network') ||
    message.includes('connection refused')
  ) {
    return {
      type: 'network',
      message: err.message,
      titleKey: 'emma.errors.network.title',
      messageKey: 'emma.errors.network.message',
      canRetry: true,
      originalError: err
    }
  }

  if (message.includes('timeout') || message.includes('aborted')) {
    return {
      type: 'timeout',
      message: err.message,
      titleKey: 'emma.errors.timeout.title',
      messageKey: 'emma.errors.timeout.message',
      canRetry: true,
      originalError: err
    }
  }

  if (message.includes('503') || message.includes('502') || message.includes('unavailable')) {
    return {
      type: 'serviceUnavailable',
      message: err.message,
      titleKey: 'emma.errors.serviceUnavailable.title',
      messageKey: 'emma.errors.serviceUnavailable.message',
      canRetry: true,
      originalError: err
    }
  }

  if (message.includes('500') || message.includes('server error')) {
    return {
      type: 'server',
      message: err.message,
      titleKey: 'emma.errors.server.title',
      messageKey: 'emma.errors.server.message',
      canRetry: true,
      originalError: err
    }
  }

  if (message.includes('401') || message.includes('403') || message.includes('unauthorized') || message.includes('authorization header')) {
    return {
      type: 'auth',
      message: err.message,
      titleKey: 'emma.errors.auth.title',
      messageKey: 'emma.errors.auth.message',
      canRetry: false,
      originalError: err
    }
  }

  return {
    type: 'unknown',
    message: err.message,
    titleKey: 'emma.errors.unknown.title',
    messageKey: 'emma.errors.unknown.message',
    canRetry: true,
    originalError: err
  }
}

export interface EmmaQuery {
  query: string
  session_id: string
  context?: Record<string, unknown>
  enable_debug?: boolean
  deep_reasoning?: boolean
}

export interface EmmaResponse {
  query: string
  answer: string
  session_id: string
  decision_path: string[]
  tools_used: string[]
  data: unknown
  visualization: unknown
  confidence_score: number
  execution_time_ms: number
  iterations: number
  learning_applied: boolean
}

export interface EmmaAgent {
  name: string
  description: string
  capabilities: string[]
  status: 'active' | 'inactive'
}

export interface ClarificationOption {
  label: string
  value: string
  description?: string
}

import { ReasoningStepType } from '@/lib/types/emma'

export interface EmmaStreamEvent {
  event: 'start' | 'plan_created' | 'step_start' | 'step_complete' | 'step_error' | 'complete' | 'error' | 'token' | 'first_token' | 'clarification' | 'hitl_review' | 'progress' | 'structural_step'
  data: {
    message?: string
    text?: string // Token text for streaming events
    progress?: number
    step?: number
    question?: string
    header?: string
    options?: ClarificationOption[]
    multi_select?: boolean
    severity?: 'info' | 'warning' | 'critical'
    suggestions?: Array<{ label: string; action: string; description?: string }>
    total_steps?: number
    agent?: string
    description?: string
    findings_count?: number
    execution_time_ms?: number
    error?: string
    plan_id?: string
    steps?: Array<{ index: number; description: string; agent: string }>
    final_result?: unknown
    answer?: string
    success?: boolean
    session_id?: string
    tools_used?: string[] // Tools used during processing
    elapsed_ms?: number // Time elapsed for delegation events
    // LangGraph chain-of-thought fields
    stage?: string // Current stage
    isReasoning?: boolean // Whether LLM is currently reasoning
    route?: string // LangGraph execution route
    // Interleaved thinking / structural_step fields
    step_type?: ReasoningStepType
    content?: string
    entities?: string[]
    confidence?: number
  }
}

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

const normalizedBaseUrl = (API_CONFIG.BASE_URL || '').replace(/\/$/, '')
const BASE_API_URL = `${normalizedBaseUrl}${API_CONFIG.API_V1}`
// For SSE streaming, use direct backend URL to bypass Next.js proxy buffering
const STREAMING_API_URL = `${API_CONFIG.STREAMING_BASE_URL}/api/v1`
const EMMA_QUERY_PATH = '/emma/query'
const EMMA_QUERY_STREAM_PATH = '/emma/query/stream'
const EMMA_QUERY_RESUME_STREAM_PATH = '/emma/query/resume/stream'
const EMMA_TOOLS_PATH = '/emma/tools'

// Re-export from canonical type definitions
export type { ReasoningStepType, ReasoningStep } from '@/lib/types/emma'

const fetchWithTimeout = async (url: string, options: RequestInit = {}, useEmmaTimeout = false) => {
  const controller = new AbortController()
  const timeoutMs = useEmmaTimeout ? 180000 : 30000
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (error) {
    if ((error as Error)?.name === 'AbortError') {
      throw new Error(`Emma request timed out after ${Math.ceil(timeoutMs / 1000)}s`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

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
    const detail =
      typeof data === 'string'
        ? data
        : (data as Record<string, string>)?.detail ||
          (data as Record<string, string>)?.message ||
          (data as Record<string, string>)?.error || ''
    const message = detail
      ? `${defaultErrorPrefix}: ${detail}`
      : `${defaultErrorPrefix} (status ${response.status})`
    throw new Error(message)
  }

  return data as T
}

export async function generateReportDocument(
  reportId: string,
  mode: 'new' | 'template' = 'new',
  templateDocumentId?: string,
  title?: string,
): Promise<{ download_url: string; format: string; size_bytes: number; title: string }> {
  const token = getAccessToken()
  const resp = await fetchWithTimeout(
    `${BASE_API_URL}/emma/reports/${reportId}/generate-document`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token || ''}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        mode,
        template_document_id: templateDocumentId,
        title,
      }),
    },
    true,
  )
  return parseResponse(resp, 'Failed to generate report document')
}

export function getReportDownloadUrl(reportId: string): string {
  return `${BASE_API_URL}/emma/reports/${reportId}/download`
}

export function useEmmaService() {
  const apiBase = BASE_API_URL

  const uploadTempDocument = async (file: File): Promise<{ upload_id: string; filename: string; characters?: number }> => {
    const token = getAccessToken()
    const formData = new FormData()
    formData.append('file', file, file.name)

    const response = await fetchWithTimeout(
      `${apiBase}${API_CONFIG.ENDPOINTS.EMMA_UPLOAD_TEMP}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token || ''}`
        },
        body: formData
      },
      true
    )

    return await parseResponse(response, 'Temp upload failed')
  }

  const queryEmma = async (query: EmmaQuery): Promise<EmmaResponse> => {
    const token = getAccessToken()

    const response = await fetchWithTimeout(
      `${apiBase}${EMMA_QUERY_PATH}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token || ''}`
        },
        body: JSON.stringify(query)
      },
      true
    )

    return await parseResponse<EmmaResponse>(response, 'Emma query failed')
  }

  /**
   * Stream Emma query responses using async generator pattern.
   * Uses direct backend URL to bypass Next.js proxy buffering.
   */
  async function* queryEmmaStreamGenerator(
    query: EmmaQuery
  ): AsyncGenerator<EmmaStreamEvent, void, unknown> {
    const token = getAccessToken()

    // Use direct backend URL to bypass Next.js proxy buffering for SSE
    const streamUrl = `${STREAMING_API_URL}${EMMA_QUERY_STREAM_PATH}`
    console.log('[Emma] Streaming URL:', streamUrl)

    const response = await fetch(streamUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token || ''}`
      },
      body: JSON.stringify(query)
    })

    if (!response.ok) {
      let errorDetail = ''
      try {
        const errorBody = await response.json()
        errorDetail = errorBody?.detail || errorBody?.message || ''
      } catch {
        // Response body not JSON
      }
      throw new Error(errorDetail || `Stream request failed: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentData = ''

    const processLine = (line: string): EmmaStreamEvent | null => {
      const normalized = line.replace(/\r$/, '')

      // Comments in SSE start with ":"
      if (normalized.startsWith(':')) return null

      if (normalized.startsWith('event:')) {
        currentEvent = normalized.slice('event:'.length).trim()
      } else if (normalized.startsWith('data:')) {
        const chunk = normalized.slice('data:'.length)
        const dataPart = chunk.startsWith(' ') ? chunk.slice(1) : chunk
        currentData = currentData ? `${currentData}\n${dataPart}` : dataPart
      } else if (normalized.trim() === '' && currentData) {
        const eventName = (currentEvent || 'progress') as EmmaStreamEvent['event']
        try {
          const parsed = JSON.parse(currentData)
          const data =
            parsed && typeof parsed === 'object' ? parsed : { message: String(parsed) }
          const event = { event: eventName, data } as EmmaStreamEvent
          currentEvent = ''
          currentData = ''
          return event
        } catch {
          console.warn('[Emma] Failed to parse SSE data:', currentData?.slice(0, 100))
          const event = { event: eventName, data: { message: currentData } } as EmmaStreamEvent
          currentEvent = ''
          currentData = ''
          return event
        }
      }
      return null
    }

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (value) {
          buffer += decoder.decode(value, { stream: !done })
        }

        const lines = buffer.split('\n')

        if (done) {
          // Stream ended - process ALL remaining lines
          buffer = ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
          // Final flush with empty line to trigger any pending event
          const finalEvent = processLine('')
          if (finalEvent) yield finalEvent
          break
        } else {
          // Keep incomplete line in buffer for next iteration
          buffer = lines.pop() || ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  /**
   * Stream Emma query with callback interface (wrapper around generator).
   * Use queryEmmaStreamGenerator directly for better control.
   */
  const queryEmmaStream = async (
    query: EmmaQuery,
    onEvent: (event: EmmaStreamEvent) => void
  ): Promise<void> => {
    for await (const event of queryEmmaStreamGenerator(query)) {
      onEvent(event)
      // If many events arrive in a single network chunk, yield control so the UI can paint.
      if (event.event === 'token') {
        await new Promise<void>((resolve) => setTimeout(resolve, 0))
      }
    }
  }

  const getAvailableAgents = async (): Promise<EmmaAgent[]> => {
    try {
      const token = getAccessToken()
      const response = await fetchWithTimeout(`${apiBase}${EMMA_TOOLS_PATH}`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      })

      const data = await parseResponse<{ tools?: EmmaAgent[] }>(
        response,
        'Failed to get agents'
      )

      if (data?.tools && Array.isArray(data.tools) && data.tools.length > 0) {
        return data.tools
      }

      return [
        { name: 'text_response', description: 'Generación de respuestas de texto', capabilities: ['conversación', 'respuestas'], status: 'active' },
        { name: 'cited_summarize', description: 'Resúmenes con citas de documentos', capabilities: ['resumen', 'citas', 'documentos'], status: 'active' },
        { name: 'aggregate', description: 'Agregación de datos', capabilities: ['análisis', 'agregación'], status: 'active' },
        { name: 'query', description: 'Búsquedas avanzadas en documentos', capabilities: ['búsqueda', 'consultas'], status: 'active' },
        { name: 'visualise', description: 'Visualización de datos', capabilities: ['gráficos', 'visualización'], status: 'active' }
      ]
    } catch (error) {
      console.error('Error getting Emma agents:', error)
      return []
    }
  }

  const sendMessage = async (
    message: string,
    sessionId: string,
    enableDebug = false,
    context?: Record<string, unknown>
  ): Promise<EmmaResponse> => {
    return queryEmma({
      query: message,
      session_id: sessionId,
      enable_debug: enableDebug,
      context
    })
  }

  const getWelcomeMessage = async (sessionId: string): Promise<EmmaResponse> => {
    return queryEmma({
      query: "Genera un mensaje de bienvenida personalizado para el usuario",
      session_id: sessionId,
      context: { is_welcome: true }
    })
  }

  /**
   * Resume a paused graph after a HITL interrupt (e.g., clarification).
   * Uses the same SSE event format as queryEmmaStreamGenerator.
   */
  async function* resumeQueryStreamGenerator(
    threadId: string,
    resumeValue: string | Record<string, unknown>,
    userId?: string,
  ): AsyncGenerator<EmmaStreamEvent, void, unknown> {
    const token = getAccessToken()
    const streamUrl = `${STREAMING_API_URL}${EMMA_QUERY_RESUME_STREAM_PATH}`

    const response = await fetch(streamUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token || ''}`
      },
      body: JSON.stringify({
        thread_id: threadId,
        resume_value: resumeValue,
        user_id: userId || undefined,
      })
    })

    if (!response.ok) {
      let errorDetail = ''
      try {
        const errorBody = await response.json()
        errorDetail = errorBody?.detail || errorBody?.message || ''
      } catch {
        // Response body not JSON
      }
      throw new Error(errorDetail || `Resume stream failed: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentData = ''

    const processLine = (line: string): EmmaStreamEvent | null => {
      const normalized = line.replace(/\r$/, '')
      if (normalized.startsWith(':')) return null
      if (normalized.startsWith('event:')) {
        currentEvent = normalized.slice('event:'.length).trim()
      } else if (normalized.startsWith('data:')) {
        const chunk = normalized.slice('data:'.length)
        const dataPart = chunk.startsWith(' ') ? chunk.slice(1) : chunk
        currentData = currentData ? `${currentData}\n${dataPart}` : dataPart
      } else if (normalized.trim() === '' && currentData) {
        const eventName = (currentEvent || 'progress') as EmmaStreamEvent['event']
        try {
          const parsed = JSON.parse(currentData)
          const data = parsed && typeof parsed === 'object' ? parsed : { message: String(parsed) }
          const event = { event: eventName, data } as EmmaStreamEvent
          currentEvent = ''
          currentData = ''
          return event
        } catch {
          const event = { event: eventName, data: { message: currentData } } as EmmaStreamEvent
          currentEvent = ''
          currentData = ''
          return event
        }
      }
      return null
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (value) buffer += decoder.decode(value, { stream: !done })
        const lines = buffer.split('\n')
        if (done) {
          buffer = ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
          const finalEvent = processLine('')
          if (finalEvent) yield finalEvent
          break
        } else {
          buffer = lines.pop() || ''
          for (const line of lines) {
            const event = processLine(line)
            if (event) yield event
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  }

  return {
    queryEmma,
    queryEmmaStream,
    queryEmmaStreamGenerator,
    resumeQueryStreamGenerator,
    uploadTempDocument,
    getAvailableAgents,
    sendMessage,
    getWelcomeMessage,
  }
}
