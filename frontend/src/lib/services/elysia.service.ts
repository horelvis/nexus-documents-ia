import { useAuth } from '@clerk/nextjs'
import { useCallback, useMemo } from 'react'
import { API_CONFIG } from '../config'

export interface ElysiaQuery {
  query: string
  session_id: string
  tenant_id: string
  context?: Record<string, any>
  enable_debug?: boolean
}

export interface ElysiaResponse {
  query: string
  answer: string
  session_id: string
  tenant_id: string
  decision_path: string[]
  tools_used: string[]
  data: any
  visualization: any
  confidence_score: number
  execution_time_ms: number
  iterations: number
  learning_applied: boolean
}

export interface ElysiaAgent {
  name: string
  description: string
  capabilities: string[]
  status: 'active' | 'inactive'
}

const normalizedBaseUrl = (API_CONFIG.BASE_URL || '').replace(/\/$/, '')
const BASE_API_URL = `${normalizedBaseUrl}${API_CONFIG.API_V1}`
const ELYSIA_QUERY_PATH = '/weaviate/elysia/query'
const ELYSIA_TOOLS_PATH = '/weaviate/elysia/tools'

const fetchWithTimeout = async (url: string, options: RequestInit = {}) => {
  const controller = new AbortController()
  const timeoutMs = API_CONFIG.TIMEOUT ?? 30000
  const timeoutId: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (error) {
    const errorName = (error as { name?: string })?.name

    if (errorName === 'AbortError') {
      throw new Error(`Elysia request timed out after ${Math.ceil(timeoutMs / 1000)}s`)
    }
    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

const parseResponse = async <T>(response: Response, defaultErrorPrefix: string): Promise<T> => {
  const rawPayload = await response.text()
  let data: any = null

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
        : data?.detail || data?.message || data?.error || ''
    const message = detail
      ? `${defaultErrorPrefix}: ${detail}`
      : `${defaultErrorPrefix} (status ${response.status})`
    throw new Error(message)
  }

  return data as T
}

export function useElysiaService() {
  const { getToken } = useAuth()
  const apiBase = BASE_API_URL

  const queryElysia = useCallback(async (query: ElysiaQuery): Promise<ElysiaResponse> => {
    const token = await getToken()

    const response = await fetchWithTimeout(`${apiBase}${ELYSIA_QUERY_PATH}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token || ''}`
      },
      body: JSON.stringify(query)
    })

    return await parseResponse<ElysiaResponse>(response, 'Elysia query failed')
  }, [getToken, apiBase])

  const getAvailableAgents = useCallback(async (): Promise<ElysiaAgent[]> => {
    try {
      const token = await getToken()
      const response = await fetchWithTimeout(`${apiBase}${ELYSIA_TOOLS_PATH}`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      })

      const data = await parseResponse<{ tools?: ElysiaAgent[] }>(
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
      console.error('Error getting Elysia agents:', error)
      return []
    }
  }, [getToken, apiBase])

  const sendMessage = useCallback(async (
    message: string,
    sessionId: string,
    tenantId: string,
    enableDebug: boolean = false,
    context?: Record<string, any>
  ): Promise<ElysiaResponse> => {
    return queryElysia({
      query: message,
      session_id: sessionId,
      tenant_id: tenantId,
      enable_debug: enableDebug,
      context
    })
  }, [queryElysia])

  const getWelcomeMessage = useCallback(async (sessionId: string, tenantId: string): Promise<ElysiaResponse> => {
    return queryElysia({
      query: "Genera un mensaje de bienvenida personalizado para el usuario",
      session_id: sessionId,
      tenant_id: tenantId,
      context: { is_welcome: true }
    })
  }, [queryElysia])

  return useMemo(() => ({
    queryElysia,
    getAvailableAgents,
    sendMessage,
    getWelcomeMessage
  }), [queryElysia, getAvailableAgents, sendMessage, getWelcomeMessage])
}
