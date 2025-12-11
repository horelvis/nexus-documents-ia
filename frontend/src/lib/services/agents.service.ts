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
    // Redirect chat flow to Emma (semantic-router + memory) instead of legacy agents
    const payload = {
      query: request.message,
      session_id: request.conversation_id,
      context: request.context ?? {},
    }

    // Tenant/user resolution happens server-side (gateway injects tenant_id)
    const response = await this.apiClient.post<any>(
      API_CONFIG.ENDPOINTS.EMMA_QUERY,
      payload,
      { timeoutMs: API_CONFIG.EMMA_TIMEOUT }
    )

    const data = (response as any)?.data ?? response

    return {
      message: data?.answer || data?.response || '',
      metadata: {
        decision_path: data?.decision_path,
        tools_used: data?.tools_used,
        suggestions: data?.suggestions,
        confidence: data?.confidence_score,
      },
      conversation_id: data?.session_id,
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

  // Health check for CAG integration
  async checkCAGHealth() {
    const response = await this.apiClient.get<any>(`${API_CONFIG.ENDPOINTS.AGENTS}/health`)
    return response
  }

  // Test CAG integration
  async testCAGAgent() {
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
