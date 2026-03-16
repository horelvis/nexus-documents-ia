'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { useApiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'
import { useEmmaService } from '@/lib/services/emma.service'
import { EmmaQueryInput } from './EmmaQueryInput'
import { EmmaRenderChat } from './EmmaRenderChat'
import { HITLReviewCard } from './HITLReviewCard'
import { PDFPreviewModal } from './PDFPreviewModal'
import {
  EmmaMessage,
  EmmaChatProps,
  DocumentInfo,
  Attachment,
} from '@/lib/types/emma'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { IconBrain, IconBolt } from '@tabler/icons-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ArtifactsPanel, ArtifactTab } from './ArtifactsPanel'
import { FileCheck, TrendingUp, Hammer, History } from 'lucide-react'
import { VerifiedGenTab } from './artifacts/VerifiedGenTab'
import { PredictiveTab } from './artifacts/PredictiveTab'
import { ForgeTab } from './artifacts/ForgeTab'
import { EmmaStreamProvider, useEmmaStream } from './EmmaStreamProvider'
import { BranchSwitcher } from './messages/BranchSwitcher'
import { CommandBar } from './messages/CommandBar'
import { ThreadHistory } from './ThreadHistory'

// Extracted hooks
import { useMessageConverter } from './hooks/useMessageConverter'
import { useStreamSubmit } from './hooks/useStreamSubmit'
import { useInterruptHandler } from './hooks/useInterruptHandler'

// Extracted handlers (side-feature SSE streams)
import { useVerifiedGenerationHandler } from './handlers/useVerifiedGeneration'
import { usePredictiveAnalysisHandler } from './handlers/usePredictiveAnalysis'
import { useForgeDetection } from './handlers/useForgeDetection'

// Example prompts
const EXAMPLE_PROMPTS = [
  '¿Cuántos documentos tengo?',
  'Resume los contratos activos',
  '¿Qué documentos vencen pronto?',
]

function EmmaChatInner({ className, initialQuery }: EmmaChatProps) {
  const { user, tenantId, isAuthenticated, login } = useAuth()
  const { uploadTempDocument } = useEmmaService()
  const apiClient = useApiClient()

  // ── Local state (must be declared before hooks that reference it) ──
  const [deepReasoning, setDeepReasoning] = useState(false)

  // ── useStream SDK integration (always active) ──
  const stream = useEmmaStream()

  // ── Core hooks ──
  const { messages: displayMessages } = useMessageConverter(
    stream.messages,
    stream.values,
    stream.isLoading,
  )
  const { submit } = useStreamSubmit(stream, {
    userId: user?.id,
    tenantId,
    deepReasoning,
    uploadTempDocument,
    onAuthError: login,
  })
  const { pendingInterrupt, handleResume } = useInterruptHandler(stream)
  const [showThreadHistory, setShowThreadHistory] = useState(false)
  const [previewDoc, setPreviewDoc] = useState<DocumentInfo | null>(null)
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [artifactsPanelOpen, setArtifactsPanelOpen] = useState(false)
  const [activeArtifactTab, setActiveArtifactTab] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // ── Session ID ──
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

  // ── Welcome message ──
  const [welcomeMessage, setWelcomeMessage] = useState<string>('')
  const [welcomeLoaded, setWelcomeLoaded] = useState(false)
  const welcomeFetchedRef = useRef(false)

  useEffect(() => {
    if (welcomeFetchedRef.current) return
    async function loadWelcome() {
      welcomeFetchedRef.current = true
      try {
        const res = await apiClient.get<{ message: string; personalized: boolean }>(
          API_CONFIG.ENDPOINTS.EMMA_WELCOME,
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

  // ── updateMessages helper for side-feature handlers ──
  // In useStream mode, side-features (verified/predictive) inject results
  // into the message list. We store these as "injected" messages that get
  // merged with the SDK-derived messages.
  const [injectedMessages, setInjectedMessages] = useState<EmmaMessage[]>([])
  const updateMessages = useCallback(
    (updater: (prev: EmmaMessage[]) => EmmaMessage[]) => {
      setInjectedMessages(updater)
    },
    [],
  )

  // Merge SDK messages + injected side-feature messages
  const allMessages = [...displayMessages, ...injectedMessages]

  // ── Side-feature handlers (own SSE streams) ──
  const { verifiedJobs, handleVerifiedGeneration, handleReviewSubmit } =
    useVerifiedGenerationHandler({
      userId: user?.id,
      tenantId,
      sessionId,
      uploadTempDocument,
      updateMessages,
      setError,
      setArtifactsPanelOpen,
      setActiveArtifactTab,
      onAuthError: login,
    })

  const { predictiveJobs, handlePredictiveAnalysis } = usePredictiveAnalysisHandler({
    userId: user?.id,
    tenantId,
    sessionId,
    uploadTempDocument,
    updateMessages,
    setError,
    setArtifactsPanelOpen,
    setActiveArtifactTab,
    onAuthError: login,
  })

  const { forgeMetadata, setForgeMetadata } = useForgeDetection(allMessages)

  // ── Derived state ──
  const displayIsLoading = stream.isLoading
  const displayError =
    stream.error
      ? stream.error instanceof Error
        ? stream.error.message
        : String(stream.error)
      : error
  const hasMessages = allMessages.length > 0

  // ── Event handlers ──
  const handleSendQuery = useCallback(
    async (query: string, attachments?: Attachment[]) => {
      await submit(query, attachments)
    },
    [submit],
  )

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      submit(suggestion)
    },
    [submit],
  )

  const handleRetry = useCallback(
    (failedQuery: string) => {
      submit(failedQuery)
    },
    [submit],
  )

  const handleFeedback = useCallback(
    (messageId: string, feedback: 'positive' | 'negative') => {
      console.log('Feedback:', messageId, feedback)
      // TODO: Send feedback to backend
    },
    [],
  )

  const handleDocumentClick = useCallback((doc: DocumentInfo) => {
    setPreviewDoc(doc)
    setShowPreviewModal(true)
  }, [])

  const handlePreviewClick = useCallback((doc: DocumentInfo) => {
    setPreviewDoc(doc)
    setShowPreviewModal(true)
  }, [])

  // Execute initial query
  useEffect(() => {
    if (initialQuery && user?.id && tenantId && allMessages.length === 0) {
      const timer = setTimeout(() => {
        submit(initialQuery)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [initialQuery, user?.id, tenantId, allMessages.length, submit])

  // ── Build artifact tabs ──
  const artifactTabs: ArtifactTab[] = []

  if (Object.keys(verifiedJobs).length > 0) {
    const totalClaims = Object.values(verifiedJobs).reduce(
      (sum, j) => sum + (j.total_claims || 0),
      0,
    )
    const verifiedCount = Object.values(verifiedJobs).reduce(
      (sum, j) => sum + (j.verified_count || 0),
      0,
    )
    artifactTabs.push({
      id: 'verified',
      label: 'Verified Gen',
      icon: <FileCheck className="h-3.5 w-3.5" />,
      badge: totalClaims > 0 ? `${verifiedCount}/${totalClaims}` : undefined,
      content: <VerifiedGenTab jobs={verifiedJobs} onSubmitReview={handleReviewSubmit} />,
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

  // ── Render ──
  return (
    <div className={cn('flex h-full', className)}>
      {/* Thread History sidebar */}
      {showThreadHistory && (
        <ThreadHistory
          currentThreadId={null}
          onSelectThread={() => {}}
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
              messages={allMessages}
              isLoading={displayIsLoading}
              error={displayError}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSuggestionClick}
              onRetry={handleRetry}
              onDocumentClick={handleDocumentClick}
              onPreviewClick={handlePreviewClick}
              renderHITLReview={(request, messageId) => (
                <HITLReviewCard
                  request={request}
                  isLoading={stream.isLoading}
                  onSubmit={(decision) => handleResume(decision)}
                />
              )}
              renderBranchSwitcher={(msgId) => {
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
              }}
              renderCommandBar={(msgId, content) => (
                <CommandBar
                  content={content}
                  isLoading={stream.isLoading}
                  onRegenerate={() => {
                    const sdkMsg = stream.messages.find((m) => m.id === msgId)
                    if (!sdkMsg) return
                    const meta = stream.getMessagesMetadata(sdkMsg)
                    if (meta?.firstSeenState?.parent_checkpoint) {
                      stream.submit(undefined, {
                        checkpoint: meta.firstSeenState.parent_checkpoint,
                      })
                    }
                  }}
                />
              )}
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
                <p className="text-muted-foreground animate-pulse">
                  Preparando tu sesión...
                </p>
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
          {/* Deep Reasoning Toggle + Thread History Toggle */}
          <TooltipProvider>
            <div className="flex items-center justify-end gap-2 mb-3">
              <button
                onClick={() => setShowThreadHistory(!showThreadHistory)}
                className={cn(
                  'mr-auto flex items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors',
                  showThreadHistory
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <History className="h-3.5 w-3.5" />
                Historial
              </button>

              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-2">
                    <IconBolt
                      className={cn(
                        'h-4 w-4 transition-colors',
                        !deepReasoning ? 'text-yellow-500' : 'text-muted-foreground',
                      )}
                    />
                    <Label
                      htmlFor="deep-reasoning"
                      className={cn(
                        'text-xs cursor-pointer select-none transition-colors',
                        !deepReasoning ? 'text-foreground' : 'text-muted-foreground',
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
                        'text-xs cursor-pointer select-none transition-colors',
                        deepReasoning ? 'text-foreground' : 'text-muted-foreground',
                      )}
                    >
                      Profundo
                    </Label>
                    <IconBrain
                      className={cn(
                        'h-4 w-4 transition-colors',
                        deepReasoning ? 'text-purple-500' : 'text-muted-foreground',
                      )}
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <p className="font-semibold mb-1">
                    {deepReasoning ? 'Modo Profundo' : 'Modo Rápido'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {deepReasoning
                      ? 'Análisis exhaustivo con razonamiento detallado. Ideal para contratos, cumplimiento y análisis legal.'
                      : 'Respuestas rápidas y directas. Ideal para búsquedas simples y consultas generales.'}
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>

          <EmmaQueryInput
            onSendQuery={handleSendQuery}
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

// ── Exported wrapper: wraps Inner in EmmaStreamProvider ──

export function EmmaChat(props: EmmaChatProps) {
  const { tenantId } = useAuth()
  const [streamThreadId, setStreamThreadId] = useState<string | null>(null)

  return (
    <EmmaStreamProvider
      threadId={streamThreadId}
      onThreadId={setStreamThreadId}
      tenantId={tenantId || ''}
    >
      <EmmaChatInner {...props} />
    </EmmaStreamProvider>
  )
}
