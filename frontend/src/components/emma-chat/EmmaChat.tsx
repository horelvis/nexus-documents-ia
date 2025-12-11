"use client"

import { useState, useCallback, useRef, useEffect, useImperativeHandle, forwardRef } from "react"
import { cn } from "@/lib/utils"
import { useBackendUser } from "@/contexts/user-context"
import { useEmmaService, EmmaStreamEvent, classifyError } from "@/lib/services/emma.service"
import { useDocumentService } from "@/lib/services/document.service"
import { useTranslation } from "@/lib/i18n/hooks"
import { useRouter } from "next/navigation"
import { EmmaQueryInput } from "./EmmaQueryInput"
import { EmmaRenderChat } from "./EmmaRenderChat"
import { toast } from "sonner"
import { ToastProvider } from "@/contexts/ToastContext"

import { EmmaMessage, WorkflowStep } from "./types"


interface EmmaChatProps {
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

export interface EmmaChatRef {
  sendQuery: (query: string) => void
}

export const EmmaChat = forwardRef<EmmaChatRef, EmmaChatProps>(function EmmaChat({
  tenantId, className, initialMessage, initialQuery, onClose, onFirstQuery, isAdmin = false, documentId, enableMentions = true
}, ref) {
  const { backendUser } = useBackendUser()
  const { sendMessage, queryEmmaStream } = useEmmaService()
  const documentService = useDocumentService()
  const router = useRouter()
  const { t } = useTranslation()

  // State management
  const [messages, setMessages] = useState<EmmaMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Persist conversationId in sessionStorage to maintain context across component remounts
  const [conversationId] = useState(() => {
    // Use a stable key based on tenantId to allow different sessions per tenant
    const storageKey = `emma_conversation_${tenantId}`

    // Check if we have a stored session ID
    if (typeof window !== 'undefined') {
      const storedId = sessionStorage.getItem(storageKey)
      if (storedId) {
        return storedId
      }
      // Generate new ID and store it
      const newId = `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      sessionStorage.setItem(storageKey, newId)
      return newId
    }
    // Fallback for SSR
    return `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  })
  const [streamProgress, setStreamProgress] = useState<{ message: string; progress: number } | null>(null)
  const [lastFailedQuery, setLastFailedQuery] = useState<string | null>(null)


  // No initialization needed - user is already authenticated

  // Handle sending queries with streaming
  const handleSendQuery = useCallback(async (query: string) => {
    if (!backendUser?.id || isLoading) return

    // Notify parent about first query (to hide example prompts)
    if (messages.length === 0 && onFirstQuery) {
      onFirstQuery()
    }

    // Add user message immediately
    const queryMessage: EmmaMessage = {
      id: Date.now().toString(),
      type: "user",
      content: query,
      timestamp: new Date()
    }

    setMessages(prev => [...prev, queryMessage])
    setIsLoading(true)
    setError(null)
    // Use neutral placeholder - ThinkingIndicator will show animated phrases
    setStreamProgress({ message: "", progress: 0 })

    // Add a progress message - ThinkingIndicator will handle the display until backend sends plan
    const progressMessageId = (Date.now() + 1).toString()
    const progressMessage: EmmaMessage = {
      id: progressMessageId,
      type: "progress",
      content: "",  // Empty - ThinkingIndicator will show animated phrases
      timestamp: new Date(),
      metadata: { progress: 0 }
    }
    setMessages(prev => [...prev, progressMessage])

    // Track workflow steps during streaming
    let workflowSteps: WorkflowStep[] = []

    try {
      // Build context with user info for personalization
      const context: Record<string, any> = {
        user_id: backendUser.id,
        user_name: backendUser.full_name || backendUser.email?.split('@')[0],
        user_email: backendUser.email,
      }
      if (documentId) {
        context.document_id = documentId
        context.focus_document = true
      }

      await queryEmmaStream(
        {
          query,
          session_id: conversationId,
          tenant_id: tenantId,
          enable_debug: isAdmin,
          context
        },
        (event: EmmaStreamEvent) => {
          const { data } = event

          // Handle plan_created - update with dynamic LLM-generated message
          if (event.event === 'plan_created' && data.steps) {
            workflowSteps = data.steps.map((step: { index: number; description: string; agent: string }) => ({
              index: step.index,
              description: step.description,
              agent: step.agent,
              status: 'pending' as const
            }))

            // Update progress indicator with dynamic message from backend
            if (data.message) {
              setStreamProgress({
                message: data.message,
                progress: data.progress || 10
              })
            }

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    content: data.message || "Plan creado",
                    metadata: {
                      ...msg.metadata,
                      progress: data.progress || 10,
                      total_steps: data.total_steps || workflowSteps.length,
                      plan_id: data.plan_id,
                      workflow_steps: [...workflowSteps]
                    }
                  }
                : msg
            ))
          }

          // Handle step_start - mark step as in_progress
          if (event.event === 'step_start' && data.step !== undefined) {
            const stepIndex = data.step - 1 // Convert 1-indexed to 0-indexed
            workflowSteps = workflowSteps.map((step, idx) => ({
              ...step,
              status: idx === stepIndex ? 'in_progress' : idx < stepIndex ? 'completed' : step.status
            }))

            setStreamProgress({
              message: data.message || `Ejecutando ${data.agent || 'agente'}...`,
              progress: data.progress || 0
            })

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    content: data.message || msg.content,
                    metadata: {
                      ...msg.metadata,
                      progress: data.progress,
                      step: data.step,
                      total_steps: data.total_steps,
                      agent: data.agent,
                      workflow_steps: [...workflowSteps]
                    }
                  }
                : msg
            ))
          }

          // Handle step_complete - mark step as completed
          if (event.event === 'step_complete' && data.step !== undefined) {
            const stepIndex = data.step - 1
            workflowSteps = workflowSteps.map((step, idx) =>
              idx === stepIndex
                ? {
                    ...step,
                    status: 'completed' as const,
                    findings_count: data.findings_count,
                    execution_time_ms: data.execution_time_ms
                  }
                : step
            )

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    content: data.message || msg.content,
                    metadata: {
                      ...msg.metadata,
                      progress: data.progress,
                      step: data.step,
                      total_steps: data.total_steps,
                      agent: data.agent,
                      workflow_steps: [...workflowSteps]
                    }
                  }
                : msg
            ))
          }

          // Handle step_error - mark step as error
          if (event.event === 'step_error' && data.step !== undefined) {
            const stepIndex = data.step - 1
            workflowSteps = workflowSteps.map((step, idx) =>
              idx === stepIndex
                ? { ...step, status: 'error' as const, error: data.error }
                : step
            )

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      workflow_steps: [...workflowSteps]
                    }
                  }
                : msg
            ))
          }

          // Handle other progress events (planning, consolidating, etc.)
          if (!['plan_created', 'step_start', 'step_complete', 'step_error', 'complete', 'error'].includes(event.event)) {
            setStreamProgress({
              message: data.message || `Procesando...`,
              progress: data.progress || 0
            })

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    content: data.message || msg.content,
                    metadata: {
                      ...msg.metadata,
                      progress: data.progress,
                      step: data.step,
                      total_steps: data.total_steps,
                      agent: data.agent
                    }
                  }
                : msg
            ))
          }

          // Handle completion
          if (event.event === 'complete') {
            setStreamProgress(null)

            // Replace progress message with final result
            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    type: "result" as const,
                    content: extractAnswer(data.answer || data.final_result?.summary || "Análisis completado"),
                    metadata: {
                      confidence_score: data.final_result?.confidence_score || data.confidence_score || 0.7,
                      processing_time: data.execution_time_ms,
                      execution_time_ms: data.execution_time_ms,
                      decision_path: data.final_result?.decision_path || data.decision_path || [],
                      tools_used: data.final_result?.tools_used || data.tools_used || [],
                      agent_flow: workflowSteps.map(s => s.agent),
                      suggestions: getContextualSuggestions(data),
                      debug_data: isAdmin ? { ...data, workflow_steps: workflowSteps } : undefined
                    }
                  }
                : msg
            ))

            setIsLoading(false)
          }

          // Handle error
          if (event.event === 'error') {
            setStreamProgress(null)

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    type: "error" as const,
                    content: data.error || "Error en el análisis"
                  }
                : msg
            ))

            setIsLoading(false)
          }
        }
      )

    } catch (err) {
      console.error('Query failed:', err)
      setStreamProgress(null)

      // Classify the error and get i18n keys
      const classifiedError = classifyError(err)

      // Store failed query for retry functionality
      setLastFailedQuery(query)

      // Update progress message to error with i18n keys in metadata
      setMessages(prev => prev.map(msg =>
        msg.id === progressMessageId
          ? {
              ...msg,
              type: "error" as const,
              content: `${t(classifiedError.titleKey)}: ${t(classifiedError.messageKey)}`,
              metadata: {
                ...msg.metadata,
                errorType: classifiedError.type,
                errorTitleKey: classifiedError.titleKey,
                errorMessageKey: classifiedError.messageKey,
                canRetry: classifiedError.canRetry,
                failedQuery: query
              }
            }
          : msg
      ))

      setIsLoading(false)
    }
  }, [backendUser?.id, tenantId, isLoading, queryEmmaStream, conversationId, documentId, isAdmin, messages.length, onFirstQuery, t])

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
    // Clear the sessionStorage to generate a new session ID on next component mount
    // This allows users to start a completely fresh conversation
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem(`emma_conversation_${tenantId}`)
    }
  }

  const handleFeedback = (messageId: string, feedback: 'positive' | 'negative') => {
    // TODO: Implement feedback system
    console.log('Feedback:', messageId, feedback)
  }

  const handleSuggestionClick = (suggestion: string) => {
    handleSendQuery(suggestion)
  }

  // Handle retry for failed queries
  const handleRetry = (failedQuery: string) => {
    // Remove the error message before retrying
    setMessages(prev => prev.filter(msg => msg.type !== 'error'))
    // Clear the failed query state
    setLastFailedQuery(null)
    // Re-execute the query
    handleSendQuery(failedQuery)
  }

  const hasMessages = messages.length > 0

  return (
    <ToastProvider>
      <div className={cn("flex flex-col h-full", className)}>
        {/* Chat messages when available */}
        {hasMessages && (
          <div className="flex-1 overflow-hidden min-h-0">
            <EmmaRenderChat
              messages={messages}
              isLoading={isLoading}
              error={error}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSuggestionClick}
              onDocumentClick={handleDocumentClick}
              onPreviewClick={handlePreviewClick}
              onRetry={handleRetry}
              isAdmin={isAdmin}
            />
          </div>
        )}

        {/* Spacer when no messages */}
        {!hasMessages && <div className="flex-1" />}

        {/* Query Input always at bottom */}
        <div className="border-t bg-background p-4 pb-6">
          <EmmaQueryInput
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
function determineMessageType(data: any): EmmaMessage["type"] {
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

    // Handle JSON followed by natural text (LLM sometimes outputs both)
    // Find where JSON ends by matching braces
    if (answer.trim().startsWith('{')) {
      let braceCount = 0
      let jsonEndIndex = -1

      for (let i = 0; i < answer.length; i++) {
        if (answer[i] === '{') braceCount++
        else if (answer[i] === '}') {
          braceCount--
          if (braceCount === 0) {
            jsonEndIndex = i
            break
          }
        }
      }

      if (jsonEndIndex > 0) {
        const jsonPart = answer.substring(0, jsonEndIndex + 1)
        const textAfterJson = answer.substring(jsonEndIndex + 1).trim()

        try {
          const parsed = JSON.parse(jsonPart)
          // If text after JSON exists, use it (it's the friendly message)
          if (textAfterJson) {
            return textAfterJson
          }
          // If no text after, try to extract summary from JSON
          if (parsed.summary) {
            return parsed.summary
          }
          if (parsed.text) {
            return parsed.text
          }
          if (parsed.answer) {
            return parsed.answer
          }
          if (parsed.content) {
            return parsed.content
          }
          // If we have a message field, use it
          if (parsed.message) {
            return parsed.message
          }
        } catch {
          // Not valid JSON, return original answer
        }
      }
    }

    // Handle other string formats
    return answer
  }
  if (Array.isArray(answer) && answer.length > 0) {
    return typeof answer[0] === "string" ? answer[0] : String(answer[0])
  }
  if (answer && typeof answer === "object") {
    return answer.content || answer.text || answer.summary || String(answer)
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

// Backward compatibility
export { EmmaChat as ElysiaChat }
export type { EmmaChatProps as ElysiaChatProps }
export type { EmmaChatRef as ElysiaChatRef }
