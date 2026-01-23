'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { useEmmaService, classifyError, EmmaStreamEvent } from '@/lib/services/emma.service'
import { EmmaQueryInput } from './EmmaQueryInput'
import { EmmaRenderChat } from './EmmaRenderChat'
import { PDFPreviewModal } from './PDFPreviewModal'
import { EmmaMessage, WorkflowStep, EmmaChatProps, DocumentInfo, Attachment } from '@/lib/types/emma'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { IconBrain, IconBolt } from '@tabler/icons-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const SSO_TOKEN_KEY = 'nexus_sso_tokens'

function hasValidToken(): boolean {
  if (typeof window === 'undefined') return false
  const stored = sessionStorage.getItem(SSO_TOKEN_KEY)
  if (!stored) return false
  try {
    const tokens = JSON.parse(stored)
    // Check if token exists and is not expired
    if (!tokens.access_token) return false
    if (tokens.expires_at && Date.now() >= tokens.expires_at - 60000) {
      return false // Expired or about to expire
    }
    return true
  } catch {
    return false
  }
}

export function EmmaChat({
  className,
  initialQuery,
  messages: externalMessages,
  onMessagesChange,
  conversationId,
}: EmmaChatProps) {
  const { user, tenantId, isAuthenticated, login } = useAuth()
  const { queryEmmaStream } = useEmmaService()

  // Use internal state if no external messages provided (uncontrolled mode)
  const [internalMessages, setInternalMessages] = useState<EmmaMessage[]>([])
  const messages = externalMessages !== undefined ? externalMessages : internalMessages

  // Use ref to track current messages without causing callback recreation
  // This fixes the circular dependency: updateMessages -> messages -> updateMessages
  const messagesRef = useRef(messages)
  messagesRef.current = messages

  // Stable callback refs for parent handlers
  const onMessagesChangeRef = useRef(onMessagesChange)
  onMessagesChangeRef.current = onMessagesChange

  // Wrapper to update messages (supports both controlled and uncontrolled modes)
  // IMPORTANT: No dependencies on 'messages' to prevent recreation during streaming
  const updateMessages = useCallback(
    (updater: EmmaMessage[] | ((prev: EmmaMessage[]) => EmmaMessage[])) => {
      const currentMessages = messagesRef.current
      const newMessages = typeof updater === 'function' ? updater(currentMessages) : updater

      if (onMessagesChangeRef.current) {
        onMessagesChangeRef.current(newMessages)
      } else {
        setInternalMessages(newMessages)
      }
    },
    [] // No dependencies - uses refs for current values
  )

  const [isLoading, setIsLoadingInternal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Use ref to track loading state without causing callback recreations
  const isLoadingRef = useRef(isLoading)
  isLoadingRef.current = isLoading

  // Wrapper for setIsLoading with debug logging
  const setIsLoading = useCallback((value: boolean) => {
    console.log('[EmmaChat] setIsLoading:', value)
    setIsLoadingInternal(value)
  }, [])
  const [deepReasoning, setDeepReasoning] = useState(false) // Fast mode by default

  // PDF Preview modal state
  const [previewDoc, setPreviewDoc] = useState<DocumentInfo | null>(null)
  const [showPreviewModal, setShowPreviewModal] = useState(false)

  // Generate stable session ID
  const [sessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      const storageKey = `emma_session_${tenantId || 'default'}`
      const stored = sessionStorage.getItem(storageKey)
      if (stored) return stored

      const newId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
      sessionStorage.setItem(storageKey, newId)
      return newId
    }
    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
  })

  // Handle sending queries
  const handleSendQuery = useCallback(
    async (query: string, attachments?: Attachment[]) => {
      // Use ref to check loading state (prevents stale closure issues)
      if (!user?.id || !tenantId || isLoadingRef.current) return

      // Verify token is valid before making the request
      if (!hasValidToken()) {
        setError('Tu sesión ha expirado. Por favor inicia sesión nuevamente.')
        // Give user a moment to see the message, then redirect to login
        setTimeout(() => {
          login()
        }, 1500)
        return
      }

      // Build user message content
      // Attachments are now shown visually in the chat, so content is just the query
      // If no query but has attachments, show a placeholder text
      let userContent = query
      if (!query && attachments && attachments.length > 0) {
        userContent = 'Analiza estos documentos'
      }

      // Add user message
      const userMessage: EmmaMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: userContent,
        timestamp: new Date(),
        metadata: attachments && attachments.length > 0 ? {
          documents: attachments.map((a) => ({
            name: a.name,
            id: a.type === 'indexed' ? a.documentId : a.id,
            fileType: a.fileType,
          })),
        } : undefined,
      }

      // Add progress message placeholder
      const progressMessageId = (Date.now() + 1).toString()
      const progressMessage: EmmaMessage = {
        id: progressMessageId,
        type: 'progress',
        content: '',
        timestamp: new Date(),
        metadata: { progress: 0, streaming_text: '' },
      }

      updateMessages((prev) => [...prev, userMessage, progressMessage])
      setIsLoading(true)
      setError(null)

      // Track workflow steps
      let workflowSteps: WorkflowStep[] = []
      let streamedAnswer = ''

      // Prepare attachment context for backend
      const attachmentContext: Record<string, unknown> = {}
      if (attachments && attachments.length > 0) {
        // Indexed documents - send their IDs
        const indexedDocs = attachments.filter((a) => a.type === 'indexed')
        if (indexedDocs.length > 0) {
          // Use the first indexed document as the primary document_id
          attachmentContext.document_id = indexedDocs[0].documentId
          // All indexed document IDs for multi-document queries
          attachmentContext.indexed_document_ids = indexedDocs.map((a) => a.documentId)
        }

        // Uploaded files - prepare metadata (files stay in memory for now)
        const uploadedDocs = attachments.filter((a) => a.type === 'upload')
        if (uploadedDocs.length > 0) {
          attachmentContext.uploaded_files = uploadedDocs.map((a) => ({
            name: a.name,
            type: a.fileType,
            size: a.size,
          }))
        }

        // Attachment summary for the AI
        attachmentContext.attachment_summary = `Usuario adjuntó ${attachments.length} documento(s): ${attachments.map((a) => a.name).join(', ')}`
      }

      let streamCompleted = false // Track if we received a terminal event

      try {
        await queryEmmaStream(
          {
            query: query || (attachments?.length ? `Analiza los siguientes documentos adjuntos: ${attachments.map((a) => a.name).join(', ')}` : ''),
            session_id: sessionId,
            tenant_id: tenantId,
            deep_reasoning: deepReasoning,
            context: {
              user_id: user.id,
              user_name: user.full_name || user.email?.split('@')[0],
              user_email: user.email,
              ...attachmentContext,
            },
          },
          (event: EmmaStreamEvent) => {
            const { data } = event

            // Handle plan_created
            if (event.event === 'plan_created' && data.steps) {
              workflowSteps = data.steps.map((step) => ({
                index: step.index,
                description: step.description,
                agent: step.agent,
                status: 'pending' as const,
              }))

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        content: data.message || 'Plan creado',
                        metadata: {
                          ...msg.metadata,
                          progress: data.progress || 10,
                          total_steps: data.total_steps || workflowSteps.length,
                          plan_id: data.plan_id,
                          workflow_steps: [...workflowSteps],
                        },
                      }
                    : msg
                )
              )
            }

            // Handle step_start
            if (event.event === 'step_start' && data.step !== undefined) {
              const stepIndex = data.step - 1
              workflowSteps = workflowSteps.map((step, idx) => ({
                ...step,
                status:
                  idx === stepIndex
                    ? 'in_progress'
                    : idx < stepIndex
                      ? 'completed'
                      : step.status,
              }))

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        content: data.message || `Ejecutando ${data.agent || 'agente'}...`,
                        metadata: {
                          ...msg.metadata,
                          progress: data.progress,
                          step: data.step,
                          total_steps: data.total_steps,
                          agent: data.agent,
                          workflow_steps: [...workflowSteps],
                        },
                      }
                    : msg
                )
              )
            }

            // Handle step_complete
            if (event.event === 'step_complete' && data.step !== undefined) {
              const stepIndex = data.step - 1
              workflowSteps = workflowSteps.map((step, idx) =>
                idx === stepIndex
                  ? {
                      ...step,
                      status: 'completed' as const,
                      findings_count: data.findings_count,
                      execution_time_ms: data.execution_time_ms,
                    }
                  : step
              )

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        content: data.message || msg.content,
                        metadata: {
                          ...msg.metadata,
                          progress: data.progress,
                          step: data.step,
                          total_steps: data.total_steps,
                          workflow_steps: [...workflowSteps],
                        },
                      }
                    : msg
                )
              )
            }

            // Handle step_error
            if (event.event === 'step_error' && data.step !== undefined) {
              const stepIndex = data.step - 1
              workflowSteps = workflowSteps.map((step, idx) =>
                idx === stepIndex
                  ? { ...step, status: 'error' as const, error: data.error }
                  : step
              )

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        metadata: {
                          ...msg.metadata,
                          workflow_steps: [...workflowSteps],
                        },
                      }
                    : msg
                )
              )
            }

            // Handle token events - accumulate streamed text
            if (event.event === 'token' && data.text) {
              streamedAnswer += data.text
              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        metadata: {
                          ...msg.metadata,
                          agent: data.agent || msg.metadata?.agent,
                          isStreaming: true,
                          streaming_text: streamedAnswer,
                        },
                      }
                    : msg
                )
              )
              return // Don't process as other event
            }

            // Handle other progress events (progress, start, delegation, first_token, etc.)
            if (
              !['plan_created', 'step_start', 'step_complete', 'step_error', 'complete', 'error', 'token'].includes(
                event.event
              )
            ) {
              updateMessages((prev) =>
                prev.map((msg) =>
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
                        },
                      }
                    : msg
                )
              )
            }

            // Handle completion
            if (event.event === 'complete') {
              streamCompleted = true
              // Use data.answer if provided, otherwise preserve accumulated content from tokens
              const answerFromServer =
                typeof data.answer === 'string' && data.answer.trim()
                  ? data.answer
                  : (data.final_result as any)?.summary || null

              // Build documents array from attachments (with real names)
              // These are the documents the user attached for analysis
              const documentSources = attachments?.map((a) => ({
                name: a.name,
                id: a.type === 'indexed' ? a.documentId : a.id,
                fileType: a.fileType,
              })) || []

              updateMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== progressMessageId) return msg

                  // Preserve accumulated content if server didn't provide an answer
                  const finalContent =
                    answerFromServer ||
                    msg.metadata?.streaming_text ||
                    msg.content ||
                    'Análisis completado'

                  return {
                    ...msg,
                    type: 'result' as const,
                    content: finalContent,
                    metadata: {
                      confidence_score:
                        (data.final_result as any)?.confidence_score || 0.7,
                      processing_time: data.execution_time_ms,
                      execution_time_ms: data.execution_time_ms,
                      decision_path:
                        (data.final_result as any)?.decision_path || [],
                      tools_used: (data.final_result as any)?.tools_used || [],
                      agent_flow: workflowSteps.map((s) => s.agent),
                      suggestions: getContextualSuggestions(),
                      isStreaming: false,
                      // Include attached documents as sources with real names
                      documents: documentSources.length > 0 ? documentSources : undefined,
                    },
                    suggestions: getContextualSuggestions(),
                  }
                })
              )

              setIsLoading(false)
            }

            // Handle error
            if (event.event === 'error') {
              streamCompleted = true
              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        type: 'error' as const,
                        content: data.error || 'Error en el análisis',
                      }
                    : msg
                )
              )

              setIsLoading(false)
            }
          }
        )

        // Safety: If stream ended without 'complete' or 'error' event, ensure we reset loading state
        if (!streamCompleted) {
          console.warn('[EmmaChat] Stream ended without terminal event, resetting loading state')
          setIsLoading(false)
        }
      } catch (err) {
        console.error('Query failed:', err)

        const classifiedError = classifyError(err)

        // If auth error, redirect to login
        if (classifiedError.type === 'auth') {
          updateMessages((prev) =>
            prev.map((msg) =>
              msg.id === progressMessageId
                ? {
                    ...msg,
                    type: 'error' as const,
                    content: 'Tu sesión ha expirado. Redirigiendo al login...',
                    metadata: {
                      ...msg.metadata,
                      errorType: classifiedError.type,
                      canRetry: false,
                    },
                  }
                : msg
            )
          )
          setIsLoading(false)
          setTimeout(() => login(), 1500)
          return
        }

        updateMessages((prev) =>
          prev.map((msg) =>
            msg.id === progressMessageId
              ? {
                  ...msg,
                  type: 'error' as const,
                  content: `${classifiedError.message}`,
                  metadata: {
                    ...msg.metadata,
                    errorType: classifiedError.type,
                    canRetry: classifiedError.canRetry,
                    failedQuery: query,
                  },
                }
              : msg
          )
        )

        setIsLoading(false)
      }
    },
    [user, tenantId, queryEmmaStream, sessionId, login, updateMessages, deepReasoning]
  )

  // Handle feedback
  const handleFeedback = useCallback(
    (messageId: string, feedback: 'positive' | 'negative') => {
      console.log('Feedback:', messageId, feedback)
      // TODO: Send feedback to backend
    },
    []
  )

  // Handle suggestion click
  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      handleSendQuery(suggestion)
    },
    [handleSendQuery]
  )

  // Handle retry
  const handleRetry = useCallback(
    (failedQuery: string) => {
      // Remove error message before retry
      updateMessages((prev) => prev.filter((msg) => msg.type !== 'error'))
      handleSendQuery(failedQuery)
    },
    [handleSendQuery, updateMessages]
  )

  // Handle document click
  const handleDocumentClick = useCallback((doc: DocumentInfo) => {
    // Default behavior: open preview
    setPreviewDoc(doc)
    setShowPreviewModal(true)
  }, [])

  // Handle preview click
  const handlePreviewClick = useCallback((doc: DocumentInfo) => {
    setPreviewDoc(doc)
    setShowPreviewModal(true)
  }, [])

  // Execute initial query
  useEffect(() => {
    if (initialQuery && user?.id && tenantId && messages.length === 0) {
      const timer = setTimeout(() => {
        handleSendQuery(initialQuery)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [initialQuery, user?.id, tenantId, messages.length, handleSendQuery])

  const hasMessages = messages.length > 0

  // Debug: log render state
  console.log('[EmmaChat] Render - isLoading:', isLoading, 'hasMessages:', hasMessages)

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Chat messages */}
      {hasMessages && (
        <div className="flex-1 overflow-hidden min-h-0">
          <EmmaRenderChat
            messages={messages}
            isLoading={isLoading}
            error={error}
            onFeedback={handleFeedback}
            onSuggestionClick={handleSuggestionClick}
            onRetry={handleRetry}
            onDocumentClick={handleDocumentClick}
            onPreviewClick={handlePreviewClick}
          />
        </div>
      )}

      {/* Empty state */}
      {!hasMessages && (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div className="text-center space-y-4 max-w-md">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center">
              <span className="text-3xl">🧠</span>
            </div>
            <h2 className="text-2xl font-semibold">Hola, soy Emma</h2>
            <p className="text-muted-foreground">
              Tu asistente de inteligencia empresarial. Puedo ayudarte a buscar,
              analizar y entender tus documentos.
            </p>

            {/* Example prompts */}
            <div className="space-y-2 pt-4">
              <p className="text-sm text-muted-foreground font-medium">
                Prueba preguntarme:
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {EXAMPLE_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendQuery(prompt)}
                    className="px-3 py-1.5 text-sm bg-muted hover:bg-muted/80 rounded-lg transition-colors"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t bg-background p-4">
        {/* Deep Reasoning Toggle */}
        <TooltipProvider>
          <div className="flex items-center justify-end gap-2 mb-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex items-center gap-2">
                  <IconBolt className={cn(
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
                  <IconBrain className={cn(
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
          disabled={!user?.id}
          placeholder="Pregúntame sobre tus documentos..."
          maxAttachments={10}
        />
      </div>

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        document={previewDoc}
        open={showPreviewModal}
        onOpenChange={setShowPreviewModal}
      />
    </div>
  )
}

// Example prompts
const EXAMPLE_PROMPTS = [
  '¿Cuántos documentos tengo?',
  'Resume los contratos activos',
  '¿Qué documentos vencen pronto?',
]

// Contextual suggestions
function getContextualSuggestions(): string[] {
  return [
    '¿Puedes darme más detalles?',
    'Buscar información relacionada',
    '¿Qué documentos mencionan esto?',
  ]
}
