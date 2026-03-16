'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { flushSync } from 'react-dom'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { useApiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'
import { useEmmaService, classifyError, EmmaStreamEvent } from '@/lib/services/emma.service'
import { queryVerifiedStream, mapEventToClaim, VerifiedStreamEvent, recoverVerifiedSession, submitReviewAndResume, ReviewDecision } from '@/lib/services/verified-generation.service'
import { queryPredictiveStream, PredictiveStreamEvent } from '@/lib/services/predictive-analysis.service'
import { EmmaQueryInput } from './EmmaQueryInput'
import { EmmaRenderChat } from './EmmaRenderChat'
import { HITLReviewCard } from './HITLReviewCard'
import { PDFPreviewModal } from './PDFPreviewModal'
import { useVerifiedGeneration } from '@/contexts/verified-generation-context'
import { EmmaMessage, WorkflowStep, EmmaChatProps, DocumentInfo, Attachment, SLMThinkingStep, VerifiedClaimInfo, VerifiedGenerationMetadata, PredictiveFactorInfo, PredictiveAnalysisMetadata, HITLReviewRequest, HITLDecision, ForgeMetadata } from '@/lib/types/emma'
import { isDocGenResult, extractDocGenMetadata } from '@/lib/utils/docgen-detector'
import { isForgeResult, extractForgeMetadata } from '@/lib/utils/forge-detector'
import { getSessionInfo } from '@/lib/services/forge.service'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { IconBrain, IconBolt } from '@tabler/icons-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ArtifactsPanel, ArtifactTab } from './ArtifactsPanel'
import { FileCheck, TrendingUp, Hammer, History } from 'lucide-react'
import { VerifiedGenTab } from './artifacts/VerifiedGenTab'
import { PredictiveTab } from './artifacts/PredictiveTab'
import { ForgeTab } from './artifacts/ForgeTab'
import { EmmaStreamProvider, useEmmaStream } from './EmmaStreamProvider'
import { BranchSwitcher } from './messages/BranchSwitcher'
import { CommandBar } from './messages/CommandBar'
import { ThreadHistory } from './ThreadHistory'
import type { Message as SDKMessage } from '@langchain/langgraph-sdk'

const USE_LANGGRAPH_PROTOCOL = process.env.NEXT_PUBLIC_LANGGRAPH_PROTOCOL === 'true'

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

/**
 * Helper to process SSE events from a resume stream (clarification or HITL decision).
 * Extracted to share between handleClarificationResume and handleHITLDecision.
 */
async function processResumeEvents(
  generator: AsyncGenerator<EmmaStreamEvent, void, unknown>,
  progressMessageId: string,
  updateMessagesFn: (updater: (prev: EmmaMessage[]) => EmmaMessage[], immediate?: boolean) => void,
): Promise<{ streamCompleted: boolean }> {
  let streamedAnswer = ''
  let slmThinkingSteps: SLMThinkingStep[] = []
  let streamCompleted = false

  for await (const event of generator) {
    const data = (event.data || {}) as Record<string, any>

    // Token streaming
    if (event.event === 'token' && data.text) {
      streamedAnswer += data.text
      updateMessagesFn(
        (prev) =>
          prev.map((msg) =>
            msg.id === progressMessageId
              ? {
                  ...msg,
                  metadata: {
                    ...msg.metadata,
                    isStreaming: true,
                    streaming_text: streamedAnswer,
                  },
                }
              : msg
          ),
        true
      )
      continue
    }

    // SLM thinking
    if (event.event === 'slm_thinking') {
      const inlineStepType = data.step_type || data.type
      if (inlineStepType) {
        const newStep: SLMThinkingStep = {
          step: typeof data.step === 'number' ? data.step : slmThinkingSteps.length + 1,
          type: inlineStepType as SLMThinkingStep['type'],
          content: data.content || data.message || '',
          detail: data.detail,
          confidence: data.confidence,
        }
        slmThinkingSteps = [...slmThinkingSteps, newStep]
        updateMessagesFn((prev) =>
          prev.map((msg) =>
            msg.id === progressMessageId
              ? {
                  ...msg,
                  content: data.message || msg.content,
                  metadata: {
                    ...msg.metadata,
                    slmIsThinking: data.slmIsThinking !== false,
                    slmThinkingSteps: [...slmThinkingSteps],
                  },
                }
              : msg
          )
        )
        continue
      }
    }

    // Completion
    if (event.event === 'complete') {
      streamCompleted = true
      const answerFromServer =
        typeof data.answer === 'string' && data.answer.trim()
          ? data.answer
          : data.final_result?.summary || null

      const apiSources = (data.final_result?.sources || data.sources || [])
        .map((src: any) => ({
          name: src.title || src.name || src.document_id || src.id || 'Fuente',
          id: src.document_id || src.id,
          url: src.url,
          boe_id: src.boe_id,
          graph_link: src.graph_link,
          source_type: src.source_type || src.type,
          fileType: src.file_type || src.mime_type,
          relevanceScore: src.score || src.relevance,
        }))
        .filter((s: any) => s.name && s.name !== 'Fuente')

      updateMessagesFn((prev) =>
        prev.map((msg) => {
          if (msg.id !== progressMessageId) return msg
          const finalContent =
            answerFromServer || msg.metadata?.streaming_text || msg.content || 'Analisis completado'
          const finalSlmSteps =
            slmThinkingSteps.length > 0 ? [...slmThinkingSteps] : msg.metadata?.slmThinkingSteps || []
          return {
            ...msg,
            type: 'result' as const,
            content: finalContent,
            isStreaming: false,
            documents: apiSources.length > 0 ? apiSources : undefined,
            suggestions: data.suggestions || data.final_result?.suggestions,
            metadata: {
              ...msg.metadata,
              progress: 100,
              isStreaming: false,
              streaming_text: undefined,
              slmIsThinking: false,
              slmThinkingSteps: finalSlmSteps,
            },
          }
        })
      )
      continue
    }

    // Error
    if (event.event === 'error') {
      streamCompleted = true
      updateMessagesFn((prev) =>
        prev.map((msg) =>
          msg.id === progressMessageId
            ? {
                ...msg,
                type: 'error' as const,
                content: data.message || 'Error procesando la respuesta.',
                isStreaming: false,
                metadata: { ...msg.metadata, isStreaming: false, slmIsThinking: false },
              }
            : msg
        )
      )
      continue
    }

    // Progress events
    if (!['complete', 'error', 'token', 'slm_thinking'].includes(event.event)) {
      updateMessagesFn((prev) =>
        prev.map((msg) =>
          msg.id === progressMessageId
            ? {
                ...msg,
                content: data.message || msg.content,
                metadata: {
                  ...msg.metadata,
                  progress: data.progress,
                  agent: data.agent,
                  ...(data.slmIsThinking !== undefined && { slmIsThinking: data.slmIsThinking }),
                },
              }
            : msg
        )
      )
    }
  }

  return { streamCompleted }
}

// ---- useStream helpers (only used when USE_LANGGRAPH_PROTOCOL === true) ----

/** Convert SDK Message[] to EmmaMessage[] for rendering */
function convertStreamMessages(sdkMessages: SDKMessage[]): EmmaMessage[] {
  return sdkMessages
    .filter((m): m is SDKMessage & { type: 'human' | 'ai' } =>
      m.type === 'human' || m.type === 'ai'
    )
    .map((m, i) => {
      const contentStr =
        typeof m.content === 'string'
          ? m.content
          : Array.isArray(m.content)
            ? m.content
                .filter((c): c is { type: 'text'; text: string } => (c as any).type === 'text')
                .map((c) => c.text)
                .join('')
            : ''
      return {
        id: m.id || `msg-${i}`,
        type: m.type === 'human' ? ('user' as const) : ('result' as const),
        content: contentStr,
        timestamp: new Date(),
      }
    })
}

function EmmaChatInner({
  className,
  initialQuery,
  messages: externalMessages,
  onMessagesChange,
  conversationId,
  useStreamMode,
}: EmmaChatProps & { useStreamMode?: boolean }) {
  const { user, tenantId, isAuthenticated, login } = useAuth()
  const { queryEmmaStream, resumeQueryStreamGenerator, uploadTempDocument } = useEmmaService()
  const apiClient = useApiClient()

  // --- useStream SDK integration (feature-flagged) ---
  // When useStreamMode is true, this component is wrapped in EmmaStreamProvider
  // so calling useEmmaStream() is safe. When false, we pass a dummy object.
  const stream = useStreamMode ? useEmmaStream() : null

  // Thread history sidebar (only in useStream mode)
  const [showThreadHistory, setShowThreadHistory] = useState(false)

  // Proactive welcome message from Emma (LLM-generated with user context)
  const [welcomeMessage, setWelcomeMessage] = useState<string>('')
  const [welcomeLoaded, setWelcomeLoaded] = useState(false)
  const welcomeFetchedRef = useRef(false)

  useEffect(() => {
    if (welcomeFetchedRef.current) return
    async function loadWelcome() {
      welcomeFetchedRef.current = true
      try {
        const res = await apiClient.get<{ message: string; personalized: boolean }>(
          API_CONFIG.ENDPOINTS.EMMA_WELCOME
        )
        if (res.data?.message) {
          setWelcomeMessage(res.data.message)
        }
      } catch {
        // Silently ignore — will show default welcome
      } finally {
        setWelcomeLoaded(true)
      }
    }
    if (isAuthenticated && user?.id) {
      loadWelcome()
    }
  }, [isAuthenticated, user?.id])

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

  const setIsLoading = useCallback((value: boolean) => {
    setIsLoadingInternal(value)
  }, [])
  const [deepReasoning, setDeepReasoning] = useState(false) // Fast mode by default

  // PDF Preview modal state
  const [previewDoc, setPreviewDoc] = useState<DocumentInfo | null>(null)
  const [showPreviewModal, setShowPreviewModal] = useState(false)

  // Verified generation queue state (from layout-level context — persists across navigation)
  const {
    jobs: verifiedJobs,
    jobsRef: verifiedJobsRef,
    updateJob: contextUpdateJob,
    setJob: contextSetJob,
    removeJob: contextRemoveJob,
    reviewHandler: contextReviewHandler,
  } = useVerifiedGeneration()

  // Predictive analysis queue state
  const [predictiveJobs, setPredictiveJobs] = useState<Record<string, PredictiveAnalysisMetadata>>({})
  const predictiveJobsRef = useRef<Record<string, PredictiveAnalysisMetadata>>({})

  // Artifacts panel state
  const [artifactsPanelOpen, setArtifactsPanelOpen] = useState(false)
  const [activeArtifactTab, setActiveArtifactTab] = useState<string | null>(null)

  // Forge metadata (latest forge result from messages)
  const [forgeMetadata, setForgeMetadata] = useState<ForgeMetadata | null>(null)

  // Retain uploaded file IDs across follow-up queries in the same session
  const sessionUploadIdsRef = useRef<string[]>([])
  const sessionDocIdRef = useRef<string | null>(null)
  const sessionIndexedDocIdsRef = useRef<string[]>([])

  // HITL: track pending clarification thread_id for interrupt() → Command(resume) flow
  const pendingClarificationRef = useRef<{ threadId: string; progressMessageId: string } | null>(null)

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

  // Recover verified generation session if user navigated away during generation
  useEffect(() => {
    if (typeof window === 'undefined' || !tenantId) return
    const raw = sessionStorage.getItem('verified_active_session')
    if (!raw) return

    let marker: { sessionId: string; topic: string }
    try { marker = JSON.parse(raw) } catch { sessionStorage.removeItem('verified_active_session'); return }

    // Avoid injecting duplicate
    if (messages.some(m => m.verified?.session_id === marker.sessionId)) {
      sessionStorage.removeItem('verified_active_session')
      return
    }

    recoverVerifiedSession(marker.sessionId).then(data => {
      if (!data) {
        sessionStorage.removeItem('verified_active_session')
        return
      }
      if (data.status === 'completed') {
        sessionStorage.removeItem('verified_active_session')
        updateMessages(prev => {
          if (prev.some(m => m.verified?.session_id === marker.sessionId)) return prev
          return [...prev, {
            id: `recovered_${Date.now()}`,
            type: 'verified_result' as const,
            content: data.document_text || '',
            timestamp: new Date(),
            verified: {
              session_id: data.session_id,
              tenant_id: tenantId,
              topic: data.topic || marker.topic,
              claims: data.claims || [],
              current_phase: 'complete' as const,
              verified_count: data.verified_count || 0,
              rejected_count: data.rejected_count || 0,
              total_claims: data.total_claims || 0,
              document_text: data.document_text,
              execution_time_ms: data.execution_time_ms,
              average_confidence: data.average_confidence,
              sources: data.sources,
              doi_validations: data.doi_validations,
              source_filenames: data.source_filenames,
              source_summary: data.source_summary,
            },
          }]
        })
      }
      // If still running, leave marker for next mount
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId])

  // Consume completed verified generation jobs from layout-level context.
  // This effect fires when a job completes (either while on this page or after navigating back).
  // It injects the result into chat messages and cleans up context + sessionStorage.
  useEffect(() => {
    const completedEntries = Object.entries(verifiedJobs).filter(
      ([, job]) => job.current_phase === 'complete'
    )
    if (completedEntries.length === 0) return

    for (const [jobId, job] of completedEntries) {
      updateMessages(prev => {
        // Avoid duplicates
        if (prev.some(m => m.id === jobId)) return prev
        return [...prev, {
          id: jobId,
          type: 'verified_result' as const,
          content: job.document_text || '',
          timestamp: new Date(),
          verified: job,
        }]
      })
      contextRemoveJob(jobId)
      // Clear recovery marker now that the result is safely in messages
      sessionStorage.removeItem('verified_active_session')
    }
  }, [verifiedJobs, updateMessages, contextRemoveJob])

  // Handle sending queries
  const handleSendQuery = useCallback(
    async (query: string, attachments?: Attachment[]) => {
      // Use ref to check loading state (prevents stale closure issues)
      if (!user?.id || !tenantId || isLoadingRef.current) {
        return
      }

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
          sessionDocIdRef.current = attachmentContext.document_id as string | null
          sessionIndexedDocIdsRef.current = attachmentContext.indexed_document_ids as string[]
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
              user_name: user.full_name || user.email?.split('@')[0] || '',
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
              const inlineStepType = data.step_type || (data as any).type
              if (inlineStepType && !data.slmThinkingStep) {
                // Normalize inline step into SLMThinkingStep
                const newStep: SLMThinkingStep = {
                  step: typeof data.step === 'number' ? data.step : slmThinkingSteps.length + 1,
                  type: inlineStepType as SLMThinkingStep['type'],
                  content: data.content || data.message || '',
                  detail: (data as any).detail,
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

            // Handle clarification event — LangGraph interrupt() HITL
            // Graph is paused; user selects an option → resume via Command(resume=value)
            if (event.event === 'clarification') {
              streamCompleted = true
              const question = data.question || data.message || ''
              const options = (data.options || []) as Array<{ label: string; value: string }>
              const threadId = (data as any).thread_id as string | undefined

              // Store thread_id so handleSuggestionClick can resume the paused graph
              if (threadId) {
                pendingClarificationRef.current = { threadId, progressMessageId }
              }

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        type: 'clarification' as const,
                        content: question,
                        isStreaming: false,
                        metadata: {
                          ...msg.metadata,
                          isStreaming: false,
                          slmIsThinking: false,
                          clarification: {
                            question,
                            options: options.map((o) => ({
                              label: o.label,
                              value: o.value,
                            })),
                          },
                        },
                      }
                    : msg
                )
              )
              setIsLoading(false)
              return
            }

            // Handle HITL review event (Approve/Edit/Reject for tool calls)
            if (event.event === 'hitl_review') {
              streamCompleted = true
              const hitlData = data as unknown as HITLReviewRequest
              const threadId = (data as any).thread_id as string | undefined

              // Store pending review for resume (same ref as clarification)
              if (threadId) {
                pendingClarificationRef.current = {
                  threadId,
                  progressMessageId,
                }
              }

              updateMessages((prev) =>
                prev.map((msg) =>
                  msg.id === progressMessageId
                    ? {
                        ...msg,
                        type: 'clarification' as const,
                        content: hitlData.action_request?.description || hitlData.action_request?.name || 'Accion pendiente de revision',
                        isStreaming: false,
                        metadata: {
                          ...msg.metadata,
                          isStreaming: false,
                          slmIsThinking: false,
                          hitl_review: hitlData,
                        },
                      }
                    : msg
                )
              )
              setIsLoading(false)
              return
            }

            // Handle other progress events (progress, start, delegation, first_token, etc.)
            // Also handles slm_reasoning and slm_executing stages via progress events
            if (
              !['plan_created', 'step_start', 'step_complete', 'step_error', 'complete', 'error', 'token', 'slm_thinking', 'slm_plan', 'clarification', 'hitl_review'].includes(
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
                          // LangGraph reasoning fields from progress events
                          ...(data.slmIsThinking !== undefined && { slmIsThinking: data.slmIsThinking }),
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

              // If this is a clarification complete, skip — already handled by clarification event
              if ((data as any).query_clarification) {
                setIsLoading(false)
                return
              }
              // Use data.answer if provided, otherwise preserve accumulated content from tokens
              const answerFromServer =
                typeof data.answer === 'string' && data.answer.trim()
                  ? data.answer
                  : (data.final_result as any)?.summary || null

              // Build documents array from attachments (with real names)
              // These are the documents the user attached for analysis
              const attachmentDocs = attachments?.map((a) => ({
                name: a.name,
                id: a.type === 'indexed' ? a.documentId : a.id,
                fileType: a.fileType,
              })) || []

              // Extract sources from API response (includes graph_link for BOE legislation)
              const apiSources = ((data.final_result as any)?.sources || (data as any).sources || [])
                .map((src: any) => ({
                  name: src.title || src.name || src.document_id || src.id || 'Fuente',
                  id: src.document_id || src.id,
                  url: src.url,
                  boe_id: src.boe_id,
                  graph_link: src.graph_link,
                  source_type: src.source_type || src.type,
                  fileType: src.file_type || src.mime_type,
                  relevanceScore: src.score || src.relevance,
                }))
                .filter((s: any) => s.name && s.name !== 'Fuente')

              // Combine: API sources first (more relevant), then attachments
              const documentSources = [...apiSources, ...attachmentDocs]

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

                  // Detect forge_document tool result
                  if (isForgeResult({
                    content: finalContent,
                    toolsUsed: (data.final_result as any)?.tools_used,
                  })) {
                    const forgeMeta = extractForgeMetadata(finalContent, data.execution_time_ms)
                    if (forgeMeta) {
                      // Capture forge metadata for artifacts panel
                      setForgeMetadata(forgeMeta)
                      if (!artifactsPanelOpen) {
                        setArtifactsPanelOpen(true)
                        setActiveArtifactTab('forge')
                      }

                      // Enrich with full session data via API (fire-and-forget)
                      getSessionInfo(forgeMeta.session_id).then(resp => {
                        if (resp.data) {
                          const enriched: ForgeMetadata = {
                            ...forgeMeta,
                            fields: resp.data!.fields,
                            source_title: resp.data!.source_title || forgeMeta.source_title,
                            document_type: resp.data!.document_type || forgeMeta.document_type,
                            confidence: resp.data!.confidence || forgeMeta.confidence,
                            outputs: resp.data!.outputs,
                            status: resp.data!.status as any,
                          }
                          // Update artifacts panel with enriched data
                          setForgeMetadata(enriched)
                          // Update message in place with enriched data
                          updateMessages(prev => prev.map(m =>
                            m.id === msg.id ? {
                              ...m,
                              forge: enriched,
                            } : m
                          ))
                        }
                      })

                      return {
                        ...msg,
                        type: 'forge_result' as const,
                        content: finalContent,
                        forge: forgeMeta,
                        metadata: {
                          processing_time: data.execution_time_ms,
                          execution_time_ms: data.execution_time_ms,
                          tools_used: (data.final_result as any)?.tools_used || [],
                          slmThinkingSteps: finalSlmSteps.length > 0 ? finalSlmSteps : undefined,
                          slmIsThinking: false,
                          isStreaming: false,
                        },
                        suggestions: finalSuggestions,
                      }
                    }
                  }

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

  // useStream-based submit handler (feature-flagged path)
  function handleSendQueryViaStream(query: string) {
    if (!stream || !user?.id || !tenantId) return
    stream.submit(
      { messages: [{ type: 'human' as const, content: query }] },
      {
        streamMode: ['values'],
        config: {
          configurable: {
            user_id: user.id,
            tenant_id: tenantId,
            deep_reasoning: deepReasoning,
          },
        },
      }
    )
  }

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

      // Helper to update this job in the queue (delegates to context)
      const jobId = verifiedMessageId
      const updateJob = (updater: (prev: VerifiedGenerationMetadata) => VerifiedGenerationMetadata) => {
        contextUpdateJob(jobId, updater)
      }
      const removeJob = () => {
        contextRemoveJob(jobId)
      }

      // Add job to queue and open artifacts panel
      contextSetJob(jobId, initialVerified)
      setArtifactsPanelOpen(true)
      setActiveArtifactTab('verified')

      // Mark active session for recovery if user navigates away
      sessionStorage.setItem('verified_active_session', JSON.stringify({
        sessionId, topic, startedAt: new Date().toISOString(),
      }))

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
            // Don't clear verified_active_session here — the consumption effect
            // will clear it after successfully injecting into messages.
            // This ensures recoverability if the tab is closed before consumption.

            // Capture accumulated claims before updating job
            const jobClaims = verifiedJobsRef.current[jobId]?.claims || []

            // Recompute stats from actual claims array (backend counts may include regenerated claims)
            const finalVerifiedCount = jobClaims.filter((c: VerifiedClaimInfo) => c.status === 'verified').length
            const finalCorrectedCount = jobClaims.filter((c: VerifiedClaimInfo) => c.status === 'corrected').length
            const finalRejectedCount = jobClaims.filter((c: VerifiedClaimInfo) => c.status === 'rejected').length

            // Mark job as complete in context (don't remove — effect will inject into messages)
            // This works even if EmmaChat is unmounted because context lives at layout level
            updateJob((prev) => ({
              ...prev,
              claims: jobClaims,
              current_phase: 'complete' as const,
              document_text: event.data.document_text,
              verified_count: finalVerifiedCount + finalCorrectedCount,
              rejected_count: finalRejectedCount,
              total_claims: jobClaims.length,
              execution_time_ms: event.data.execution_time_ms,
              average_confidence: event.data.average_confidence,
              sources: event.data.sources,
              doi_validations: event.data.doi_validations,
              source_filenames: event.data.source_filenames,
              source_summary: event.data.source_summary,
            }))
            return
          }

          // HITL: Backend requests human review before document assembly
          if (event.event_type === 'review_requested') {
            const reviewData = event.data
            const reviewClaims = (reviewData.claims || []) as Array<{
              claim_id: string; claim_text: string; confidence: number;
              status: string; verification_type?: string;
              verification_reason?: string; needs_review: boolean;
            }>

            // Update job claims with review flags and transition to review phase
            updateJob((prev) => {
              const updatedClaims = prev.claims.map(c => {
                const reviewInfo = reviewClaims.find(rc => rc.claim_id === c.claim_id)
                if (reviewInfo) {
                  return {
                    ...c,
                    needs_review: reviewInfo.needs_review,
                    auto_approved: !reviewInfo.needs_review,
                  }
                }
                return { ...c, auto_approved: true }
              })
              return {
                ...prev,
                claims: updatedClaims,
                current_phase: 'review' as const,
                needs_review_count: reviewData.needs_review_count || 0,
                confidence_threshold: reviewData.confidence_threshold,
              }
            })
            // SSE stream ends after this event — don't return, let the
            // stream close naturally. The review UI is shown in the widget.
            return
          }

          if (event.event_type === 'error') {
            sessionStorage.removeItem('verified_active_session')
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
                  evidence_sources: claimUpdate.evidence_sources,
                  verification_type: claimUpdate.verification_type,
                  verification_reason: claimUpdate.verification_reason,
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

  // Handle HITL review submission — resume verified generation after human review
  const handleReviewSubmit = useCallback(
    async (jobId: string, decisions: ReviewDecision[]) => {
      if (!tenantId) return

      const job = verifiedJobsRef.current[jobId]
      if (!job) return

      // Mark as resuming (shows loading state)
      contextUpdateJob(jobId, (prev) => ({
        ...prev,
        current_phase: 'verifying' as const,
      }))

      try {
        for await (const event of submitReviewAndResume(
          job.session_id,
          tenantId,
          decisions,
        )) {
          if (event.event_type === 'document_complete') {
            const jobClaims = verifiedJobsRef.current[jobId]?.claims || []
            // Filter out rejected claims (they were removed from Redis)
            const remainingClaims = jobClaims.filter(c => {
              const dec = decisions.find(d => d.claim_id === c.claim_id)
              return !dec || dec.action !== 'reject'
            }).map(c => {
              // Update edited claims
              const dec = decisions.find(d => d.claim_id === c.claim_id)
              if (dec?.action === 'edit' && dec.edited_text) {
                return { ...c, claim_text: dec.edited_text, status: 'corrected' as const, original_text: c.claim_text }
              }
              return c
            })

            const finalVerifiedCount = remainingClaims.filter(c => c.status === 'verified').length
            const finalCorrectedCount = remainingClaims.filter(c => c.status === 'corrected').length
            const finalRejectedCount = decisions.filter(d => d.action === 'reject').length

            contextUpdateJob(jobId, (prev) => ({
              ...prev,
              claims: remainingClaims,
              current_phase: 'complete' as const,
              document_text: event.data.document_text,
              verified_count: finalVerifiedCount + finalCorrectedCount,
              rejected_count: finalRejectedCount,
              total_claims: remainingClaims.length,
              execution_time_ms: event.data.execution_time_ms,
              average_confidence: event.data.average_confidence,
              sources: event.data.sources,
              doi_validations: event.data.doi_validations,
              source_filenames: event.data.source_filenames,
              source_summary: event.data.source_summary,
              needs_review_count: 0,
            }))
            return
          }

          if (event.event_type === 'error') {
            console.error('[VerifiedGen/Resume] Error:', event.data.error)
            contextUpdateJob(jobId, (prev) => ({
              ...prev,
              current_phase: 'review' as const,
            }))
            return
          }
        }
      } catch (err) {
        console.error('[VerifiedGen/Resume] Failed:', err)
        // Restore review phase so user can retry
        contextUpdateJob(jobId, (prev) => ({
          ...prev,
          current_phase: 'review' as const,
        }))
      }
    },
    [tenantId, verifiedJobsRef, contextUpdateJob]
  )

  // Register HITL review handler in context so the floating widget can call it
  useEffect(() => {
    contextReviewHandler.current = handleReviewSubmit
    return () => { contextReviewHandler.current = null }
  }, [handleReviewSubmit, contextReviewHandler])

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
        setArtifactsPanelOpen(true)
        setActiveArtifactTab('predictive')

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
                sources: event.data.sources,
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
                  factorUpdate.supporting_matches = event.data.supporting_matches
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

  // Handle clarification resume — continues paused LangGraph via Command(resume=value)
  const handleClarificationResume = useCallback(
    async (selectedValue: string) => {
      const pending = pendingClarificationRef.current
      if (!pending || !user?.id || !tenantId) return

      pendingClarificationRef.current = null // Clear — only resume once
      const { threadId } = pending

      // Add user message showing what they selected
      const userMessage: EmmaMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: selectedValue,
        timestamp: new Date(),
      }
      updateMessages((prev) => [...prev, userMessage])

      // Create a new progress message for resume stream
      const resumeProgressId = (Date.now() + 1).toString()
      const resumeProgress: EmmaMessage = {
        id: resumeProgressId,
        type: 'progress',
        content: 'Procesando tu seleccion...',
        timestamp: new Date(),
        metadata: { progress: 0, streaming_text: '' },
      }
      updateMessages((prev) => [...prev, resumeProgress])
      setIsLoading(true)
      setError(null)

      try {
        const { streamCompleted } = await processResumeEvents(
          resumeQueryStreamGenerator(threadId, selectedValue, tenantId, user.id),
          resumeProgressId,
          updateMessages,
        )
        if (!streamCompleted) {
          // Stream ended without complete/error — should not happen normally
        }
      } catch (err: any) {
        console.error('Clarification resume failed:', err)
        updateMessages((prev) =>
          prev.map((msg) =>
            msg.id === resumeProgressId
              ? {
                  ...msg,
                  type: 'error' as const,
                  content: 'Error al continuar la consulta. Por favor, intenta de nuevo.',
                  isStreaming: false,
                  metadata: { ...msg.metadata, isStreaming: false, slmIsThinking: false },
                }
              : msg
          )
        )
      } finally {
        setIsLoading(false)
      }
    },
    [user, tenantId, resumeQueryStreamGenerator, updateMessages]
  )

  // Handle HITL review decision — sends Approve/Edit/Reject to resume the paused graph
  async function handleHITLDecision(messageId: string, decision: HITLDecision) {
    const pending = pendingClarificationRef.current
    if (!pending || !user?.id || !tenantId) return

    pendingClarificationRef.current = null
    const { threadId } = pending

    // Show decision in chat
    const decisionLabel =
      decision.type === 'approve' ? 'Aprobado'
        : decision.type === 'edit' ? 'Editado y enviado'
        : `Rechazado${decision.message ? `: ${decision.message}` : ''}`

    updateMessages((prev) =>
      prev.map((msg) =>
        msg.id === messageId
          ? { ...msg, type: 'info' as const, content: decisionLabel, metadata: { ...msg.metadata, hitl_review: undefined } }
          : msg
      )
    )

    // Create resume progress message
    const resumeProgressId = (Date.now() + 1).toString()
    updateMessages((prev) => [
      ...prev,
      {
        id: resumeProgressId,
        type: 'progress' as const,
        content: 'Procesando tu decision...',
        timestamp: new Date(),
        metadata: { progress: 0, streaming_text: '' },
      },
    ])
    setIsLoading(true)
    setError(null)

    // Resume graph with decision object
    try {
      await processResumeEvents(
        resumeQueryStreamGenerator(threadId, decision as unknown as Record<string, unknown>, tenantId, user.id),
        resumeProgressId,
        updateMessages,
      )
    } catch (error) {
      console.error('HITL resume failed:', error)
      updateMessages((prev) =>
        prev.map((msg) =>
          msg.id === resumeProgressId
            ? { ...msg, type: 'error' as const, content: 'Error procesando la decision', isStreaming: false }
            : msg
        )
      )
    } finally {
      setIsLoading(false)
    }
  }

  // Handle suggestion click — dispatches to resume flow if clarification is pending
  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      if (pendingClarificationRef.current) {
        handleClarificationResume(suggestion)
      } else {
        handleSendQuery(suggestion)
      }
    },
    [handleSendQuery, handleClarificationResume]
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

  // When useStream mode is active, messages come from the SDK stream
  const displayMessages = useStreamMode && stream
    ? convertStreamMessages(stream.messages)
    : messages

  // Derive loading state from stream when in useStream mode
  const displayIsLoading = useStreamMode && stream
    ? stream.isLoading
    : isLoading

  // Derive error from stream when in useStream mode
  const displayError = useStreamMode && stream && stream.error
    ? (stream.error instanceof Error ? stream.error.message : String(stream.error))
    : error

  const hasMessages = displayMessages.length > 0

  // Build artifact tabs from active jobs
  const artifactTabs: ArtifactTab[] = []

  if (Object.keys(verifiedJobs).length > 0) {
    const totalClaims = Object.values(verifiedJobs).reduce((sum, j) => sum + (j.total_claims || 0), 0)
    const verifiedCount = Object.values(verifiedJobs).reduce((sum, j) => sum + (j.verified_count || 0), 0)
    artifactTabs.push({
      id: 'verified',
      label: 'Verified Gen',
      icon: <FileCheck className="h-3.5 w-3.5" />,
      badge: totalClaims > 0 ? `${verifiedCount}/${totalClaims}` : undefined,
      content: (
        <VerifiedGenTab
          jobs={verifiedJobs}
          onSubmitReview={handleReviewSubmit}
        />
      ),
    })
  }

  if (Object.keys(predictiveJobs).length > 0) {
    artifactTabs.push({
      id: 'predictive',
      label: 'Predictive',
      icon: <TrendingUp className="h-3.5 w-3.5" />,
      content: <PredictiveTab jobs={predictiveJobs} />,
    })
  }

  if (forgeMetadata) {
    artifactTabs.push({
      id: 'forge',
      label: 'Document Forge',
      icon: <Hammer className="h-3.5 w-3.5" />,
      badge: forgeMetadata.fields?.length
        ? `${forgeMetadata.fields_filled || 0}/${forgeMetadata.fields.length}`
        : undefined,
      content: <ForgeTab metadata={forgeMetadata} />,
    })
  }

  // Effective send handler: routes to stream or SSE based on mode
  async function effectiveSendQuery(query: string, attachments?: Attachment[]) {
    if (useStreamMode && stream) {
      handleSendQueryViaStream(query)
      return
    }
    await handleSendQuery(query, attachments)
  }

  // Effective suggestion handler: routes to stream resume or existing logic
  function effectiveSuggestionClick(suggestion: string) {
    if (useStreamMode && stream) {
      handleSendQueryViaStream(suggestion)
      return
    }
    handleSuggestionClick(suggestion)
  }

  return (
    <div className={cn('flex h-full', className)}>
      {/* Thread History sidebar (useStream mode only) */}
      {useStreamMode && showThreadHistory && stream && (
        <ThreadHistory
          currentThreadId={null}
          onSelectThread={() => {
            // Thread switching is handled by the provider's onThreadId callback
          }}
          apiUrl="/api"
          tenantId={tenantId || ''}
        />
      )}

      {/* Chat area */}
      <div className="flex flex-1 flex-col min-w-0">
      {/* Chat messages */}
      {hasMessages && (
        <div className="flex-1 overflow-hidden min-h-0">
          <EmmaRenderChat
            messages={displayMessages}
            isLoading={displayIsLoading}
            error={displayError}
            onFeedback={handleFeedback}
            onSuggestionClick={effectiveSuggestionClick}
            onRetry={handleRetry}
            onDocumentClick={handleDocumentClick}
            onPreviewClick={handlePreviewClick}
            renderHITLReview={useStreamMode && stream?.interrupt
              ? (request, messageId) => {
                  // In useStream mode, render interrupt-based review
                  return (
                    <HITLReviewCard
                      request={request}
                      isLoading={stream.isLoading}
                      onSubmit={(decision) => {
                        stream.submit(undefined, { command: { resume: decision } })
                      }}
                    />
                  )
                }
              : (request, messageId) => (
                  <HITLReviewCard
                    request={request}
                    isLoading={false}
                    onSubmit={(decision) => handleHITLDecision(messageId, decision)}
                  />
                )
            }
            renderBranchSwitcher={useStreamMode && stream ? (msgId) => {
              const sdkMsg = stream.messages.find((m) => m.id === msgId)
              if (!sdkMsg) return null
              const meta = stream.getMessagesMetadata(sdkMsg)
              if (!meta) return null
              return (
                <BranchSwitcher
                  branch={meta.branch}
                  branchOptions={meta.branchOptions}
                  onSelect={(b) => stream.setBranch(b)}
                  isLoading={stream.isLoading}
                />
              )
            } : undefined}
            renderCommandBar={useStreamMode && stream ? (msgId, content) => (
              <CommandBar
                content={content}
                isLoading={stream.isLoading}
                onRegenerate={() => {
                  const sdkMsg = stream.messages.find((m) => m.id === msgId)
                  if (!sdkMsg) return
                  const meta = stream.getMessagesMetadata(sdkMsg)
                  if (meta?.firstSeenState?.parent_checkpoint) {
                    stream.submit(undefined, { checkpoint: meta.firstSeenState.parent_checkpoint })
                  }
                }}
              />
            ) : undefined}
          />
        </div>
      )}

      {/* Empty state — proactive welcome from Emma */}
      {!hasMessages && (
        <div className="flex-1 flex flex-col items-center justify-center p-8 min-h-[60vh]">
          <div className="text-center space-y-4 max-w-md">
            <img
              src="/emma-welcome.png"
              alt="Emma"
              className="w-24 h-24 mx-auto rounded-full object-cover object-top shadow-lg"
            />

            {/* Dynamic LLM-generated welcome or loading state */}
            {welcomeLoaded && welcomeMessage ? (
              <p className="text-lg text-foreground">{welcomeMessage}</p>
            ) : welcomeLoaded ? (
              <>
                <h2 className="text-2xl font-semibold">Hola, soy Emma</h2>
                <p className="text-muted-foreground">
                  Tu asistente de inteligencia empresarial. Puedo ayudarte a buscar,
                  analizar y entender tus documentos.
                </p>
              </>
            ) : (
              <p className="text-muted-foreground animate-pulse">Preparando tu sesión...</p>
            )}

            {/* Example prompts */}
            <div className="space-y-2 pt-4">
              <p className="text-sm text-muted-foreground font-medium">
                Prueba preguntarme:
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {EXAMPLE_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => effectiveSendQuery(prompt)}
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

      {/* Stream interrupt rendering (useStream mode only) */}
      {useStreamMode && stream?.interrupt && (
        <div className="border-t bg-amber-500/5 p-4">
          {stream.interrupt.value && typeof stream.interrupt.value === 'object' && (stream.interrupt.value as any).type === 'clarification' ? (
            <div className="space-y-2">
              <p className="text-sm text-foreground/90">{(stream.interrupt.value as any).question}</p>
              <div className="flex flex-wrap gap-2">
                {((stream.interrupt.value as any).options || []).map((opt: { label: string; value: string }, idx: number) => (
                  <button
                    key={idx}
                    onClick={() => stream.submit(undefined, { command: { resume: opt.value } })}
                    className="px-3 py-1.5 text-xs font-mono border border-amber-500/30 rounded hover:bg-amber-500/10"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <HITLReviewCard
              request={stream.interrupt.value as any}
              isLoading={stream.isLoading}
              onSubmit={(decision) => {
                stream.submit(undefined, { command: { resume: decision } })
              }}
            />
          )}
        </div>
      )}

      {/* Input */}
      <div className="border-t bg-background p-4">
        {/* Deep Reasoning Toggle + Thread History Toggle */}
        <TooltipProvider>
          <div className="flex items-center justify-end gap-2 mb-3">
            {/* Thread history toggle (useStream mode only) */}
            {useStreamMode && (
              <button
                onClick={() => setShowThreadHistory(!showThreadHistory)}
                className={cn(
                  'mr-auto flex items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors',
                  showThreadHistory
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <History className="h-3.5 w-3.5" />
                Historial
              </button>
            )}

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
                    disabled={displayIsLoading}
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
          onSendQuery={effectiveSendQuery}
          onVerifiedGeneration={handleVerifiedGeneration}
          onPredictiveAnalysis={handlePredictiveAnalysis}
          isLoading={displayIsLoading}
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

      {/* Artifacts Panel */}
      {artifactTabs.length > 0 && (
        <ArtifactsPanel
          tabs={artifactTabs}
          activeTabId={activeArtifactTab}
          onTabChange={setActiveArtifactTab}
          open={artifactsPanelOpen}
          onOpenChange={setArtifactsPanelOpen}
        />
      )}
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

// ---- Exported wrapper: conditionally wraps Inner in EmmaStreamProvider ----

export function EmmaChat(props: EmmaChatProps) {
  const { tenantId } = useAuth()
  const [streamThreadId, setStreamThreadId] = useState<string | null>(null)

  if (USE_LANGGRAPH_PROTOCOL) {
    return (
      <EmmaStreamProvider
        apiUrl="/api"
        threadId={streamThreadId}
        onThreadId={setStreamThreadId}
        tenantId={tenantId || ''}
      >
        <EmmaChatInner {...props} useStreamMode />
      </EmmaStreamProvider>
    )
  }

  return <EmmaChatInner {...props} />
}
