import { useMemo } from 'react'
import { useApiClient } from '@/lib/api-client'

export interface Agent {
  id: string
  name: string
  description?: string
  agent_type: 'generic' | 'document_analyzer' | 'digital_signature' | 'rag_assistant' | 'contract_analyzer' | 'financial_analyzer' | 'legal_compliance'
  tenant_id: string
  created_by: string
  created_at: string
  updated_at: string
  status: 'inactive' | 'active' | 'busy' | 'error'
  last_activity?: string
  configuration: Record<string, any>
  is_active: boolean
  capabilities?: string[]
}

export interface AgentStats {
  total_agents: number
  active_agents: number
  total_conversations: number
  total_messages: number
  agents_by_type: Record<string, number>
  recent_activity: Array<{
    agent_id: string
    agent_name: string
    action: string
    timestamp: string
    status: 'success' | 'error' | 'info'
  }>
}

export interface AgentHealth {
  status: string
  message: string
  service_name?: string
  version?: string
  uptime?: number
}

export interface AgentServiceStatus {
  langgraph_service: {
    status: string
    graphs_loaded: number
    active_sessions: number
  }
  system_resources: {
    cpu_percent: number
    memory_percent: number
    disk_percent: number
  }
  graph_stats: {
    total_graphs: number
    active_graphs: number
    graphs_by_type: Record<string, number>
  }
}

export interface CreateAgentRequest {
  name: string
  description?: string
  agent_type: Agent['agent_type']
  configuration?: Record<string, any>
}

export interface ChatMessage {
  content: string
  role: 'user' | 'assistant' | 'system'
  timestamp?: string
}

class AgentService {
  constructor(private apiClient: ReturnType<typeof useApiClient>) {}

  async getAgents(): Promise<{ data?: Agent[]; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/list')
      
      // Handle the nested structure from the API
      if (response.data && typeof response.data === 'object' && 'agents' in response.data) {
        return { data: response.data.agents }
      }
      
      // Fallback to direct array if API changes
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agents:', error)
      return { error: error.message || 'Failed to fetch agents' }
    }
  }

  async createAgent(data: CreateAgentRequest): Promise<{ data?: Agent; error?: string }> {
    try {
      const response = await this.apiClient.post('/agents/create', data)
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to create agent:', error)
      return { error: error.message || 'Failed to create agent' }
    }
  }

  async deleteAgent(agentId: string): Promise<{ success?: boolean; error?: string }> {
    try {
      await this.apiClient.delete(`/agents/${agentId}`)
      return { success: true }
    } catch (error: any) {
      console.error('Failed to delete agent:', error)
      return { error: error.message || 'Failed to delete agent' }
    }
  }

  async getAgentHealth(): Promise<{ data?: AgentHealth; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/health')
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent health:', error)
      return { error: error.message || 'Failed to fetch agent health' }
    }
  }

  async getAgentStatus(): Promise<{ data?: AgentServiceStatus; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/status')
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent status:', error)
      return { error: error.message || 'Failed to fetch agent status' }
    }
  }

  async chatWithAgent(
    agentId: string,
    message: string,
    onMessage?: (chunk: string) => void,
    onComplete?: () => void
  ): Promise<{ error?: string }> {
    try {
      const response = await this.apiClient.fetchRaw(`/agents/${agentId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              if (onComplete) onComplete()
              return {}
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.content && onMessage) {
                onMessage(parsed.content)
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }

      return {}
    } catch (error: any) {
      console.error('Failed to chat with agent:', error)
      return { error: error.message || 'Failed to chat with agent' }
    }
  }

  async executeTask(
    agentId: string,
    task: string,
    documentIds?: string[],
    onMessage?: (chunk: string) => void,
    onComplete?: () => void
  ): Promise<{ error?: string }> {
    try {
      const response = await this.apiClient.fetchRaw(`/agents/${agentId}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ task, document_ids: documentIds })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              if (onComplete) onComplete()
              return {}
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.content && onMessage) {
                onMessage(parsed.content)
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }

      return {}
    } catch (error: any) {
      console.error('Failed to execute task:', error)
      return { error: error.message || 'Failed to execute task' }
    }
  }

  async getAgentStats(agentId: string): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get(`/agents/${agentId}/stats`)
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent stats:', error)
      return { error: error.message || 'Failed to fetch agent stats' }
    }
  }

  async getAgentActivity(limit: number = 10): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get(`/agents/activity?limit=${limit}`)
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent activity:', error)
      return { error: error.message || 'Failed to fetch agent activity' }
    }
  }

  async analyzeDocument(
    documentId: string,
    documentType: string,
    onProgress?: (event: any) => void,
    onResult?: (result: any) => void,
    onError?: (error: string) => void
  ): Promise<{ error?: string }> {
    try {
      const response = await this.apiClient.fetchRaw('/agents/document/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          document_content: documentId, // For now, just pass ID
          analysis_type: documentType
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No response body')
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              return {}
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.type === 'progress' && onProgress) {
                onProgress(parsed)
              } else if (parsed.type === 'result' && onResult) {
                onResult(parsed.content)
              } else if (parsed.type === 'error' && onError) {
                onError(parsed.content)
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e)
            }
          }
        }
      }

      return {}
    } catch (error: any) {
      console.error('Failed to analyze document:', error)
      if (onError) onError(error.message)
      return { error: error.message || 'Failed to analyze document' }
    }
  }

  async getDocumentAgents(documentId: string): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get(`/documents/${documentId}/agents`)
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch document agents:', error)
      return { error: error.message || 'Failed to fetch document agents' }
    }
  }

  // Helper function to get agent type metadata
  getAgentMetadata(agentType: Agent['agent_type']) {
    const metadata: Record<Agent['agent_type'], {
      icon: string
      color: string
      description: string
      capabilities: string[]
    }> = {
      generic: {
        icon: '🤖',
        color: 'bg-gray-500',
        description: 'General purpose AI assistant',
        capabilities: ['general_qa', 'text_generation']
      },
      document_analyzer: {
        icon: '📄',
        color: 'bg-blue-500',
        description: 'Analyzes document content and structure',
        capabilities: ['content_analysis', 'extraction', 'summarization']
      },
      digital_signature: {
        icon: '✍️',
        color: 'bg-purple-500',
        description: 'Manages digital signature workflows',
        capabilities: ['signature_requests', 'status_tracking', 'signer_management']
      },
      rag_assistant: {
        icon: '🔍',
        color: 'bg-green-500',
        description: 'Retrieval-augmented generation for Q&A',
        capabilities: ['document_search', 'context_qa', 'knowledge_retrieval']
      },
      contract_analyzer: {
        icon: '📑',
        color: 'bg-orange-500',
        description: 'Analyzes contracts and legal documents',
        capabilities: ['clause_extraction', 'risk_assessment', 'compliance_check']
      },
      financial_analyzer: {
        icon: '💰',
        color: 'bg-yellow-500',
        description: 'Financial document analysis',
        capabilities: ['financial_metrics', 'trend_analysis', 'report_generation']
      },
      legal_compliance: {
        icon: '⚖️',
        color: 'bg-red-500',
        description: 'Legal compliance and regulatory analysis',
        capabilities: ['compliance_check', 'risk_assessment', 'regulatory_analysis']
      }
    }
    
    return metadata[agentType] || metadata.generic
  }
}

// Hook to use the agent service with authentication
export function useAgentService() {
  const apiClient = useApiClient()
  return useMemo(() => new AgentService(apiClient), [apiClient])
}