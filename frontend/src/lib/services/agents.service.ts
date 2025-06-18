import { useMemo } from 'react'
import { useApiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'

export interface Agent {
  id: string
  name: string
  description: string
  type: string
  icon?: string
  configuration?: Record<string, any>
  tools?: string[]
  is_active?: boolean
  is_public?: boolean
  created_at?: string
  updated_at?: string
  created_by?: string
  source?: 'built-in' | 'dynamic'
  capabilities?: string[]
  ui_config?: {
    icon?: string
    color?: string
    quick_actions?: string[]
  }
}

export interface ChatMessage {
  id?: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  metadata?: Record<string, any>
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  context?: Record<string, any>
}

export interface AgentExecutionRequest {
  task_type: string
  parameters: Record<string, any>
  context?: Record<string, any>
}

export interface StreamingEvent {
  type: string
  content: string
  metadata?: Record<string, any>
  timestamp: string
  execution_id?: string
}

export class AgentsService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async getAgents() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/list`)
    return response
  }

  async getAgentTypes() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/types`)
    return response
  }

  async getAgent(agentId: string) {
    const response = await this.apiClient.get<Agent>(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}`)
    return response
  }

  async createAgent(agentData: Partial<Agent>) {
    const response = await this.apiClient.post<Agent>(API_CONFIG.ENDPOINTS.AGENTS, agentData)
    return response
  }

  async chatWithAgent(agentId: string, request: ChatRequest) {
    try {
      // The backend returns a streaming response, so we need to handle it differently
      const response = await this.streamChat(agentId, request)
      return response
    } catch (error) {
      // Re-throw the error to preserve the response structure
      throw error
    }
  }

  private async streamChat(agentId: string, request: ChatRequest): Promise<any> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const token = await this.apiClient.getAuthToken()
    
    const response = await fetch(`${apiUrl}/api/v1/agents/${agentId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(request)
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw { response: { status: response.status, data: errorData } }
    }

    // Read the streaming response
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let fullMessage = ''
    let metadata = {}
    let conversation_id = null
    let buffer = ''

    if (reader) {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // Decode the chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })
        
        // Process complete lines
        const lines = buffer.split('\n')
        
        // Keep the last line in buffer if it's incomplete
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.trim() === '') continue
          
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6).trim()
            if (jsonStr === '[DONE]') continue
            
            try {
              const data = JSON.parse(jsonStr)
              
              if (data.type === 'message') {
                fullMessage += data.content
                metadata = { ...metadata, ...data.metadata }
              } else if (data.type === 'conversation_id') {
                conversation_id = data.content
              } else if (data.type === 'error') {
                console.error('Agent error:', data.content)
              }
              // Log other event types for debugging
              console.log('SSE Event:', data.type, data)
            } catch (e) {
              console.error('Error parsing SSE data:', e, 'Line:', jsonStr)
            }
          }
        }
      }
      
      // Process any remaining data in buffer
      if (buffer.trim() && buffer.startsWith('data: ')) {
        const jsonStr = buffer.slice(6).trim()
        try {
          const data = JSON.parse(jsonStr)
          if (data.type === 'message') {
            fullMessage += data.content
            metadata = { ...metadata, ...data.metadata }
          }
        } catch (e) {
          console.error('Error parsing final SSE data:', e)
        }
      }
    }

    return {
      message: fullMessage || 'No response received',
      metadata,
      conversation_id
    }
  }

  // Streaming chat using EventSource
  createChatStream(agentId: string, request: ChatRequest): EventSource {
    const params = new URLSearchParams()
    const url = `/api/v1/agents/${agentId}/chat/stream`
    
    // Create EventSource for streaming
    const eventSource = new EventSource(url, {
      // Add headers if needed for authentication
    })
    
    // Send the chat request via POST first
    this.initiateChatStream(agentId, request)
    
    return eventSource
  }

  private async initiateChatStream(agentId: string, request: ChatRequest) {
    // This would typically be handled differently in a real implementation
    // For now, we'll use the regular endpoint
    await this.apiClient.post(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}/chat/stream`, request)
  }

  async executeAgent(agentId: string, request: AgentExecutionRequest) {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}/execute`, request)
    return response
  }

  // Streaming execution
  createExecutionStream(agentId: string, request: AgentExecutionRequest): EventSource {
    const url = `/api/v1/agents/${agentId}/execute/stream`
    
    const eventSource = new EventSource(url)
    
    // Initiate execution
    this.initiateExecutionStream(agentId, request)
    
    return eventSource
  }

  private async initiateExecutionStream(agentId: string, request: AgentExecutionRequest) {
    await this.apiClient.post(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}/execute/stream`, request)
  }

  // Health check for LangGraph integration
  async checkLangGraphHealth() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/health`)
    return response
  }

  // Test LangGraph integration
  async testLangGraphAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/test`)
    return response
  }

  // Get service status
  async getServiceStatus() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/status`)
    return response
  }

  // Create specific agent types
  async createDigitalSignatureAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/create`, {
      agent_type: 'digital_signature',
      configuration: {}
    })
    return response
  }

  async createDocumentAnalyzerAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/create`, {
      agent_type: 'document_analyzer', 
      configuration: {}
    })
    return response
  }

  async createRAGAssistantAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/create`, {
      agent_type: 'rag_assistant',
      configuration: {}
    })
    return response
  }

  async createLegalComplianceAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/create`, {
      agent_type: 'legal_compliance',
      configuration: {}
    })
    return response
  }

  async createFinancialAnalysisAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/create`, {
      agent_type: 'financial_analysis',
      configuration: {}
    })
    return response
  }

  // Get conversation history
  async getConversations(agentId?: string) {
    const params = agentId ? `?agent_id=${agentId}` : ''
    const response = await this.apiClient.get<any[]>(`${API_CONFIG.ENDPOINTS.AGENTS}/conversations${params}`)
    return response
  }

  // Create new conversation
  async createConversation(agentId: string, title?: string) {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}/conversations`, {
      agent_id: agentId,
      title: title || `Chat - ${new Date().toLocaleDateString()}`
    })
    return response
  }
}

// Hook para usar el servicio de agentes
export function useAgentsService() {
  const apiClient = useApiClient()
  return useMemo(() => new AgentsService(apiClient), [apiClient])
}