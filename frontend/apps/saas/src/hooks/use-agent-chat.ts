'use client'

import { useState, useCallback, useRef } from 'react'
import { ChatMessage, ChatRequest, useAgentsService } from '@/lib/services/agents.service'

export interface ThinkingEvent {
  type: 'thinking' | 'reasoning' | 'planning' | 'observation' | 'conclusion'
  content: string
  metadata?: Record<string, any>
}

export interface UseAgentChatOptions {
  agentId: string
  onMessage?: (message: ChatMessage) => void
  onError?: (error: string) => void
  onStreamEnd?: () => void
  onThinkingEvent?: (event: ThinkingEvent) => void
}

export function useAgentChat({ agentId, onMessage, onError, onStreamEnd, onThinkingEvent }: UseAgentChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [thinkingEvents, setThinkingEvents] = useState<ThinkingEvent[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const agentsService = useAgentsService()

  const addMessage = useCallback((message: ChatMessage) => {
    setMessages(prev => [...prev, message])
    onMessage?.(message)
  }, [onMessage])

  const addThinkingEvent = useCallback((event: ThinkingEvent) => {
    setThinkingEvents(prev => [...prev, event])
    onThinkingEvent?.(event)
  }, [onThinkingEvent])

  const sendMessage = useCallback(async (content: string, context?: Record<string, any>) => {
    if (!content.trim()) return
    
    // Prevent duplicate messages in development (React StrictMode)
    if (messages.length > 0 && messages[messages.length - 1].content === content && messages[messages.length - 1].role === 'user') {
      console.log('Duplicate message detected, skipping')
      return
    }

    // Clear thinking events for new message
    setThinkingEvents([])

    // Add user message immediately
    const userMessage: ChatMessage = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    }
    addMessage(userMessage)

    setIsLoading(true)
    setIsStreaming(true)

    try {
      // For streaming chat, we'll use a different approach
      // Since EventSource with POST is complex, we'll simulate streaming with regular API
      const request: ChatRequest = {
        message: content,
        conversation_id: conversationId || undefined,
        context
      }

      const response = await agentsService.chatWithAgent(agentId, request)
      
      // Add assistant response
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.message || 'No response received',
        timestamp: new Date().toISOString(),
        metadata: response.metadata
      }
      addMessage(assistantMessage)

      // Update conversation ID if received
      if (response.conversation_id) {
        setConversationId(response.conversation_id)
      }

    } catch (error: any) {
      console.error('Error sending message:', error)
      console.log('Error structure:', {
        hasResponse: !!error?.response,
        status: error?.response?.status,
        hasDetail: !!error?.response?.data?.detail,
        detail: error?.response?.data?.detail
      })
      
      // Check if it's a subscription error (403)
      if (error?.response?.status === 403 && error?.response?.data?.detail) {
        console.log('Subscription error detected, showing dialog')
        // Pass the full error detail to the error handler
        onError?.(JSON.stringify({
          type: 'subscription_error',
          detail: error.response.data.detail
        }))
        
        // Add a custom error message to the chat
        const errorMessage: ChatMessage = {
          role: 'assistant',
          content: 'Esta función requiere una suscripción activa. Por favor, actualiza tu plan para acceder a los agentes AI.',
          timestamp: new Date().toISOString(),
          metadata: { error: true, errorType: 'subscription' }
        }
        addMessage(errorMessage)
      } else {
        // Handle other errors with transparency
        const errorMessage: ChatMessage = {
          role: 'assistant',
          content: `🔥 Error del agente: ${error?.message || 'Servicio de agentes no disponible'}. Estado del sistema: Fallo real.`,
          timestamp: new Date().toISOString(),
          metadata: { error: true, errorDetails: error?.message }
        }
        addMessage(errorMessage)
        onError?.(error?.message || 'Unknown error')
      }
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
    }
  }, [agentId, conversationId, addMessage, onError, agentsService, messages])

  const sendMessageStreaming = useCallback(async (content: string, context?: Record<string, any>) => {
    if (!content.trim()) return

    // Add user message immediately
    const userMessage: ChatMessage = {
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    }
    addMessage(userMessage)

    setIsLoading(true)
    setIsStreaming(true)

    try {
      // For now, reuse non-streaming flow against Emma endpoint
      await sendMessage(content, context)
      onStreamEnd?.()
    } catch (error) {
      console.error('Error in streaming chat:', error)
      onError?.(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
    }
  }, [addMessage, onError, onStreamEnd, sendMessage])

  const clearChat = useCallback(() => {
    setMessages([])
    setConversationId(null)
  }, [])

  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsStreaming(false)
    setIsLoading(false)
  }, [])

  return {
    messages,
    thinkingEvents,
    isLoading,
    isStreaming,
    conversationId,
    sendMessage,
    sendMessageStreaming,
    clearChat,
    stopStreaming
  }
}
