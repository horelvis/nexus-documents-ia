"use client"

import { createContext, useContext, useState, useCallback, ReactNode, useRef } from "react"
import { useBackendUser } from "./user-context"
import { useApiClient } from "@/lib/api-client"
import { useAuth } from "@clerk/nextjs"
import { useAuthToken } from "@/hooks/use-auth-token"

interface Message {
  id: string
  content: string
  role: "user" | "assistant"
  timestamp: Date
  metadata?: Record<string, any>
  actions?: Array<{
    action: string
    success: boolean
    result?: any
  }>
  suggestions?: string[]
  confidence?: number
  isStreaming?: boolean
}

interface Conversation {
  id: string
  messages: Message[]
  createdAt: Date
  updatedAt: Date
}

interface VirtualAssistantContextType {
  // State
  conversations: Conversation[]
  currentConversation: Conversation | null
  isLoading: boolean
  isStreaming: boolean
  error: string | null
  
  // Actions
  sendMessage: (content: string, useStreaming?: boolean) => Promise<void>
  clearConversation: () => void
  loadConversation: (id: string) => Promise<void>
  createNewConversation: () => void
  loadWelcomeMessage: () => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  stopStreaming: () => void
}

const VirtualAssistantContext = createContext<VirtualAssistantContextType | undefined>(undefined)

export function VirtualAssistantProvider({ children }: { children: ReactNode }) {
  const currentUser = useBackendUser()
  const apiClient = useApiClient()
  const { getToken } = useAuth()
  const { getValidToken, invalidateToken } = useAuthToken()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const createNewConversation = useCallback(() => {
    console.log("Creating new conversation in context...")
    const newConversation: Conversation = {
      id: Date.now().toString(),
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    }
    
    setCurrentConversation(newConversation)
    setConversations(prev => [newConversation, ...prev])
    console.log("New conversation created:", newConversation.id)
    
    // Don't fetch welcome message here - wait until chatbox actually opens
    // Just set empty conversation for now
  }, [])

  const loadWelcomeMessage = useCallback(async () => {
    if (!currentConversation || currentConversation.messages.length > 0) {
      // Don't load welcome if conversation already has messages
      return
    }
    
    setIsLoading(true)
    setError(null)
    
    try {
      const token = await getValidToken()
      console.log("Loading personalized welcome message...")
      console.log("User info:", { tenant_id: currentUser?.tenant_id, user_id: currentUser?.id })
      
      const response = await apiClient.post("/api/v1/assistant/v2/chat", {
        message: "SYSTEM: Generate a personalized welcome message for the user",
        conversation_id: currentConversation.id,
        context: {
          tenant_id: currentUser?.tenant_id,
          user_id: currentUser?.id,
          is_welcome: true
        }
      })
      
      console.log("Welcome response status:", response.status)
      
      if (response.error) {
        console.error("Welcome request failed:", response.status, response.error)
      }
      
      if (response.data) {
        const data = response.data
        console.log("Welcome response data:", data)
        console.log("Response content:", data.response)
        console.log("Suggestions:", data.suggestions)
        
        // Add the personalized welcome message
        const welcomeMessage: Message = {
          id: "welcome",
          content: data.response || "¡Hola! Soy tu asistente virtual inteligente. ¿En qué puedo ayudarte hoy?",
          role: "assistant",
          timestamp: new Date(),
          suggestions: data.suggestions || [
            "Buscar documentos recientes",
            "Ver estadísticas",
            "Analizar un documento",
            "Solicitar una firma"
          ],
          metadata: data.metadata,
          confidence: data.confidence
        }
        
        setCurrentConversation(prev => {
          if (!prev) return prev
          return {
            ...prev,
            messages: [welcomeMessage],
            updatedAt: new Date(),
          }
        })
      } else {
        // Fallback to default message if CAG fails
        const defaultMessage: Message = {
          id: "welcome",
          content: "¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?",
          role: "assistant",
          timestamp: new Date(),
          suggestions: [
            "Buscar documentos",
            "Ver estadísticas",
            "Analizar documento",
            "Gestionar firmas"
          ]
        }
        
        setCurrentConversation(prev => {
          if (!prev) return prev
          return {
            ...prev,
            messages: [defaultMessage],
            updatedAt: new Date(),
          }
        })
      }
    } catch (error) {
      console.error("Error getting welcome message:", error)
      // Use default message on error
      const defaultMessage: Message = {
        id: "welcome",
        content: "¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?",
        role: "assistant",
        timestamp: new Date(),
        suggestions: [
          "Buscar documentos",
          "Ver estadísticas",
          "Analizar documento",
          "Gestionar firmas"
        ]
      }
      
      setCurrentConversation(prev => {
        if (!prev) return prev
        return {
          ...prev,
          messages: [defaultMessage],
          updatedAt: new Date(),
        }
      })
    } finally {
      setIsLoading(false)
    }
  }, [currentConversation, currentUser, getValidToken, apiClient])

  const sendMessage = useCallback(async (content: string, useStreaming: boolean = true) => {
    if (!currentConversation || !currentUser) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      // Add user message
      const userMessage: Message = {
        id: Date.now().toString(),
        content,
        role: "user",
        timestamp: new Date(),
      }
      
      setCurrentConversation(prev => {
        if (!prev) return prev
        return {
          ...prev,
          messages: [...prev.messages, userMessage],
          updatedAt: new Date(),
        }
      })

      if (useStreaming) {
        // Use streaming endpoint
        setIsStreaming(true)
        
        // Create abort controller for cancellation
        abortControllerRef.current = new AbortController()
        
        // Create streaming message
        const streamingMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: "",
          role: "assistant",
          timestamp: new Date(),
          isStreaming: true
        }
        
        setCurrentConversation(prev => {
          if (!prev) return prev
          return {
            ...prev,
            messages: [...prev.messages, streamingMessage],
            updatedAt: new Date(),
          }
        })
        
        // Start SSE connection with token refresh retry logic
        const makeStreamRequest = async (retryCount = 0) => {
          const token = await getValidToken()
          const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/assistant/v2/chat/stream`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token || ''}`,
          },
          body: JSON.stringify({
            message: content,
            conversation_id: currentConversation.id,
            context: {
              tenant_id: currentUser.tenant_id,
              user_id: currentUser.id,
            }
          }),
          signal: abortControllerRef.current.signal
        })
        
        // Handle 401 Unauthorized (token expired) with retry
        if (response.status === 401 && retryCount === 0) {
          console.log('Token expired, invalidating cache and retrying...')
          invalidateToken() // Clear the cached token
          return makeStreamRequest(retryCount + 1)
        }
        
        if (!response.ok) {
          const errorData = await response.text()
          throw new Error(`Stream request failed: ${response.status} ${errorData}`)
        }
        
        return response
        }
        
        const response = await makeStreamRequest()
        
        const reader = response.body?.getReader()
        const decoder = new TextDecoder()
        
        if (reader) {
          let accumulatedContent = ""
          let metadata: any = {}
          
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            
            const chunk = decoder.decode(value)
            const lines = chunk.split('\n')
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6))
                  
                  if (data.type === 'content') {
                    accumulatedContent += data.content
                    
                    // Update streaming message
                    setCurrentConversation(prev => {
                      if (!prev) return prev
                      const messages = [...prev.messages]
                      const lastMessage = messages[messages.length - 1]
                      if (lastMessage && lastMessage.isStreaming) {
                        lastMessage.content = accumulatedContent
                      }
                      return { ...prev, messages, updatedAt: new Date() }
                    })
                  } else if (data.type === 'metadata') {
                    metadata = data
                  } else if (data.type === 'done') {
                    // Finalize message
                    setCurrentConversation(prev => {
                      if (!prev) return prev
                      const messages = [...prev.messages]
                      const lastMessage = messages[messages.length - 1]
                      if (lastMessage && lastMessage.isStreaming) {
                        lastMessage.isStreaming = false
                        lastMessage.actions = metadata.actions
                        lastMessage.suggestions = metadata.suggestions
                        lastMessage.confidence = metadata.confidence
                      }
                      return { ...prev, messages, updatedAt: new Date() }
                    })
                  }
                } catch (e) {
                  console.error('Error parsing SSE data:', e)
                }
              }
            }
          }
        }
        
        setIsStreaming(false)
      } else {
        // Use regular endpoint
        const response = await apiClient.post("/api/v1/assistant/v2/chat", {
          message: content,
          conversation_id: currentConversation.id,
          context: {
            tenant_id: currentUser.tenant_id,
            user_id: currentUser.id,
          }
        })

        if (response.data) {
          const assistantMessage: Message = {
            id: (Date.now() + 1).toString(),
            content: response.data.response,
            role: "assistant",
            timestamp: new Date(),
            metadata: response.data.metadata,
            actions: response.data.actions_taken,
            suggestions: response.data.suggestions,
            confidence: response.data.confidence
          }
          
          setCurrentConversation(prev => {
            if (!prev) return prev
            return {
              ...prev,
              messages: [...prev.messages, assistantMessage],
              updatedAt: new Date(),
            }
          })
        }
      }
    } catch (err: any) {
      console.error("Error sending message:", err)
      
      if (err.name !== 'AbortError') {
        setError("No pude procesar tu mensaje. Por favor, intenta de nuevo.")
        
        // Add error message
        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: "Lo siento, hubo un error al procesar tu mensaje. Por favor, intenta de nuevo.",
          role: "assistant",
          timestamp: new Date(),
        }
        
        setCurrentConversation(prev => {
          if (!prev) return prev
          return {
            ...prev,
            messages: [...prev.messages, errorMessage],
            updatedAt: new Date(),
          }
        })
      }
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
      abortControllerRef.current = null
    }
  }, [currentConversation, currentUser, apiClient, getValidToken, invalidateToken])

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setIsStreaming(false)
    }
  }, [])

  const clearConversation = useCallback(async () => {
    if (!currentConversation) return
    
    try {
      await apiClient.delete(`/api/v1/assistant/v2/conversation/${currentConversation.id}`)
      
      const clearedConversation: Conversation = {
        ...currentConversation,
        messages: [
          {
            id: "cleared",
            content: "Conversación limpiada. ¿En qué puedo ayudarte?",
            role: "assistant",
            timestamp: new Date(),
          }
        ],
        updatedAt: new Date(),
      }
      
      setCurrentConversation(clearedConversation)
      setConversations(prev => 
        prev.map(conv => 
          conv.id === currentConversation.id ? clearedConversation : conv
        )
      )
    } catch (err) {
      console.error("Error clearing conversation:", err)
    }
  }, [currentConversation, apiClient])

  const loadConversation = useCallback(async (id: string) => {
    setIsLoading(true)
    setError(null)
    
    try {
      const response = await apiClient.get(`/api/v1/assistant/v2/conversation/${id}`)
      
      if (response.data) {
        const conversation: Conversation = {
          id,
          messages: response.data.messages.map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          })),
          createdAt: new Date(),
          updatedAt: new Date()
        }
        
        setCurrentConversation(conversation)
      }
    } catch (err) {
      console.error("Error loading conversation:", err)
      setError("No pude cargar la conversación.")
    } finally {
      setIsLoading(false)
    }
  }, [apiClient])

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await apiClient.delete(`/api/v1/assistant/v2/conversation/${id}`)
      
      setConversations(prev => prev.filter(c => c.id !== id))
      if (currentConversation?.id === id) {
        setCurrentConversation(null)
      }
    } catch (err) {
      console.error("Error deleting conversation:", err)
    }
  }, [currentConversation, apiClient])

  return (
    <VirtualAssistantContext.Provider
      value={{
        conversations,
        currentConversation,
        isLoading,
        isStreaming,
        error,
        sendMessage,
        clearConversation,
        loadConversation,
        createNewConversation,
        loadWelcomeMessage,
        deleteConversation,
        stopStreaming
      }}
    >
      {children}
    </VirtualAssistantContext.Provider>
  )
}

export function useVirtualAssistant() {
  const context = useContext(VirtualAssistantContext)
  if (!context) {
    throw new Error("useVirtualAssistant must be used within VirtualAssistantProvider")
  }
  return context
}

