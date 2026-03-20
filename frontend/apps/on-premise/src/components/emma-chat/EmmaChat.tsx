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
import { EmmaStreamProvider, useEmmaStream } from './EmmaStreamProvider'
import { BranchSwitcher } from './messages/BranchSwitcher'
import { CommandBar } from './messages/CommandBar'
import { ThreadHistory } from './ThreadHistory'

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
  const { user, tenantId, login } = useAuth()
  const { uploadTempDocument } = useEmmaService()

  // ── Local state ──
  const [deepReasoning, setDeepReasoning] = useState(false)
  const [showThreadHistory, setShowThreadHistory] = useState(false)
  const [previewDoc, setPreviewDoc] = useState<DocumentInfo | null>(null)
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
    tenantId,
    deepReasoning,
    uploadTempDocument,
    onAuthError: login,
  })
  const { pendingInterrupt, handleResume } = useInterruptHandler(stream)

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
      prev.every((m, i) => m.id === merged[i].id && m.content === merged[i].content)
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
      tenantId,
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
    tenantId,
    sessionId,
    uploadTempDocument,
    updateMessages: setInjectedMessages,
    setError,
    setArtifactsPanelOpen,
    setActiveArtifactTab,
    onAuthError: login,
  })

  const { forgeMetadata } = useForgeDetection(allMessages)

  // ── Close preview helper ──
  const handleClosePreview = useCallback(() => {
    setPreviewDoc(null)
  }, [])

  // ── Artifact tabs (extracted hook) ──
  const artifactTabs = useArtifactTabs({
    verifiedJobs,
    predictiveJobs,
    forgeMetadata,
    onSubmitReview: handleReviewSubmit,
    previewDoc,
    onClosePreview: handleClosePreview,
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

  const handleDocumentClick = useCallback((doc: DocumentInfo) => {
    setPreviewDoc(doc)
    setArtifactsPanelOpen(true)
    setActiveArtifactTab('preview')
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
    if (initialQuery && user?.id && tenantId && allMessages.length === 0) {
      const timer = setTimeout(() => {
        submit(initialQuery)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [initialQuery, user?.id, tenantId, allMessages.length, submit])

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
        {hasMessages ? (
          <div className="flex-1 overflow-hidden min-h-0">
            <EmmaRenderChat
              messages={allMessages}
              isLoading={displayIsLoading}
              error={displayError}
              onFeedback={handleFeedback}
              onSuggestionClick={handleSendQuery}
              onRetry={handleSendQuery}
              onDocumentClick={handleDocumentClick}
              onPreviewClick={handleDocumentClick}
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

        {/* Input */}
        <div className="border-t bg-background p-4">
          <ChatToolbar
            deepReasoning={deepReasoning}
            onDeepReasoningChange={setDeepReasoning}
            showThreadHistory={showThreadHistory}
            onToggleThreadHistory={() => setShowThreadHistory(prev => !prev)}
            isLoading={displayIsLoading}
          />

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


      </div>

      {/* Artifacts Panel — visible when there are tabs (including preview) */}
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
