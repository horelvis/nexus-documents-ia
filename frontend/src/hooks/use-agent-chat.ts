'use client'

import { useState, useCallback, useRef } from 'react'
import { ChatMessage, ChatRequest, StreamingEvent, useAgentsService } from '@/lib/services/agents.service'

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
      // Create EventSource for streaming
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const streamUrl = `${apiUrl}/api/v1/agents/${agentId}/chat/stream`
      
      eventSourceRef.current = new EventSource(streamUrl)
      
      // Handle incoming messages
      let assistantMessage = ''
      let messageMetadata: Record<string, any> = {}

      eventSourceRef.current.onmessage = (event) => {
        try {
          const data: StreamingEvent = JSON.parse(event.data)
          
          switch (data.type) {
            case 'conversation_id':
              setConversationId(data.content)
              break
              
            case 'thinking':
            case 'reasoning':
            case 'planning':
            case 'observation':
            case 'conclusion':
              // Handle thinking events
              addThinkingEvent({
                type: data.type as ThinkingEvent['type'],
                content: data.content,
                metadata: data.metadata
              })
              break
              
            case 'message':
              assistantMessage += data.content
              // Update the last assistant message in real-time
              setMessages(prev => {
                const newMessages = [...prev]
                const lastIndex = newMessages.length - 1
                if (lastIndex >= 0 && newMessages[lastIndex].role === 'assistant') {
                  newMessages[lastIndex] = {
                    ...newMessages[lastIndex],
                    content: assistantMessage,
                    metadata: { ...messageMetadata, ...data.metadata }
                  }
                } else {
                  newMessages.push({
                    role: 'assistant',
                    content: assistantMessage,
                    timestamp: new Date().toISOString(),
                    metadata: data.metadata
                  })
                }
                return newMessages
              })
              break
              
            case 'completion':
              onStreamEnd?.()
              break
              
            case 'error':
              onError?.(data.content)
              break
          }
        } catch (error) {
          console.error('Error parsing SSE data:', error)
        }
      }

      eventSourceRef.current.onerror = (error) => {
        console.error('EventSource error:', error)
        onError?.('Connection error')
        eventSourceRef.current?.close()
      }

      // Send the initial request to start the stream
      const request: ChatRequest = {
        message: content,
        conversation_id: conversationId || undefined,
        context
      }

      // This would need to be implemented differently in a real app
      // For now, we'll fallback to regular API
      await sendMessage(content, context)

    } catch (error) {
      console.error('Error in streaming chat:', error)
      onError?.(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
    }
  }, [agentId, conversationId, addMessage, onError, onStreamEnd, sendMessage])

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