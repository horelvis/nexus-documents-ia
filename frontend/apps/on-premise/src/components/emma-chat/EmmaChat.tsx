'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { flushSync } from 'react-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { useEmmaService, classifyError, EmmaStreamEvent } from '@/lib/services/emma.service'
import { queryVerifiedStream, mapEventToClaim, VerifiedStreamEvent } from '@/lib/services/verified-generation.service'
import { queryPredictiveStream, PredictiveStreamEvent } from '@/lib/services/predictive-analysis.service'
import { EmmaQueryInput } from './EmmaQueryInput'
import { EmmaRenderChat } from './EmmaRenderChat'
import { PDFPreviewModal } from './PDFPreviewModal'
import { VerifiedGenerationDialog } from './VerifiedGenerationDialog'
import { PredictiveAnalysisDialog } from './PredictiveAnalysisDialog'
import { EmmaMessage, WorkflowStep, EmmaChatProps, DocumentInfo, Attachment, SLMThinkingStep, VerifiedClaimInfo, VerifiedGenerationMetadata, PredictiveFactorInfo, PredictiveAnalysisMetadata } from '@/lib/types/emma'
import { isDocGenResult, extractDocGenMetadata } from '@/lib/utils/docgen-detector'
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
  const { queryEmmaStream, uploadTempDocument } = useEmmaService()

  // Use internal state if no external messages provided (uncontrolled mode)
  const [internalMessages, setInternalMessages] = useState<EmmaMessage[]>([])
  const isControlled = externalMessages !== undefined
  const messages = isControlled ? externalMessages : internalMessages

  // Stable callback refs for parent handlers
  const onMessagesChangeRef = useRef(onMessagesChange)
  onMessagesChangeRef.current = onMessagesChange

  // IMPORTANT: Use a separate ref to track the "working" state during rapid updates
  // This ref is updated immediately after each change, ensuring subsequent updates
  // see the latest state even before React re-renders
  const latestMessagesRef = useRef<EmmaMessage[]>(messages)

  // Sync the ref when messages change (from props or internal state)
  useEffect(() => {
    latestMessagesRef.current = messages
  }, [messages])

  // Wrapper to update messages (supports both controlled and uncontrolled modes)
  // Uses latestMessagesRef to ensure we always have the latest state during rapid updates
  // Set immediate=true to force synchronous render (for real-time streaming updates)
  const updateMessages = useCallback(
    (updater: EmmaMessage[] | ((prev: EmmaMessage[]) => EmmaMessage[]), immediate = false) => {
      // Get the most recent messages from our ref
      const currentMessages = latestMessagesRef.current

      // Calculate new messages
      const newMessages = typeof updater === 'function'
        ? updater(currentMessages)
        : updater

      // Update the ref IMMEDIATELY for subsequent rapid calls
      latestMessagesRef.current = newMessages

      // Update state (controlled or uncontrolled)
      const doUpdate = () => {
        if (onMessagesChangeRef.current) {
          // Controlled mode: notify parent
          onMessagesChangeRef.current(newMessages)
        } else {
          // Uncontrolled mode: update internal state
          setInternalMessages(newMessages)
        }
      }

      // Force immediate render for streaming updates
      if (immediate) {
        flushSync(doUpdate)
      } else {
        doUpdate()
      }
    },
    [] // No dependencies - uses refs for current values
  )

  // Legacy ref for backwards compatibility (if any code uses messagesRef)
  const messagesRef = latestMessagesRef

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

  // Verified generation queue state (supports multiple concurrent jobs)
  const [verifiedDialogOpen, setVerifiedDialogOpen] = useState(false)
  const [verifiedJobs, setVerifiedJobs] = useState<Record<string, VerifiedGenerationMetadata>>({})
  const verifiedJobsRef = useRef<Record<string, VerifiedGenerationMetadata>>({})

  // Predictive analysis queue state
  const [predictiveDialogOpen, setPredictiveDialogOpen] = useState(false)
  const [predictiveJobs, setPredictiveJobs] = useState<Record<string, PredictiveAnalysisMetadata>>({})
  const predictiveJobsRef = useRef<Record<string, PredictiveAnalysisMetadata>>({})

  // Retain uploaded file IDs across follow-up queries in the same session
  const sessionUploadIdsRef = useRef<string[]>([])
  const sessionDocIdRef = useRef<string | null>(null)
  const sessionIndexedDocIdsRef = useRef<string[]>([])

  // Generate stable session ID (migrate from default when tenantId becomes available)
  const [sessionId, setSessionId] = useState(() => {
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

  useEffect(() => {
    if (!tenantId || typeof window === 'undefined') return
    const tenantKey = `emma_session_${tenantId}`
    const storedTenant = sessionStorage.getItem(tenantKey)
    if (storedTenant && storedTenant !== sessionId) {
      setSessionId(storedTenant)
      return
    }

    const defaultKey = 'emma_session_default'
    const storedDefault = sessionStorage.getItem(defaultKey)
    if (storedDefault && storedDefault !== sessionId) {
      sessionStorage.setItem(tenantKey, storedDefault)
      sessionStorage.removeItem(defaultKey)
      setSessionId(storedDefault)
      return
    }

    if (!storedTenant) {
      const newId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
      sessionStorage.setItem(tenantKey, newId)
      setSessionId(newId)
    }
  }, [tenantId, sessionId])

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

      // Track SLM thinking steps (old format)
      let slmThinkingSteps: SLMThinkingStep[] = []

      // Prepare attachment context for backend
      const attachmentContext: Record<string, unknown> = {}
      const uploadedDocs = attachments?.filter((a) => a.type === 'upload') || []
      if (uploadedDocs.length > 0) {
        updateMessages((prev) =>
          prev.map((msg) =>
            msg.id === progressMessageId
              ? {
                  ...msg,
                  content: 'Subiendo documentos...',
                  metadata: {
                    ...msg.metadata,
                    progress: 5,
                  },
                }
              : msg
          )
        )

        const uploadResults = await Promise.all(
          uploadedDocs.map(async (doc) => {
            const result = await uploadTempDocument(doc.file)
            return { name: doc.name, uploadId: result.upload_id }
          })
        )

        const newUploadIds = uploadResults.map((r) => r.uploadId)
        attachmentContext.uploaded_file_ids = newUploadIds
        attachmentContext.uploaded_files = uploadResults.map((r) => ({
          name: r.name,
          upload_id: r.uploadId,
        }))
        // Retain IDs so follow-up queries keep the document context
        sessionUploadIdsRef.current = [...new Set([...sessionUploadIdsRef.current, ...newUploadIds])]
      }
      if (attachments && attachments.length > 0) {
        // Indexed documents - send their IDs
        const indexedDocs = attachments.filter((a) => a.type === 'indexed')
        if (indexedDocs.length > 0) {
          // Use the first indexed document as the primary document_id
          attachmentContext.document_id = indexedDocs[0].documentId
          // All indexed document IDs for multi-document queries
          attachmentContext.indexed_document_ids = indexedDocs.map((a) => a.documentId)
          // Retain for follow-up queries
          sessionDocIdRef.current = attachmentContext.document_id
          sessionIndexedDocIdsRef.current = attachmentContext.indexed_document_ids
        }

        // Uploaded files - prepare metadata (files stay in memory for now)
        // Attachment summary for the AI
        attachmentContext.attachment_summary = `Usuario adjuntó ${attachments.length} documento(s): ${attachments.map((a) => a.name).join(', ')}`
      }

      // Re-attach previous document context for follow-up queries
      if (!attachmentContext.uploaded_file_ids && sessionUploadIdsRef.current.length > 0) {
        attachmentContext.uploaded_file_ids = sessionUploadIdsRef.current
      }
      if (!attachmentContext.document_id && sessionDocIdRef.current) {
        attachmentContext.document_id = sessionDocIdRef.current
      }
      if (!attachmentContext.indexed_document_ids && sessionIndexedDocIdsRef.current.length > 0) {
        attachmentContext.indexed_document_ids = sessionIndexedDocIdsRef.current
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
              updateMessages(
                (prev) =>
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
                  ),
                true // immediate render for real-time streaming
              )
              return // Don't process as other event
            }

            // Handle SLM Router thinking step events - visible chain-of-thought
            // Support both old format (slmThinkingStep object) and new format (type at data level)
            if (event.event === 'slm_thinking') {
              // Check if this has inline thinking data (type at data level, no slmThinkingStep wrapper)
              // Backend sends: { step, type, content, slmIsThinking } without slmThinkingStep wrapper for some events
              const inlineStepType = data.step_type || data.type
              if (inlineStepType && !data.slmThinkingStep) {
                // Normalize inline step into SLMThinkingStep
                const newStep: SLMThinkingStep = {
                  step: typeof data.step === 'number' ? data.step : slmThinkingSteps.length + 1,
                  type: inlineStepType as SLMThinkingStep['type'],
                  content: data.content || data.message || '',
                  confidence: data.confidence,
                  entities: data.entities,
                }
                slmThinkingSteps = [...slmThinkingSteps, newStep]

                updateMessages(
                  (prev) =>
                    prev.map((msg) =>
                      msg.id === progressMessageId
                        ? {
                            ...msg,
                            content: data.message || msg.content,
                            metadata: {
                              ...msg.metadata,
                              slmIsThinking: data.slmIsThinking ?? true,
                              slmThinkingSteps: [...slmThinkingSteps],
                            },
                          }
                        : msg
                    ),
                  true // immediate render for real-time streaming
                )
                return // Don't process as other event
              }

              // Old format with slmThinkingStep object
              if (data.slmThinkingStep) {
                slmThinkingSteps = [...slmThinkingSteps, data.slmThinkingStep]

                updateMessages(
                  (prev) =>
                    prev.map((msg) =>
                      msg.id === progressMessageId
                        ? {
                            ...msg,
                            content: data.message || msg.content,
                            metadata: {
                              ...msg.metadata,
                              slmIsThinking: data.slmIsThinking ?? true,
                              slmThinkingSteps: [...slmThinkingSteps],
                            },
                          }
                        : msg
                    ),
                  true // immediate render for real-time streaming
                )
                return // Don't process as other event
              }
            }

            // Handle SLM Router plan ready event
            if (event.event === 'slm_plan' && data.slmPlan) {
              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        content: data.message || msg.content,
                        metadata: {
                          ...msg.metadata,
                          slmIsThinking: false,
                          slmPlan: data.slmPlan,
                        },
                      }
                    : msg
                )
              )
              return // Don't process as other event
            }

            // Handle other progress events (progress, start, delegation, first_token, etc.)
            // Also handles slm_reasoning and slm_executing stages via progress events
            if (
              !['plan_created', 'step_start', 'step_complete', 'step_error', 'complete', 'error', 'token', 'slm_thinking', 'slm_plan'].includes(
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
                          // SLM Router fields from progress events
                          ...(data.slmIsThinking !== undefined && { slmIsThinking: data.slmIsThinking }),
                          ...(data.slmIsExecuting !== undefined && { slmIsExecuting: data.slmIsExecuting }),
                          ...(data.slmThinkingSteps && { slmThinkingSteps: data.slmThinkingSteps }),
                          ...(data.stage && { stage: data.stage }),
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

                  // Merge steps: prefer local accumulated, fallback to message metadata
                  const finalSlmSteps = slmThinkingSteps.length > 0
                    ? [...slmThinkingSteps]
                    : msg.metadata?.slmThinkingSteps || []
                  // Use backend suggestions if available, otherwise generate contextual ones
                  const backendSuggestions = data.suggestions || (data.final_result as any)?.suggestions
                  const finalSuggestions = Array.isArray(backendSuggestions) && backendSuggestions.length > 0
                    ? backendSuggestions
                    : getContextualSuggestions(query, finalContent, (data.final_result as any)?.tools_used)

                  // Detect document generation results (logic in docgen-detector.ts)
                  if (isDocGenResult({
                    query,
                    content: finalContent,
                    toolsUsed: (data.final_result as any)?.tools_used,
                    domains: (data as any).domains,
                  })) {
                    return {
                      ...msg,
                      type: 'docgen_result' as const,
                      content: finalContent,
                      docgen: extractDocGenMetadata(query, finalContent, data.execution_time_ms),
                      metadata: {
                        confidence_score:
                          (data.final_result as any)?.confidence_score || 0.7,
                        processing_time: data.execution_time_ms,
                        execution_time_ms: data.execution_time_ms,
                        decision_path:
                          (data.final_result as any)?.decision_path || [],
                        tools_used: (data.final_result as any)?.tools_used || [],
                        agent_flow: workflowSteps.map((s) => s.agent),
                        workflow_steps: workflowSteps.length > 0 ? [...workflowSteps] : msg.metadata?.workflow_steps,
                        suggestions: finalSuggestions,
                        isStreaming: false,
                        documents: documentSources.length > 0 ? documentSources : undefined,
                        slmThinkingSteps: finalSlmSteps.length > 0 ? finalSlmSteps : undefined,
                        slmIsThinking: false,
                      },
                      suggestions: finalSuggestions,
                    }
                  }

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
                      suggestions: finalSuggestions,
                      isStreaming: false,
                      // Include attached documents as sources with real names
                      documents: documentSources.length > 0 ? documentSources : undefined,
                      // Preserve SLM thinking steps from progress phase
                      slmThinkingSteps: finalSlmSteps.length > 0 ? finalSlmSteps : undefined,
                      slmIsThinking: false,
                    },
                    suggestions: finalSuggestions,
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
    [user, tenantId, queryEmmaStream, uploadTempDocument, sessionId, login, updateMessages, deepReasoning]
  )

  // Handle verified document generation (non-blocking dialog)
  const handleVerifiedGeneration = useCallback(
    async (topic: string, attachments?: Attachment[]) => {
      if (!user?.id || !tenantId) return

      if (!hasValidToken()) {
        setError('Tu sesión ha expirado. Por favor inicia sesión nuevamente.')
        setTimeout(() => login(), 1500)
        return
      }

      try {

      const userMessage: EmmaMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: `/verificar ${topic}`,
        timestamp: new Date(),
        metadata: attachments && attachments.length > 0 ? {
          documents: attachments.map((a) => ({
            name: a.name,
            id: a.type === 'indexed' ? a.documentId : a.id,
            fileType: a.fileType,
          })),
        } : undefined,
      }

      // Placeholder message — will become verified_result on completion
      const verifiedMessageId = (Date.now() + 1).toString()
      const initialVerified: VerifiedGenerationMetadata = {
        session_id: sessionId,
        tenant_id: tenantId || undefined,
        topic,
        claims: [],
        current_phase: 'generating',
        verified_count: 0,
        rejected_count: 0,
        total_claims: 0,
      }

      // Add user message only; progress shown in widget
      updateMessages((prev) => [...prev, userMessage])
      setError(null)

      // Helper to update this job in the queue
      const jobId = verifiedMessageId
      const updateJob = (updater: (prev: VerifiedGenerationMetadata) => VerifiedGenerationMetadata) => {
        setVerifiedJobs((prev) => {
          const current = prev[jobId]
          if (!current) return prev
          const next = updater(current)
          const updated = { ...prev, [jobId]: next }
          verifiedJobsRef.current = updated
          return updated
        })
      }
      const removeJob = () => {
        setVerifiedJobs((prev) => {
          const { [jobId]: _, ...rest } = prev
          verifiedJobsRef.current = rest
          return rest
        })
      }

      // Add job to queue and open widget
      setVerifiedJobs((prev) => {
        const updated = { ...prev, [jobId]: initialVerified }
        verifiedJobsRef.current = updated
        return updated
      })
      setVerifiedDialogOpen(true)

      // Upload non-indexed files (same process as normal query)
      const uploadedDocs = attachments?.filter((a) => a.type === 'upload') || []
      let uploadedFileIds: string[] = []
      if (uploadedDocs.length > 0) {
        try {
          const uploadResults = await Promise.all(
            uploadedDocs.map(async (doc) => {
              const result = await uploadTempDocument(doc.file)
              return result.upload_id
            })
          )
          uploadedFileIds = uploadResults
          sessionUploadIdsRef.current = [...new Set([...sessionUploadIdsRef.current, ...uploadedFileIds])]
        } catch (err) {
          console.error('Failed to upload documents for verification:', err)
        }
      }

      // Re-attach previous uploads for follow-up
      if (uploadedFileIds.length === 0 && sessionUploadIdsRef.current.length > 0) {
        uploadedFileIds = sessionUploadIdsRef.current
      }

      const contextDocIds = attachments
        ?.filter((a) => a.type === 'indexed')
        .map((a) => a.documentId) || []

      try {
        for await (const event of queryVerifiedStream({
          query: topic,
          tenant_id: tenantId,
          session_id: sessionId,
          context_document_ids: contextDocIds.length > 0 ? contextDocIds : undefined,
          uploaded_file_ids: uploadedFileIds.length > 0 ? uploadedFileIds : undefined,
        })) {
          console.log('[VerifiedGen] SSE event:', event.event_type, event.claim_id, event.data)
          const claimUpdate = mapEventToClaim(event)
          console.log('[VerifiedGen] claimUpdate:', claimUpdate)

          if (event.event_type === 'document_complete') {
            // Capture accumulated claims from ref before removing job
            const jobClaims = verifiedJobsRef.current[jobId]?.claims || []
            removeJob()

            const finalVerified: VerifiedGenerationMetadata = {
              ...initialVerified,
              claims: jobClaims,
              current_phase: 'complete',
              document_text: event.data.document_text,
              verified_count: event.data.claims_verified ?? 0,
              rejected_count: event.data.claims_rejected ?? 0,
              total_claims: event.data.total_claims_generated ?? 0,
              execution_time_ms: event.data.execution_time_ms,
              average_confidence: event.data.average_confidence,
              sources: event.data.sources,
            }

            updateMessages((prev) => [...prev, {
              id: verifiedMessageId,
              type: 'verified_result' as const,
              content: event.data.document_text || '',
              timestamp: new Date(),
              verified: finalVerified,
            }])
            return
          }

          if (event.event_type === 'error') {
            removeJob()
            updateMessages((prev) => [...prev, {
              id: verifiedMessageId,
              type: 'error' as const,
              content: event.data.error || 'Error en generación verificada',
              timestamp: new Date(),
            }])
            return
          }

          if (claimUpdate) {
            updateJob((prev) => {
              const existingIdx = prev.claims.findIndex((c) => c.claim_id === claimUpdate.claim_id)
              let newClaims: VerifiedClaimInfo[]
              if (existingIdx >= 0) {
                newClaims = prev.claims.map((c, i) =>
                  i === existingIdx ? { ...c, ...claimUpdate } : c
                )
              } else {
                newClaims = [...prev.claims, {
                  claim_id: claimUpdate.claim_id,
                  claim_number: claimUpdate.claim_number || prev.claims.length + 1,
                  total_expected: claimUpdate.total_expected || 0,
                  claim_text: claimUpdate.claim_text || '',
                  status: claimUpdate.status || 'generating',
                  confidence: claimUpdate.confidence,
                  evidence_count: claimUpdate.evidence_count,
                  original_text: claimUpdate.original_text,
                }]
              }

              const verifiedCount = newClaims.filter(c => c.status === 'verified' || c.status === 'corrected').length
              const rejectedCount = newClaims.filter(c => c.status === 'rejected').length
              const totalExpected = claimUpdate.total_expected || prev.total_claims || newClaims.length
              const hasVerifying = newClaims.some(c => c.status === 'verifying')

              return {
                ...prev,
                claims: newClaims,
                verified_count: verifiedCount,
                rejected_count: rejectedCount,
                total_claims: totalExpected,
                current_phase: hasVerifying ? 'verifying' as const : 'generating' as const,
              }
            })
          }
        }

        // Stream ended without document_complete
        removeJob()
      } catch (err) {
        console.error('Verified generation failed:', err)
        const classifiedError = classifyError(err)
        removeJob()
        updateMessages((prev) => [...prev, {
          id: verifiedMessageId,
          type: 'error' as const,
          content: classifiedError.message,
          timestamp: new Date(),
        }])
      }

      } catch (outerErr) {
        console.error('[VerifiedGeneration] Unexpected error:', outerErr)
      }
    },
    [user, tenantId, sessionId, login, updateMessages, uploadTempDocument]
  )

  // Handle predictive analysis (non-blocking dialog)
  const handlePredictiveAnalysis = useCallback(
    async (caseDescription: string, attachments?: Attachment[]) => {
      if (!user?.id || !tenantId) return

      if (!hasValidToken()) {
        setError('Tu sesión ha expirado. Por favor inicia sesión nuevamente.')
        setTimeout(() => login(), 1500)
        return
      }

      try {
        const userMessage: EmmaMessage = {
          id: Date.now().toString(),
          type: 'user',
          content: `/predecir ${caseDescription}`,
          timestamp: new Date(),
          metadata: attachments && attachments.length > 0 ? {
            documents: attachments.map((a) => ({
              name: a.name,
              id: a.type === 'indexed' ? a.documentId : a.id,
              fileType: a.fileType,
            })),
          } : undefined,
        }

        const predictiveMessageId = (Date.now() + 1).toString()
        const initialPredictive: PredictiveAnalysisMetadata = {
          session_id: sessionId,
          tenant_id: tenantId || undefined,
          case_description: caseDescription,
          factors: [],
          current_phase: 'extracting',
          weighted_count: 0,
          rejected_count: 0,
          total_factors: 0,
        }

        updateMessages((prev) => [...prev, userMessage])
        setError(null)

        const jobId = predictiveMessageId
        const updateJob = (updater: (prev: PredictiveAnalysisMetadata) => PredictiveAnalysisMetadata) => {
          setPredictiveJobs((prev) => {
            const current = prev[jobId]
            if (!current) return prev
            const next = updater(current)
            const updated = { ...prev, [jobId]: next }
            predictiveJobsRef.current = updated
            return updated
          })
        }
        const removeJob = () => {
          setPredictiveJobs((prev) => {
            const { [jobId]: _, ...rest } = prev
            predictiveJobsRef.current = rest
            return rest
          })
        }

        setPredictiveJobs((prev) => {
          const updated = { ...prev, [jobId]: initialPredictive }
          predictiveJobsRef.current = updated
          return updated
        })
        setPredictiveDialogOpen(true)

        // Upload files
        const uploadedDocs = attachments?.filter((a) => a.type === 'upload') || []
        let uploadedFileIds: string[] = []
        if (uploadedDocs.length > 0) {
          try {
            const uploadResults = await Promise.all(
              uploadedDocs.map(async (doc) => {
                const result = await uploadTempDocument(doc.file)
                return result.upload_id
              })
            )
            uploadedFileIds = uploadResults
            sessionUploadIdsRef.current = [...new Set([...sessionUploadIdsRef.current, ...uploadedFileIds])]
          } catch (err) {
            console.error('Failed to upload documents for prediction:', err)
          }
        }

        if (uploadedFileIds.length === 0 && sessionUploadIdsRef.current.length > 0) {
          uploadedFileIds = sessionUploadIdsRef.current
        }

        const contextDocIds = attachments
          ?.filter((a) => a.type === 'indexed')
          .map((a) => a.documentId) || []

        try {
          for await (const event of queryPredictiveStream({
            case_description: caseDescription,
            tenant_id: tenantId,
            session_id: sessionId,
            context_document_ids: contextDocIds.length > 0 ? contextDocIds : undefined,
            uploaded_file_ids: uploadedFileIds.length > 0 ? uploadedFileIds : undefined,
          })) {
            console.log('[Predictive] SSE event:', event.event_type, event.factor_id)

            if (event.event_type === 'prediction_complete') {
              const jobFactors = predictiveJobsRef.current[jobId]?.factors || []
              removeJob()

              const finalPredictive: PredictiveAnalysisMetadata = {
                ...initialPredictive,
                factors: jobFactors,
                current_phase: 'complete',
                weighted_count: event.data.factors_weighted ?? 0,
                rejected_count: event.data.factors_rejected ?? 0,
                total_factors: event.data.total_factors ?? jobFactors.length,
                probability: event.data.probability,
                primary_outcome: event.data.primary_outcome,
                outcome_probabilities: event.data.outcome_probabilities
                  ? Object.fromEntries(
                      Object.entries(event.data.outcome_probabilities).map(
                        ([k, v]: [string, any]) => [k, typeof v === 'object' && v !== null ? v.probability : v]
                      )
                    )
                  : undefined,
                recommendation: event.data.recommendation,
                disclaimer: event.data.disclaimer,
                execution_time_ms: event.data.execution_time_ms,
              }

              updateMessages((prev) => [...prev, {
                id: predictiveMessageId,
                type: 'predictive_result' as const,
                content: event.data.recommendation || '',
                timestamp: new Date(),
                predictive: finalPredictive,
              }])
              return
            }

            if (event.event_type === 'error') {
              removeJob()
              updateMessages((prev) => [...prev, {
                id: predictiveMessageId,
                type: 'error' as const,
                content: event.data.error || 'Error en análisis predictivo',
                timestamp: new Date(),
              }])
              return
            }

            // Update factors in the job
            if (event.factor_id) {
              updateJob((prev) => {
                const existingIdx = prev.factors.findIndex((f) => f.factor_id === event.factor_id)
                let newFactors: PredictiveFactorInfo[]

                const factorUpdate: Partial<PredictiveFactorInfo> = {
                  factor_id: event.factor_id!,
                }

                if (event.event_type === 'factor_extracted') {
                  factorUpdate.factor_number = event.data.factor_number || prev.factors.length + 1
                  factorUpdate.total_expected = event.data.total_expected || 0
                  factorUpdate.factor_type = event.data.factor_type || ''
                  factorUpdate.description = event.data.description || ''
                  factorUpdate.status = 'extracting'
                } else if (event.event_type === 'factor_verification_started') {
                  factorUpdate.status = 'verifying'
                } else if (event.event_type === 'factor_weighted') {
                  factorUpdate.status = 'weighted'
                  factorUpdate.weight = event.data.weight
                  factorUpdate.confidence = event.data.confidence
                  factorUpdate.outcome = event.data.outcome
                  factorUpdate.evidence_count = event.data.evidence_count
                } else if (event.event_type === 'factor_rejected') {
                  factorUpdate.status = 'rejected'
                }

                if (existingIdx >= 0) {
                  newFactors = prev.factors.map((f, i) =>
                    i === existingIdx ? { ...f, ...factorUpdate } : f
                  )
                } else {
                  newFactors = [...prev.factors, {
                    factor_id: factorUpdate.factor_id!,
                    factor_number: factorUpdate.factor_number || prev.factors.length + 1,
                    total_expected: factorUpdate.total_expected || 0,
                    factor_type: factorUpdate.factor_type || '',
                    description: factorUpdate.description || '',
                    status: factorUpdate.status || 'extracting',
                    weight: factorUpdate.weight,
                    confidence: factorUpdate.confidence,
                    outcome: factorUpdate.outcome,
                    evidence_count: factorUpdate.evidence_count,
                  }]
                }

                const weightedCount = newFactors.filter(f => f.status === 'weighted').length
                const rejectedCount = newFactors.filter(f => f.status === 'rejected').length
                const totalExpected = factorUpdate.total_expected || prev.total_factors || newFactors.length
                const hasVerifying = newFactors.some(f => f.status === 'verifying')

                return {
                  ...prev,
                  factors: newFactors,
                  weighted_count: weightedCount,
                  rejected_count: rejectedCount,
                  total_factors: totalExpected,
                  current_phase: hasVerifying ? 'verifying' as const : 'extracting' as const,
                }
              })
            }

            if (event.event_type === 'synthesis_started') {
              updateJob((prev) => ({ ...prev, current_phase: 'synthesizing' as const }))
            }
          }

          // Stream ended without prediction_complete
          removeJob()
        } catch (err) {
          console.error('Predictive analysis failed:', err)
          const classifiedError = classifyError(err)
          removeJob()
          updateMessages((prev) => [...prev, {
            id: predictiveMessageId,
            type: 'error' as const,
            content: classifiedError.message,
            timestamp: new Date(),
          }])
        }
      } catch (outerErr) {
        console.error('[PredictiveAnalysis] Unexpected error:', outerErr)
      }
    },
    [user, tenantId, sessionId, login, updateMessages, uploadTempDocument]
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
            <img
              src="/emma-welcome.png"
              alt="Emma"
              className="w-24 h-24 mx-auto rounded-full object-cover object-top shadow-lg"
            />
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
          onVerifiedGeneration={handleVerifiedGeneration}
          onPredictiveAnalysis={handlePredictiveAnalysis}
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

      {/* Verified Generation Dialog */}
      <VerifiedGenerationDialog
        open={verifiedDialogOpen}
        onOpenChange={setVerifiedDialogOpen}
        jobs={verifiedJobs}
      />

      {/* Predictive Analysis Dialog */}
      <PredictiveAnalysisDialog
        open={predictiveDialogOpen}
        onOpenChange={setPredictiveDialogOpen}
        jobs={predictiveJobs}
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

// Contextual suggestions based on query and response
function getContextualSuggestions(query?: string, response?: string, toolsUsed?: string[]): string[] {
  const queryLower = (query || '').toLowerCase()
  const responseLower = (response || '').toLowerCase()

  // If tools were used (documents found), suggest follow-up actions
  if (toolsUsed && toolsUsed.length > 0) {
    if (toolsUsed.some(t => t.includes('search') || t.includes('semantic'))) {
      return [
        '¿Puedes resumir los documentos encontrados?',
        'Analiza los riesgos de estos documentos',
        '¿Qué otros documentos están relacionados?',
      ]
    }
    if (toolsUsed.some(t => t.includes('analyze'))) {
      return [
        '¿Qué acciones recomiendas?',
        'Explica los riesgos en detalle',
        '¿Hay problemas de cumplimiento?',
      ]
    }
  }

  // Contract-related queries
  if (queryLower.includes('contrato') || queryLower.includes('contract')) {
    return [
      '¿Cuáles son las cláusulas más importantes?',
      'Identifica los riesgos del contrato',
      '¿Cuándo vence este contrato?',
    ]
  }

  // Count/list queries
  if (queryLower.includes('cuántos') || queryLower.includes('cuantos') || queryLower.includes('lista')) {
    return [
      'Muestra los más recientes',
      '¿Cuáles requieren atención?',
      'Filtra por fecha',
    ]
  }

  // Document analysis
  if (queryLower.includes('analiza') || queryLower.includes('revisa') || queryLower.includes('verifica')) {
    return [
      '¿Qué riesgos encontraste?',
      'Resume los puntos clave',
      '¿Cumple con la normativa?',
    ]
  }

  // If response mentions documents were not found
  if (responseLower.includes('no se encontraron') || responseLower.includes('no encontré')) {
    return [
      'Buscar con términos diferentes',
      '¿Qué documentos tengo disponibles?',
      'Ayúdame a reformular la búsqueda',
    ]
  }

  // Greeting/intro - suggest getting started
  if (queryLower.includes('hola') || queryLower.includes('me llamo') || queryLower.includes('buenos')) {
    return [
      '¿Cuántos documentos tengo?',
      'Muestra mis contratos recientes',
      '¿Qué puedes hacer por mí?',
    ]
  }

  // Default contextual suggestions
  return [
    '¿Puedes darme más detalles?',
    'Muestra documentos relacionados',
    '¿Qué más puedo preguntarte?',
  ]
}
