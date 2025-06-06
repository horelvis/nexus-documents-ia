import { apiClient } from '@/lib/api-client'

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
  private static instance: AgentsService
  
  public static getInstance(): AgentsService {
    if (!AgentsService.instance) {
      AgentsService.instance = new AgentsService()
    }
    return AgentsService.instance
  }

  async getAgents(): Promise<Agent[]> {
    const response = await apiClient.get('/agents/')
    return response.data
  }

  async getAgent(agentId: string): Promise<Agent> {
    const response = await apiClient.get(`/agents/${agentId}`)
    return response.data
  }

  async createAgent(agentData: Partial<Agent>): Promise<Agent> {
    const response = await apiClient.post('/agents/', agentData)
    return response.data
  }

  async chatWithAgent(agentId: string, request: ChatRequest): Promise<any> {
    const response = await apiClient.post(`/agents/${agentId}/chat`, request)
    return response.data
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
    await apiClient.post(`/agents/${agentId}/chat/stream`, request)
  }

  async executeAgent(agentId: string, request: AgentExecutionRequest): Promise<any> {
    const response = await apiClient.post(`/agents/${agentId}/execute`, request)
    return response.data
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
    await apiClient.post(`/agents/${agentId}/execute/stream`, request)
  }

  // Health check for Langroid integration
  async checkLangroidHealth(): Promise<any> {
    const response = await apiClient.get('/agents/langroid/health')
    return response.data
  }

  // Test Langroid integration
  async testLangroidAgent(): Promise<any> {
    const response = await apiClient.post('/agents/langroid/test-agent')
    return response.data
  }

  // Get conversation history
  async getConversations(agentId?: string): Promise<any[]> {
    const params = agentId ? { agent_id: agentId } : {}
    const response = await apiClient.get('/agents/conversations', { params })
    return response.data
  }

  // Create new conversation
  async createConversation(agentId: string, title?: string): Promise<any> {
    const response = await apiClient.post(`/agents/${agentId}/conversations`, {
      agent_id: agentId,
      title: title || `Chat - ${new Date().toLocaleDateString()}`
    })
    return response.data
  }
}

export const agentsService = AgentsService.getInstance()