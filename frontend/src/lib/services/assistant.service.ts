import { apiClient } from '../api-client'
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

export const assistantService = {
  /**
   * Get personalized welcome message from CrewAI
   */
  async getWelcomeMessage(): Promise<WelcomeResponse> {
    try {
      const response = await apiClient.get<WelcomeResponse>(
        `${API_CONFIG.ENDPOINTS.ASSISTANT_WELCOME}`
      )
      return response
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
    return apiClient.post<ChatResponse>(
      `${API_CONFIG.ENDPOINTS.ASSISTANT_CHAT}`,
      message
    )
  },

  /**
   * Get conversation history
   */
  async getConversation(conversationId: string): Promise<any> {
    return apiClient.get(
      `${API_CONFIG.ENDPOINTS.ASSISTANT_CONVERSATION(conversationId)}`
    )
  },

  /**
   * Clear conversation
   */
  async clearConversation(conversationId: string): Promise<any> {
    return apiClient.delete(
      `${API_CONFIG.ENDPOINTS.ASSISTANT_CONVERSATION(conversationId)}`
    )
  }
}