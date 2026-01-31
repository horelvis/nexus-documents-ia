"use client"

import { useState, useCallback, useRef, useEffect, useImperativeHandle, forwardRef } from "react"
import { cn } from "@/lib/utils"
import { useBackendUser } from "@/contexts/user-context"
import { useEmmaService, EmmaStreamEvent, classifyError } from "@/lib/services/emma.service"
import { useDocumentService } from "@/lib/services/document.service"
import { useLearningService } from "@/lib/services/learning.service"
import { useTranslation } from "@/lib/i18n/hooks"
import { useRouter } from "next/navigation"
import { EmmaQueryInput } from "./EmmaQueryInput"
import { EmmaRenderChat } from "./EmmaRenderChat"
import { PDFPreviewModal, PreviewDocument } from "./displays/Document/PDFPreviewModal"
import { toast } from "sonner"
import { ToastProvider } from "@/contexts/ToastContext"
import { Switch } from "@/components/ui/switch"
import { Label } from "@/components/ui/label"
import { Brain, Zap } from "lucide-react"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

import { EmmaMessage, WorkflowStep, DelegationInfo, ProgressStage } from "./types"


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
  const learningService = useLearningService()
  const router = useRouter()
  const { t } = useTranslation()

  // State management
  const [messages, setMessages] = useState<EmmaMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deepReasoning, setDeepReasoning] = useState(false) // Fast mode by default

  // PDF Preview Modal state
  const [previewDoc, setPreviewDoc] = useState<PreviewDocument | null>(null)
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  // Persist conversationId in sessionStorage to maintain context across component remounts
  // When documentId is provided, create a new conversation specific to that document
  const [conversationId] = useState(() => {
    // If analyzing a specific document, create a document-specific conversation
    if (documentId && documentId !== "general") {
      const docStorageKey = `emma_doc_conversation_${tenantId}_${documentId}`
      if (typeof window !== 'undefined') {
        // Always create a new conversation for document analysis (don't reuse old failed ones)
        const newId = `conv_doc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        sessionStorage.setItem(docStorageKey, newId)
        return newId
      }
      return `conv_doc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    }

    // Use a stable key based on tenantId for general conversations
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
          deep_reasoning: deepReasoning,
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

          // Handle delegation events (when Emma uses tools)
          if (event.event === 'delegation') {
            const newDelegation: DelegationInfo = {
              agent: data.agent || data.tool || 'unknown',
              message: data.message || `Usando ${data.agent || data.tool}...`,
              elapsedMs: data.elapsed_ms,
              timestamp: new Date()
            }

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      delegations: [
                        ...(msg.metadata?.delegations || []),
                        newDelegation
                      ]
                    }
                  }
                : msg
            ))
          }

          // Handle progress events with stage
          if (event.event === 'progress' && data.stage) {
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
                      stage: data.stage as ProgressStage,
                      stageMessage: data.message,
                      progress: data.progress
                    }
                  }
                : msg
            ))
          }

          // Handle first_token event (transition to streaming mode)
          if (event.event === 'first_token') {
            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      stage: 'generating' as ProgressStage,
                      stageMessage: 'Generando respuesta...',
                      streamingText: data.text || '',
                      isStreaming: true
                    }
                  }
                : msg
            ))
          }

          // Handle token events (streaming text)
          if (event.event === 'token') {
            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    metadata: {
                      ...msg.metadata,
                      streamingText: (msg.metadata?.streamingText || '') + (data.text || data.token || ''),
                      isStreaming: true
                    }
                  }
                : msg
            ))
          }

          // Handle slm_thinking events — collect as workflow_steps for reasoning panel
          if (event.event === 'slm_thinking') {
            const stepType = data.type || data.slmThinkingStep?.type || 'structural'
            const stepContent = data.content || data.message || 'Procesando...'

            // Map step type to agent name for icon/color
            const typeToAgent: Record<string, string> = {
              'retrieval': 'search',
              'search': 'search',
              'observation': 'analysis',
              'domain_detection': 'reasoning',
              'agent_selection': 'reasoning',
              'agent_execution': 'synthesis',
              'transformation': 'synthesis',
              'response': 'synthesis',
              'structural': 'reasoning',
              'route': 'reasoning',
            }

            const newStep: WorkflowStep = {
              index: workflowSteps.length + 1,
              description: stepContent,
              agent: typeToAgent[stepType] || 'reasoning',
              status: 'completed' as const,
            }
            workflowSteps = [...workflowSteps, newStep]

            setStreamProgress({
              message: stepContent,
              progress: data.progress || 0
            })

            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    content: stepContent,
                    metadata: {
                      ...msg.metadata,
                      progress: data.progress,
                      workflow_steps: [...workflowSteps]
                    }
                  }
                : msg
            ))
          }

          // Handle other progress events (planning, consolidating, etc.) - fallback
          if (!['plan_created', 'step_start', 'step_complete', 'step_error', 'complete', 'error', 'delegation', 'token', 'first_token', 'slm_thinking'].includes(event.event) && !data.stage) {
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

          // Handle Human-in-the-Loop clarification requests
          if (event.event === 'clarification_needed' || event.event === 'confirmation_needed' || event.event === 'suggestions_available') {
            setStreamProgress(null)

            // Replace progress message with clarification UI
            setMessages(prev => prev.map(msg =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    type: "clarification" as const,
                    content: data.question || "Emma necesita tu ayuda",
                    metadata: {
                      ...msg.metadata,
                      clarification: {
                        question: data.question || "",
                        header: data.header || "Opción",
                        options: data.options || [],
                        multi_select: data.multi_select || false,
                        severity: data.severity,
                        type: event.event === 'confirmation_needed' ? 'confirmation'
                            : event.event === 'suggestions_available' ? 'suggestion'
                            : 'clarification'
                      }
                    }
                  }
                : msg
            ))

            // Keep loading state - waiting for user response
            // setIsLoading will be set to false when user submits clarification
          }

          // Handle completion
          if (event.event === 'complete') {
            setStreamProgress(null)

            // Replace progress message with final result
            setMessages(prev => prev.map(msg => {
              if (msg.id !== progressMessageId) return msg

              // Use streaming text as content if available, otherwise extract from data
              const finalContent = msg.metadata?.streamingText ||
                extractAnswer(data.answer || data.final_result?.summary || "Análisis completado")

              return {
                ...msg,
                type: "result" as const,
                content: finalContent,
                metadata: {
                  confidence_score: data.final_result?.confidence_score || data.confidence_score || 0.7,
                  processing_time: data.execution_time_ms,
                  execution_time_ms: data.execution_time_ms,
                  decision_path: data.final_result?.decision_path || data.decision_path || [],
                  tools_used: data.final_result?.tools_used || data.tools_used || [],
                  agent_flow: workflowSteps.length > 0
                    ? workflowSteps.map(s => s.agent)
                    : msg.metadata?.delegations?.map(d => d.agent) || [],
                  suggestions: getContextualSuggestions(data),
                  debug_data: isAdmin ? { ...data, workflow_steps: workflowSteps, delegations: msg.metadata?.delegations } : undefined,
                  // Clear streaming state
                  streamingText: undefined,
                  isStreaming: false,
                  delegations: undefined,
                  stage: undefined,
                  stageMessage: undefined
                }
              }
            }))

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
  }, [backendUser?.id, tenantId, isLoading, queryEmmaStream, conversationId, documentId, isAdmin, messages.length, onFirstQuery, t, deepReasoning])

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
    // Open PDF preview modal
    const previewDocument: PreviewDocument = {
      name: doc.name,
      id: doc.id,
      url: doc.url,
      previewUrl: doc.previewUrl,
      fileType: doc.fileType || (doc.name?.toLowerCase().endsWith('.pdf') ? 'pdf' : undefined),
      relevanceScore: doc.relevanceScore,
    }
    setPreviewDoc(previewDocument)
    setShowPreviewModal(true)
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

  const handleFeedback = async (messageId: string, feedback: 'positive' | 'negative') => {
    try {
      // Record feedback for learning system
      const result = await learningService.recordFeedback(
        conversationId,
        feedback
      )

      if (result.data) {
        // Visual feedback to user
        toast.success(
          feedback === 'positive'
            ? '¡Gracias por tu feedback!'
            : 'Trabajaremos para mejorar.'
        )
      }
    } catch (error) {
      console.error('Failed to record feedback:', error)
      // Don't show error to user - feedback is non-critical
    }
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

  // Handle Human-in-the-Loop clarification response
  const handleClarificationSubmit = useCallback((messageId: string, selectedValues: string[]) => {
    // Find the clarification message to get context
    const clarificationMsg = messages.find(m => m.id === messageId)
    if (!clarificationMsg?.metadata?.clarification) return

    const { question, options } = clarificationMsg.metadata.clarification

    // Build response context
    // If custom input (starts with "custom:"), use that text
    const isCustom = selectedValues[0]?.startsWith("custom:")
    let responseText: string

    if (isCustom) {
      responseText = selectedValues[0].replace("custom:", "").trim()
    } else {
      // Map selected values to labels for natural language
      const selectedLabels = selectedValues
        .map(v => options?.find((o: { value: string; label: string }) => o.value === v)?.label || v)
        .join(", ")
      responseText = selectedLabels
    }

    // Update the clarification message to show what was selected
    setMessages(prev => prev.map(msg =>
      msg.id === messageId
        ? {
            ...msg,
            type: "result" as const,
            content: `**${question}**\n\n✅ Seleccionaste: ${responseText}`,
            metadata: {
              ...msg.metadata,
              clarification: undefined // Clear clarification data
            }
          }
        : msg
    ))

    // Send the response as a continuation query with context
    // The backend will receive this and continue the conversation
    const continuationQuery = `[Respuesta a clarificación: ${responseText}]`
    handleSendQuery(continuationQuery)
  }, [messages, handleSendQuery])

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
              onClarificationSubmit={handleClarificationSubmit}
              isAdmin={isAdmin}
            />
          </div>
        )}

        {/* Spacer when no messages */}
        {!hasMessages && <div className="flex-1" />}

        {/* Query Input always at bottom */}
        <div className="border-t bg-background p-4 pb-6">
          {/* Deep Reasoning Toggle */}
          <TooltipProvider>
            <div className="flex items-center justify-end gap-2 mb-3">
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2">
                    <Zap className={cn(
                      "h-4 w-4 transition-colors",
                      !deepReasoning ? "text-yellow-500" : "text-muted-foreground"
                    )} />
                    <Label
                      htmlFor="deep-reasoning"
                      className={cn(
                        "text-xs cursor-pointer select-none transition-colors",
                        !deepReasoning ? "text-foreground" : "text-muted-foreground"
                      )}
                    >
                      Rápido
                    </Label>
                    <Switch
                      id="deep-reasoning"
                      checked={deepReasoning}
                      onCheckedChange={setDeepReasoning}
                      disabled={isLoading}
                      className="data-[state=checked]:bg-purple-600"
                    />
                    <Label
                      htmlFor="deep-reasoning"
                      className={cn(
                        "text-xs cursor-pointer select-none transition-colors",
                        deepReasoning ? "text-foreground" : "text-muted-foreground"
                      )}
                    >
                      Profundo
                    </Label>
                    <Brain className={cn(
                      "h-4 w-4 transition-colors",
                      deepReasoning ? "text-purple-500" : "text-muted-foreground"
                    )} />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <p className="font-semibold mb-1">
                    {deepReasoning ? "Modo Profundo" : "Modo Rápido"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {deepReasoning
                      ? "Análisis exhaustivo con razonamiento detallado. Ideal para contratos, cumplimiento y análisis legal."
                      : "Respuestas rápidas y directas. Ideal para búsquedas simples y consultas generales."
                    }
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>

          <EmmaQueryInput
            onSendQuery={handleSendQuery}
            isLoading={isLoading}
            disabled={!backendUser?.id}
            placeholder="Pregúntame sobre tus documentos... (usa @ para mencionar entidades)"
            documentId={documentId || "general"}
            enableMentions={enableMentions}
          />
        </div>

        {/* PDF Preview Modal */}
        <PDFPreviewModal
          document={previewDoc}
          open={showPreviewModal}
          onOpenChange={setShowPreviewModal}
          tenantId={tenantId}
        />
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
