import { useMemo } from 'react'
import { useApiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'

export interface Agent {
  id: string
  name: string
  description: string
  type: string
  configuration: Record<string, any>
  tools: string[]
  is_active: boolean
  is_public: boolean
  created_at: string
  updated_at: string
  created_by: string
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
    const response = await this.apiClient.get<Agent[]>(API_CONFIG.ENDPOINTS.AGENTS)
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
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/${agentId}/chat`, request)
    return response
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

  // Health check for Langroid integration
  async checkLangroidHealth() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/langroid/health`)
    return response
  }

  // Test Langroid integration
  async testLangroidAgent() {
    const response = await this.apiClient.post<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/langroid/test-agent`)
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