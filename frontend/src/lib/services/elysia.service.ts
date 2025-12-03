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

export function useElysiaService() {
  const { getToken } = useAuth()

  const queryElysia = useCallback(async (query: ElysiaQuery): Promise<ElysiaResponse> => {
    const token = await getToken()

    const response = await fetch(`/api/v1/weaviate/elysia/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token || ''}`
      },
      body: JSON.stringify(query)
    })

    if (!response.ok) {
      throw new Error(`Elysia query failed: ${response.status}`)
    }

    return await response.json()
  }, [getToken])

  const getAvailableAgents = useCallback(async (): Promise<ElysiaAgent[]> => {
    try {
      const token = await getToken()
      const response = await fetch(`/api/v1/weaviate/elysia/tools`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      })

      if (!response.ok) {
        throw new Error(`Failed to get agents: ${response.status}`)
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
  }, [getToken])

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