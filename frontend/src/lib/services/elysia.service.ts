import { useAuth } from '@clerk/nextjs'
import { API_CONFIG } from '../config'

export interface ElysiaQuery {
  query: string
  session_id: string
  tenant_id: string
  context?: Record<string, any>
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

  /**
   * Query Elysia agents directly - they auto-select based on query
   */
  async function queryElysia(query: ElysiaQuery): Promise<ElysiaResponse> {
    const token = await getToken()
    
    // Direct call to weaviate-service:8007
    const response = await fetch(`${API_CONFIG.WEAVIATE_SERVICE_URL}/elysia/query`, {
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
  }

  /**
   * Get available Elysia tools/agents
   */
  async function getAvailableAgents(): Promise<ElysiaAgent[]> {
    try {
      const token = await getToken()
      const response = await fetch(`${API_CONFIG.WEAVIATE_SERVICE_URL}/elysia/tools`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`
        }
      })

      if (!response.ok) {
        throw new Error(`Failed to get agents: ${response.status}`)
      }

      const data = await response.json()
      
      // Convert tools to agent format
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
  }

  /**
   * Send message to Elysia with automatic agent selection
   */
  async function sendMessage(
    message: string, 
    sessionId: string,
    tenantId: string,
    context?: Record<string, any>
  ): Promise<ElysiaResponse> {
    return queryElysia({
      query: message,
      session_id: sessionId,
      tenant_id: tenantId,
      context
    })
  }

  /**
   * Get welcome message using Elysia
   */
  async function getWelcomeMessage(sessionId: string, tenantId: string): Promise<ElysiaResponse> {
    return queryElysia({
      query: "Genera un mensaje de bienvenida personalizado para el usuario",
      session_id: sessionId,
      tenant_id: tenantId,
      context: { is_welcome: true }
    })
  }

  return {
    queryElysia,
    getAvailableAgents,
    sendMessage,
    getWelcomeMessage
  }
}