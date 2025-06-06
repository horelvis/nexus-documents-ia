'use client'

import { useState, useCallback, useRef } from 'react'
import { ChatMessage, ChatRequest, StreamingEvent, agentsService } from '@/lib/services/agents.service'

export interface UseAgentChatOptions {
  agentId: string
  onMessage?: (message: ChatMessage) => void
  onError?: (error: string) => void
  onStreamEnd?: () => void
}

export function useAgentChat({ agentId, onMessage, onError, onStreamEnd }: UseAgentChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const addMessage = useCallback((message: ChatMessage) => {
    setMessages(prev => [...prev, message])
    onMessage?.(message)
  }, [onMessage])

  const sendMessage = useCallback(async (content: string, context?: Record<string, any>) => {
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

    } catch (error) {
      console.error('Error sending message:', error)
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content: 'Lo siento, ocurrió un error al procesar tu mensaje.',
        timestamp: new Date().toISOString(),
        metadata: { error: true }
      }
      addMessage(errorMessage)
      onError?.(error instanceof Error ? error.message : 'Unknown error')
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
    }
  }, [agentId, conversationId, addMessage, onError])

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
    isLoading,
    isStreaming,
    conversationId,
    sendMessage,
    sendMessageStreaming,
    clearChat,
    stopStreaming
  }
}