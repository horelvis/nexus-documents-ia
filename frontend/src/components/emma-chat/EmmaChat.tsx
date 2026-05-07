'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import { useEmmaService } from '@/lib/services/emma.service'
import { EmmaQueryInput } from './EmmaQueryInput'
import { EmmaRenderChat } from './EmmaRenderChat'
import { HITLReviewCard } from './HITLReviewCard'

import { EmmaWelcomeScreen } from './EmmaWelcomeScreen'
import { ChatToolbar } from './ChatToolbar'
import {
  EmmaMessage,
  EmmaChatProps,
  DocumentInfo,
  Attachment,
} from '@/lib/types/emma'
import { ArtifactsPanel } from './ArtifactsPanel'
import { FullscreenDocumentViewer } from './FullscreenDocumentViewer'
import { EmmaStreamProvider, useEmmaStream } from './EmmaStreamProvider'
import { BranchSwitcher } from './messages/BranchSwitcher'
import { CommandBar } from './messages/CommandBar'

// Extracted hooks
import { useMessageConverter } from './hooks/useMessageConverter'
import { useStreamSubmit } from './hooks/useStreamSubmit'
import { useInterruptHandler } from './hooks/useInterruptHandler'
import { useArtifactTabs } from './hooks/useArtifactTabs'

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
  const { user, login } = useAuth()
  const { uploadTempDocument } = useEmmaService()

  // ── Local state ──
  const [deepReasoning, setDeepReasoning] = useState(false)
  const [fullscreenDoc, setFullscreenDoc] = useState<DocumentInfo | null>(null)
  const [artifactsPanelOpen, setArtifactsPanelOpen] = useState(false)
  const [activeArtifactTab, setActiveArtifactTab] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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
    deepReasoning,
    uploadTempDocument,
    onAuthError: login,
  })
  const { pendingInterrupt, handleResume } = useInterruptHandler(stream)

  // ── Session ID ──
  const [sessionId] = useState(() => {
    if (typeof window !== 'undefined') {
      const storageKey = `emma_session_default`
      const stored = sessionStorage.getItem(storageKey)
      if (stored) return stored
      const newId = `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
      sessionStorage.setItem(storageKey, newId)
      return newId
    }
    return `session_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
  })

  // ── Injected messages from side-feature SSE streams ──
  const [injectedMessages, setInjectedMessages] = useState<EmmaMessage[]>([])

  // Merge SDK messages + injected side-feature messages (dedup by ID).
  // Stabilize reference to prevent useForgeDetection re-render cascade.
  const prevAllMessagesRef = useRef<EmmaMessage[]>([])
  const allMessages = (() => {
    const seen = new Set(displayMessages.map(m => m.id))
    const merged = [...displayMessages, ...injectedMessages.filter(m => !seen.has(m.id))]

    const prev = prevAllMessagesRef.current
    if (
      prev.length === merged.length &&
      prev.every((m, i) => m === merged[i])
    ) {
      return prev
    }
    prevAllMessagesRef.current = merged
    return merged
  })()

  // ── Side-feature handlers (own SSE streams) ──
  const { verifiedJobs, handleVerifiedGeneration, handleReviewSubmit } =
    useVerifiedGenerationHandler({
      userId: user?.id,
      sessionId,
      uploadTempDocument,
      updateMessages: setInjectedMessages,
      setError,
      setArtifactsPanelOpen,
      setActiveArtifactTab,
      onAuthError: login,
    })

  const { predictiveJobs, handlePredictiveAnalysis } = usePredictiveAnalysisHandler({
    userId: user?.id,
    sessionId,
    uploadTempDocument,
    updateMessages: setInjectedMessages,
    setError,
    setArtifactsPanelOpen,
    setActiveArtifactTab,
    onAuthError: login,
  })

  const { forgeMetadata } = useForgeDetection(allMessages)

  // ── Artifact tabs (extracted hook) ──
  const artifactTabs = useArtifactTabs({
    verifiedJobs,
    predictiveJobs,
    forgeMetadata,
    onSubmitReview: handleReviewSubmit,
  })

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
      setInjectedMessages([])  // Clear stale side-feature messages from previous turn
      await submit(query, attachments)
    },
    [submit],
  )

  const handleOpenFullscreen = useCallback((doc: DocumentInfo) => {
    setFullscreenDoc(doc)
  }, [])

  const handleFeedback = useCallback(
    (messageId: string, feedback: 'positive' | 'negative') => {
      console.log('Feedback:', messageId, feedback)
      // TODO: Send feedback to backend
    },
    [],
  )

  // Execute initial query
  useEffect(() => {
    if (initialQuery && user?.id && allMessages.length === 0) {
      const timer = setTimeout(() => {
        submit(initialQuery)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [initialQuery, user?.id, allMessages.length, submit])

  // ── Render ──
  // ``stream.isThreadLoading`` is true while the SDK is fetching the
  // initial thread state from ``GET /api/threads/<id>/history`` after
  // the user opens an old conversation. The fetch can take ~1–2s
  // depending on checkpoint size; without a loader the chat looks
  // frozen on the welcome screen.
  const isHydrating = stream.isThreadLoading && !hasMessages

  return (
    <div className={cn('flex h-full', className)}>
      {/* Chat area */}
      <div className="flex flex-1 flex-col min-w-0">
        {isHydrating ? (
          <div className="flex-1 overflow-hidden min-h-0">
            <div
              className="max-w-3xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6 space-y-6"
              aria-busy="true"
              aria-label="Cargando conversación"
            >
              {/* User bubble — aligned right */}
              <div className="flex justify-end">
                <div className="max-w-[70%] space-y-2">
                  <div className="h-3.5 bg-primary/15 rounded-md animate-pulse w-48" />
                  <div className="h-3.5 bg-primary/15 rounded-md animate-pulse w-32" />
                </div>
              </div>

              {/* AI bubble — aligned left, longer */}
              <div className="flex justify-start gap-3">
                <div className="h-7 w-7 rounded-full bg-muted animate-pulse shrink-0" />
                <div className="flex-1 max-w-[80%] space-y-2">
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-3/4" />
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-full" />
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-5/6" />
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-2/3" />
                </div>
              </div>

              {/* User bubble — short */}
              <div className="flex justify-end">
                <div className="max-w-[70%] space-y-2">
                  <div className="h-3.5 bg-primary/15 rounded-md animate-pulse w-40" />
                </div>
              </div>

              {/* AI bubble — second */}
              <div className="flex justify-start gap-3">
                <div className="h-7 w-7 rounded-full bg-muted animate-pulse shrink-0" />
                <div className="flex-1 max-w-[80%] space-y-2">
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-full" />
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-4/5" />
                  <div className="h-3.5 bg-muted rounded-md animate-pulse w-3/5" />
                </div>
              </div>
            </div>
          </div>
        ) : hasMessages ? (
          <div className="flex-1 overflow-hidden min-h-0">
            <EmmaRenderChat
              messages={allMessages}
              isLoading={displayIsLoading}
              error={displayError}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSendQuery}
              onRetry={handleSendQuery}
              onOpenFullscreen={handleOpenFullscreen}
              renderHITLReview={(request) => (
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
        ) : (
          <EmmaWelcomeScreen
            onSendQuery={handleSendQuery}
            examplePrompts={EXAMPLE_PROMPTS}
          />
        )}

        {/* Input — centered to match message column */}
        <div className="border-t border-border/30 bg-background/80 backdrop-blur-sm px-4 sm:px-6 lg:px-8 py-3">
          <div className="max-w-4xl mx-auto w-full">
            <ChatToolbar
              deepReasoning={deepReasoning}
              onDeepReasoningChange={setDeepReasoning}
              isLoading={displayIsLoading}
            />

            <EmmaQueryInput
              onSendQuery={handleSendQuery}
              onVerifiedGeneration={handleVerifiedGeneration}
              onPredictiveAnalysis={handlePredictiveAnalysis}
              onStop={stream.stop}
              isLoading={displayIsLoading}
              disabled={!user?.id}
              placeholder="Pregúntame sobre tus documentos..."
              maxAttachments={10}
            />
          </div>
        </div>


      </div>

      {/* Fullscreen document viewer overlay */}
      {fullscreenDoc && (
        <FullscreenDocumentViewer
          document={fullscreenDoc}
          onClose={() => setFullscreenDoc(null)}
        />
      )}

      {/* Artifacts Panel — visible when there are tabs */}
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
  // Initialise from the parent-provided conversationId so opening an old
  // thread from the sidebar hydrates state via the LangGraph SDK
  // (fetchStateHistory: true). Without this, the prop was ignored and
  // the chat always started a fresh thread.
  const [streamThreadId, setStreamThreadId] = useState<string | null>(
    props.conversationId ?? null,
  )

  // Sync external selection → SDK. When the parent flips conversationId
  // (sidebar click, "New conversation"), reflect it on the stream.
  useEffect(() => {
    if ((props.conversationId ?? null) !== streamThreadId) {
      setStreamThreadId(props.conversationId ?? null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.conversationId])

  // ``useStream`` from @langchain/langgraph-sdk only fetches the thread
  // state during mount; subsequent changes to its ``threadId`` prop do
  // NOT re-fetch. We force a remount with a key tied to the active
  // thread, so opening a new conversation from the sidebar triggers
  // a fresh hydration including the persisted message history.
  return (
    <EmmaStreamProvider
      key={streamThreadId ?? 'new-thread'}
      threadId={streamThreadId}
      onThreadId={setStreamThreadId}
    >
      <EmmaChatInner {...props} />
    </EmmaStreamProvider>
  )
}
