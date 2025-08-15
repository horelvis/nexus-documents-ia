import { useMemo } from 'react'
import { useApiClient } from '@/lib/api-client'

export interface Agent {
  id: string
  name: string
  description?: string
  agent_type: 'virtual_assistant' | 'search_specialist' | 'document_analyst' | 'compliance_expert' | 'communication_specialist' | 'workflow_coordinator' | 'generic' | 'document_analyzer' | 'digital_signature' | 'rag_assistant' | 'contract_analyzer' | 'financial_analyzer' | 'legal_compliance'
  tenant_id?: string
  created_by?: string
  created_at?: string
  updated_at?: string
  status: 'inactive' | 'active' | 'busy' | 'error' | 'idle'
  last_activity?: string
  configuration?: Record<string, any>
  is_active?: boolean
  capabilities?: string[]
  source?: string
  role?: string
  goal?: string
  tools?: string[]
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
  service: string
  status: string
  cag_health?: {
    status: string
    agents_count?: number
    crews_running?: number
    system_resources?: {
      cpu_percent: number
      memory_percent: number
      disk_percent: number
    }
  }
  agents_available?: number
  crews_running?: number
  system_resources?: {
    cpu_percent: number
    memory_percent: number
    disk_percent: number
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

  async getAgents(): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/list')
      
      // The /agents/list endpoint returns available_types from the CrewAI integration
      // Return the full response data to let components handle the structure
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agents:', error)
      return { error: error.message || 'Failed to fetch agents' }
    }
  }

  async createAgent(data: CreateAgentRequest): Promise<{ data?: any; error?: string }> {
    try {
      const requestData = {
        name: data.name,
        role: data.name, // Use name as role for CrewAI
        goal: `Be a helpful ${data.agent_type} assistant`,
        backstory: data.description || `I am a specialized ${data.agent_type} agent.`,
        tools: [],
        configuration: data.configuration || {}
      }
      const response = await this.apiClient.post('/agents/create', requestData)
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
        body: JSON.stringify({ 
          task_description: task, 
          expected_output: 'Detailed analysis and results',
          agent_roles: [agentId],
          context: { document_ids: documentIds || [] }
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

  async getAgentStatistics(): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/statistics')
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent statistics:', error)
      return { error: error.message || 'Failed to fetch agent statistics' }
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

      let buffer = ''

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
            const data = line.slice(6).trim()
            if (data === '[DONE]') {
              return {}
            }
            
            if (data) {
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
                console.error('Failed to parse SSE data:', e, 'Data:', data)
              }
            }
          }
        }
      }

      // Process any remaining data in buffer
      if (buffer.trim() && buffer.startsWith('data: ')) {
        const data = buffer.slice(6).trim()
        if (data && data !== '[DONE]') {
          try {
            const parsed = JSON.parse(data)
            if (parsed.type === 'result' && onResult) {
              onResult(parsed.content)
            }
          } catch (e) {
            console.error('Failed to parse final SSE data:', e)
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

  // Get agent types from API - NO HARDCODING
  async getAgentTypes(): Promise<{ data?: any; error?: string }> {
    try {
      const response = await this.apiClient.get('/agents/types')
      return { data: response.data }
    } catch (error: any) {
      console.error('Failed to fetch agent types:', error)
      return { error: error.message || 'Failed to fetch agent types' }
    }
  }
}

// Hook to use the agent service with authentication
export function useAgentService() {
  const apiClient = useApiClient()
  return useMemo(() => new AgentService(apiClient), [apiClient])
}