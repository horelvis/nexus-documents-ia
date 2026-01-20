import { useApiClient } from '../api-client'
import { API_CONFIG } from '../config'

export interface WelcomeResponse {
  message: string
  personalized: boolean
  stats?: {
    documents: number
    pending_signatures: number
  }
}

export interface ChatMessage {
  message: string
  conversation_id?: string
  context?: Record<string, any>
  stream?: boolean
}

export interface ChatResponse {
  response: string
  conversation_id: string
  actions_taken: Array<Record<string, any>>
  suggestions: string[]
  confidence: number
  metadata?: Record<string, any>
  requires_confirmation: boolean
}

export function useAssistantService() {
  const apiClient = useApiClient()

  return {
    /**
     * Get personalized welcome message from CrewAI
     */
    async getWelcomeMessage(): Promise<WelcomeResponse> {
      try {
        const response = await apiClient.get<WelcomeResponse>(
          `${API_CONFIG.ENDPOINTS.ASSISTANT_WELCOME}`
        )
        return response.data || {
          message: "¡Estoy aquí para ayudarte!",
          personalized: false
        }
      } catch (error) {
        console.error('Error fetching welcome message:', error)
        // Fallback to default message
        return {
          message: "¡Estoy aquí para ayudarte!",
          personalized: false
        }
      }
    },

    /**
     * Send chat message to assistant
     */
    async sendChatMessage(message: ChatMessage): Promise<ChatResponse> {
      const response = await apiClient.post<ChatResponse>(
        `${API_CONFIG.ENDPOINTS.ASSISTANT_CHAT}`,
        message
      )
      return response.data
    },

    /**
     * Get conversation history
     */
    async getConversation(conversationId: string): Promise<any> {
      const response = await apiClient.get(
        `${API_CONFIG.ENDPOINTS.ASSISTANT_CONVERSATION(conversationId)}`
      )
      return response.data
    },

    /**
     * Clear conversation
     */
    async clearConversation(conversationId: string): Promise<any> {
      const response = await apiClient.delete(
        `${API_CONFIG.ENDPOINTS.ASSISTANT_CONVERSATION(conversationId)}`
      )
      return response.data
    }
  }
}

// Legacy export for backward compatibility - DO NOT USE (no authentication)
export const assistantService = {
  async getWelcomeMessage(): Promise<WelcomeResponse> {
    console.warn('⚠️ assistantService.getWelcomeMessage() is deprecated and lacks authentication. Use useAssistantService() hook instead.')
    return {
      message: "¡Estoy aquí para ayudarte!",
      personalized: false
    }
  }
}