"use client"

import { useState, useCallback, useRef, useEffect, useImperativeHandle, forwardRef } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Brain, MessageSquare, Trash2, RefreshCw, Zap, Settings, BarChart3 } from "lucide-react"
import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import { useBackendUser } from "@/contexts/user-context"
import { useEmmaService } from "@/lib/services/emma.service"
import { useDocumentService } from "@/lib/services/document.service"
import { useRouter } from "next/navigation"
import { ElysiaQueryInput } from "./ElysiaQueryInput"
import { ElysiaRenderChat } from "./ElysiaRenderChat"
import { toast } from "sonner"
import { ToastProvider } from "@/contexts/ToastContext"

import { ElysiaMessage } from "./types"


interface ElysiaChatProps {
  tenantId: string
  className?: string
  initialMessage?: string
  initialQuery?: string // Auto-execute this query on load
  onClose?: () => void
  onFirstQuery?: () => void
  isAdmin?: boolean
  documentId?: string // Optional document context
  enableMentions?: boolean
}

export interface ElysiaChatRef {
  sendQuery: (query: string) => void
}

export const ElysiaChat = forwardRef<ElysiaChatRef, ElysiaChatProps>(function ElysiaChat({
  tenantId, className, initialMessage, initialQuery, onClose, onFirstQuery, isAdmin = false, documentId, enableMentions = true
}, ref) {
  const { backendUser } = useBackendUser()
  const { sendMessage } = useEmmaService()
  const documentService = useDocumentService()
  const router = useRouter()
  
  // State management
  const [messages, setMessages] = useState<ElysiaMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversationId] = useState(() => `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`)
  

  // No initialization needed - user is already authenticated

  // Handle sending queries
  const handleSendQuery = useCallback(async (query: string) => {
    if (!backendUser?.id || isLoading) return

    // Notify parent about first query (to hide example prompts)
    if (messages.length === 0 && onFirstQuery) {
      onFirstQuery()
    }

    // Add user message immediately
    const queryMessage: ElysiaMessage = {
      id: Date.now().toString(),
      type: "user", // Show as user message in the UI
      content: query,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, queryMessage])
    setIsLoading(true)
    setError(null)

    try {
      // Enable debug mode for admin users
      const debugEnabled = isAdmin
      // Pass document context if available
      const context = documentId ? { document_id: documentId, focus_document: true } : undefined
      const result = await sendMessage(query, conversationId, tenantId, debugEnabled, context)
      
      // Add result message
      const resultMessage: ElysiaMessage = {
        id: (Date.now() + 1).toString(),
        type: determineMessageType(result),
        content: extractAnswer(result.answer),
        timestamp: new Date(),
        metadata: {
          confidence_score: result.confidence_score,
          sources: extractSources(result.data?.citations || []),
          processing_time: result.execution_time_ms,
          execution_time_ms: result.execution_time_ms,
          agent_flow: result.tools_used || [],
          suggestions: getContextualSuggestions(result),
          debug_data: isAdmin && result.data ? result.data : undefined
        }
      }

      setMessages(prev => [...prev, resultMessage])

    } catch (err) {
      console.error('Query failed:', err)
      const errorMessage: ElysiaMessage = {
        id: (Date.now() + 1).toString(),
        type: "error",
        content: "Sorry, I encountered an error processing your request. Please try again.",
        timestamp: new Date()
      }

      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }, [backendUser?.id, tenantId, isLoading, sendMessage, conversationId, documentId, isAdmin])

  // Expose sendQuery method via ref
  // Handle document interactions
  const handleDocumentClick = useCallback(async (doc: any) => {
    if (!doc.name || !tenantId) return
    
    try {
      // If document ID is already available, navigate directly
      if (doc.id) {
        router.push(`/${tenantId}/documents/${doc.id}/preview`)
        return
      }
      
      // Fallback: Search for document by name to get its ID
      setIsLoading(true)
      
      const searchResponse = await documentService.searchDocuments(doc.name, 10)
      
      if (searchResponse.error || !searchResponse.data?.results) {
        toast.error(`No se pudo encontrar el documento: ${doc.name}`)
        return
      }
      
      // Find exact match by filename
      const exactMatch = searchResponse.data.results.find(
        result => result.filename === doc.name || result.title === doc.name
      )
      
      if (!exactMatch) {
        toast.error(`No se encontró el documento exacto: ${doc.name}`)
        return
      }
      
      // Navigate to preview page
      router.push(`/${tenantId}/documents/${exactMatch.id}/preview`)
      
    } catch (error) {
      console.error('Error finding document:', error)
      toast.error(`Error al buscar documento: ${error instanceof Error ? error.message : 'Error desconocido'}`)
    } finally {
      setIsLoading(false)
    }
  }, [documentService, tenantId, router, setIsLoading])

  const handlePreviewClick = useCallback((doc: any) => {
    // TODO: Implement document preview (modal, iframe, etc.)
    console.log('Preview clicked:', doc)
    if (doc.previewUrl) {
      window.open(doc.previewUrl, '_blank')
    } else {
      toast(`Vista previa de: ${doc.name}`)
    }
  }, [])

  useImperativeHandle(ref, () => ({
    sendQuery: handleSendQuery
  }), [handleSendQuery])

  // Execute initial query if provided
  useEffect(() => {
    if (initialQuery && backendUser?.id && messages.length === 0) {
      // Small delay to ensure component is fully mounted
      const timer = setTimeout(() => {
        handleSendQuery(initialQuery)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [initialQuery, backendUser?.id, messages.length, handleSendQuery])


  const clearMessages = () => {
    setMessages([])
    setError(null)
  }

  const startNewConversation = () => {
    setMessages([])
    setError(null)
  }

  const handleFeedback = (messageId: string, feedback: 'positive' | 'negative') => {
    // TODO: Implement feedback system
    console.log('Feedback:', messageId, feedback)
  }

  const handleSuggestionClick = (suggestion: string) => {
    handleSendQuery(suggestion)
  }

  const hasMessages = messages.length > 0

  return (
    <ToastProvider>
      <div className={cn("flex flex-col h-full", className)}>
        {hasMessages && (
          /* Chat messages solo cuando hay mensajes */
          <div className="flex-1 overflow-hidden min-h-0">
            <ElysiaRenderChat
              messages={messages}
              isLoading={isLoading}
              error={error}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSuggestionClick}
              onDocumentClick={handleDocumentClick}
              onPreviewClick={handlePreviewClick}
              isAdmin={isAdmin}
            />
          </div>
        )}

        {/* Spacer cuando no hay mensajes */}
        {!hasMessages && <div className="flex-1" />}

        {/* Query Input siempre pegado al bottom */}
        <div className="border-t bg-background p-4 pb-6">
          <ElysiaQueryInput
            onSendQuery={handleSendQuery}
            isLoading={isLoading}
            disabled={!backendUser?.id}
            placeholder="Pregúntame sobre tus documentos... (usa @ para mencionar entidades)"
            documentId={documentId || "general"}
            enableMentions={enableMentions}
          />
        </div>
      </div>
    </ToastProvider>
  )
})

// Helper functions
function determineMessageType(data: any): ElysiaMessage["type"] {
  if (data.error) return "error"
  if (data.confidence_score && data.confidence_score < 0.5) return "warning"
  return "result"
}

function extractAnswer(answer: any): string {
  if (typeof answer === "string") {
    // Handle Python tuple format: "('text', [])" or "('text', [...])""
    const tupleMatch = answer.match(/^\('([^']*)',\s*\[.*\]\)$/)
    if (tupleMatch) {
      return tupleMatch[1] // Extract just the text content
    }
    
    // Handle other string formats
    return answer
  }
  if (Array.isArray(answer) && answer.length > 0) {
    return typeof answer[0] === "string" ? answer[0] : String(answer[0])
  }
  if (answer && typeof answer === "object") {
    return answer.content || answer.text || String(answer)
  }
  return String(answer || "")
}

function extractSources(citations: any[]): Array<{document: string; page?: number; relevance: number}> {
  return citations.map((citation, index) => ({
    document: citation.document || citation.source || `Source ${index + 1}`,
    page: citation.page || citation.page_number,
    relevance: citation.relevance || citation.score || 0.8
  }))
}

function getContextualSuggestions(result: any): string[] {
  // Dynamic suggestions based on result context
  if (result.document_type === "contract") {
    return [
      "Analizar términos del contrato",
      "Buscar cláusulas específicas", 
      "Verificar fechas de vencimiento"
    ]
  }

  return [
    "¿Qué más puedes hacer?",
    "Buscar información específica",
    "Mostrar estadísticas"
  ]
}