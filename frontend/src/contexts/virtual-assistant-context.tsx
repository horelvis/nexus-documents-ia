"use client"

import { createContext, useContext, useState, useCallback, ReactNode, useRef } from "react"
import { useBackendUser } from "./user-context"
import { useElysiaService } from "@/lib/services/elysia.service"

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
  const { backendUser } = useBackendUser()
  const { sendMessage: elysiaSendMessage } = useElysiaService()
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
    if (!currentConversation || currentConversation.messages.length > 0 || !backendUser?.tenant_id) {
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      // Use Elysia to generate welcome message
      const result = await elysiaSendMessage(
        "Genera un mensaje de bienvenida personalizado. Menciona cuántos documentos tiene el usuario si los hay.",
        currentConversation.id,
        backendUser.tenant_id,
        false,
        { is_welcome: true }
      )

      // Use suggestions from backend if available
      const backendSuggestions = result.suggestions?.map((s: any) =>
        typeof s === 'string' ? s : s.text
      ) || []

      const welcomeMessage: Message = {
        id: "welcome",
        content: result.answer || "",
        role: "assistant",
        timestamp: new Date(),
        suggestions: backendSuggestions.length > 0 ? backendSuggestions : undefined,
        metadata: {
          confidence: result.confidence_score,
          execution_time_ms: result.execution_time_ms,
          available_tools: result.available_tools
        }
      }

      setCurrentConversation(prev => {
        if (!prev) return prev
        return { ...prev, messages: [welcomeMessage], updatedAt: new Date() }
      })

    } catch (error: any) {
      console.error("Error getting welcome message:", error)
      const errorMessage: Message = {
        id: "error",
        content: `El servicio de asistente no está disponible. Error: ${error.message || 'Conexión fallida'}`,
        role: "assistant",
        timestamp: new Date(),
      }
      setCurrentConversation(prev => {
        if (!prev) return prev
        return { ...prev, messages: [errorMessage], updatedAt: new Date() }
      })
      setError(error.message || "Error de conexión")
    } finally {
      setIsLoading(false)
    }
  }, [currentConversation, backendUser?.tenant_id, elysiaSendMessage])

  const sendMessage = useCallback(async (content: string, _useStreaming: boolean = false) => {
    if (!currentConversation || !backendUser?.tenant_id) return

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

      // Use Elysia service (same as main chat page)
      const result = await elysiaSendMessage(
        content,
        currentConversation.id,
        backendUser.tenant_id,
        false // debug mode off for regular users
      )

      // Extract answer properly (handle tuple format from Python)
      let answerText = result.answer
      if (typeof answerText === 'string') {
        const tupleMatch = answerText.match(/^\('([^']*)',\s*\[.*\]\)$/)
        if (tupleMatch) {
          answerText = tupleMatch[1]
        }
      }

      // Use suggestions from backend
      const backendSuggestions = result.suggestions?.map((s: any) =>
        typeof s === 'string' ? s : s.text
      ) || []

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: answerText || "",
        role: "assistant",
        timestamp: new Date(),
        metadata: {
          confidence: result.confidence_score,
          execution_time_ms: result.execution_time_ms,
          tools_used: result.tools_used,
          decision_path: result.decision_path,
          available_tools: result.available_tools
        },
        suggestions: backendSuggestions.length > 0 ? backendSuggestions : undefined,
        confidence: result.confidence_score
      }

      setCurrentConversation(prev => {
        if (!prev) return prev
        return {
          ...prev,
          messages: [...prev.messages, assistantMessage],
          updatedAt: new Date(),
        }
      })

    } catch (err: any) {
      console.error("Error sending message:", err)

      setError(`Error del servicio: ${err.message || 'Servicio de asistente no disponible'}`)

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: `❌ Error: ${err.message || 'El servicio de asistente virtual falló'}`,
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
    } finally {
      setIsLoading(false)
      setIsStreaming(false)
      abortControllerRef.current = null
    }
  }, [currentConversation, backendUser?.tenant_id, elysiaSendMessage])

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      setIsStreaming(false)
    }
  }, [])

  const clearConversation = useCallback(async () => {
    if (!currentConversation) return

    // Clear conversation locally (Elysia doesn't persist conversations server-side)
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
  }, [currentConversation])

  const loadConversation = useCallback(async (id: string) => {
    // Conversations are stored locally only with Elysia
    const conversation = conversations.find(c => c.id === id)
    if (conversation) {
      setCurrentConversation(conversation)
    }
  }, [conversations])

  const deleteConversation = useCallback(async (id: string) => {
    // Delete conversation locally
    setConversations(prev => prev.filter(c => c.id !== id))
    if (currentConversation?.id === id) {
      setCurrentConversation(null)
    }
  }, [currentConversation])

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

