'use client'

import { useRef, useEffect, useState } from 'react'
import { IconAlertCircle, IconThumbUp, IconThumbDown, IconRotate, IconCircleCheck, IconPaperclip, IconSearch, IconBulb, IconGitBranch, IconArrowRight, IconHelpCircle, IconDownload, IconFileText } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { EmmaMessage, WorkflowStep, DocumentInfo, SLMThinkingStep, ReasoningStep, ClarificationData } from '@/lib/types/emma'
import { EmmaMarkdown } from './EmmaMarkdown'
import { DocumentDisplay } from './DocumentDisplay'
import { ReasoningCollapsible } from './ReasoningCollapsible'
import { VerifiedDocumentResult } from './VerifiedDocumentResult'
import { PredictionResult } from './PredictionResult'
import { DocGenResult } from './DocGenResult'
import { ForgeResult } from './ForgeResult'

interface EmmaRenderChatProps {
  messages: EmmaMessage[]
  isLoading?: boolean
  error?: string | null
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
  className?: string
  /** Show terminal-style header with traffic lights */
  showTerminalHeader?: boolean
}

export function EmmaRenderChat({
  messages,
  isLoading = false,
  error = null,
  onFeedback,
  onSuggestionClick,
  onRetry,
  onDocumentClick,
  onPreviewClick,
  className,
  showTerminalHeader = false,
}: EmmaRenderChatProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const prevMessageCountRef = useRef(0)
  const isUserNearBottomRef = useRef(true)

  // Check if user is near bottom of scroll area
  const checkIfNearBottom = () => {
    const scrollArea = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (!scrollArea) return true
    const threshold = 150 // pixels from bottom
    return scrollArea.scrollHeight - scrollArea.scrollTop - scrollArea.clientHeight < threshold
  }

  // Track scroll position
  useEffect(() => {
    const scrollArea = scrollRef.current?.querySelector('[data-radix-scroll-area-viewport]')
    if (!scrollArea) return

    const handleScroll = () => {
      isUserNearBottomRef.current = checkIfNearBottom()
    }

    scrollArea.addEventListener('scroll', handleScroll, { passive: true })
    return () => scrollArea.removeEventListener('scroll', handleScroll)
  }, [])

  // Auto-scroll only when:
  // 1. New messages are added (not just updated)
  // 2. User is already near the bottom (hasn't scrolled up to read)
  useEffect(() => {
    const messageCount = messages.length
    const isNewMessage = messageCount > prevMessageCountRef.current
    prevMessageCountRef.current = messageCount

    // Only auto-scroll for new messages when user is near bottom
    if (isNewMessage && isUserNearBottomRef.current) {
      // Use requestAnimationFrame to ensure DOM has updated
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      })
    }
  }, [messages.length]) // Only trigger on message count change, not content updates

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Optional Terminal-style header */}
      {showTerminalHeader && (
        <div className="flex items-center gap-3 px-4 py-2 bg-card/50 border-b border-border/30">
          {/* Traffic lights */}
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-red-500/80" />
            <span className="h-3 w-3 rounded-full bg-yellow-500/80" />
            <span className="h-3 w-3 rounded-full bg-green-500/80" />
          </div>
          <span className="text-xs font-mono text-muted-foreground">
            emma-orchestrator.log
          </span>
        </div>
      )}

      <ScrollArea className="flex-1" ref={scrollRef}>
        <div className="space-y-3 p-4">
          {messages.map((message, idx) => {
            // A clarification is "answered" if there's any message after it
            const hasMessagesAfter = idx < messages.length - 1
            return (
              <MessageBubble
                key={message.id}
                message={message}
                isLastMessage={idx === messages.length - 1}
                clarificationAnswered={message.type === 'clarification' && hasMessagesAfter}
                onFeedback={onFeedback}
                onSuggestionClick={onSuggestionClick}
                onRetry={onRetry}
                onDocumentClick={onDocumentClick}
                onPreviewClick={onPreviewClick}
              />
            )
          })}

          {/* Loading indicator when no progress message */}
          {isLoading && !messages.some((m) => m.type === 'progress') && (
            <LoadingBubble />
          )}

          {/* Global error */}
          {error && <ErrorBubble error={error} />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>
    </div>
  )
}

// Message Bubble Component
interface MessageBubbleProps {
  message: EmmaMessage
  isLastMessage?: boolean
  clarificationAnswered?: boolean
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
}

function MessageBubble({
  message,
  isLastMessage = false,
  clarificationAnswered = false,
  onFeedback,
  onSuggestionClick,
  onRetry,
  onDocumentClick,
  onPreviewClick,
}: MessageBubbleProps) {
  const isUser = message.type === 'user'
  const isProgress = message.type === 'progress'
  const isError = message.type === 'error'

  // Verified generation progress — now shown in dialog, skip inline rendering
  if (message.type === 'verified_progress') {
    return null
  }

  // Verified generation result
  if (message.type === 'verified_result' && message.verified) {
    return <VerifiedDocumentResult content={message.content} verified={message.verified} />
  }

  // Predictive analysis result
  if (message.type === 'predictive_result' && message.predictive) {
    return <PredictionResult metadata={message.predictive} />
  }

  // Document generation result — wrapped with EMMA label + reasoning steps
  if (message.type === 'docgen_result' && message.docgen) {
    const docgenSlmSteps = message.metadata?.slmThinkingSteps || []
    return (
      <div className="w-full">
        <div className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
          {/* EMMA label */}
          <div className="flex items-center gap-2">
            <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
            <span className="text-xs font-mono text-primary uppercase tracking-wide">
              EMMA:
            </span>
          </div>

          {/* Reasoning steps (if any) */}
          {docgenSlmSteps.length > 0 && (
            <ReasoningCollapsible
              steps={docgenSlmSteps.map((s: SLMThinkingStep) => ({
                type: s.type as ReasoningStep['type'],
                content: s.content,
                detail: s.detail,
                entities: s.entities,
                confidence: s.confidence,
              }))}
              isActive={false}
            />
          )}

          {/* Document generation card */}
          <DocGenResult metadata={message.docgen} />

          {/* Suggestions */}
          {message.suggestions && message.suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-3 border-t border-border/50">
              {message.suggestions.map((suggestion, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  onClick={() => onSuggestionClick?.(suggestion)}
                  className="text-xs h-7 font-mono"
                >
                  {suggestion}
                </Button>
              ))}
            </div>
          )}

          {/* Footer */}
          {onFeedback && (
            <div className="flex items-center justify-between pt-2 border-t border-primary/10">
              <span className="text-[10px] font-mono text-muted-foreground">
                {message.timestamp.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
                {message.metadata?.execution_time_ms && (
                  <span className="ml-2 text-emerald-500">
                    {message.metadata.execution_time_ms < 1000
                      ? `${Math.round(message.metadata.execution_time_ms)}ms`
                      : `${(message.metadata.execution_time_ms / 1000).toFixed(1)}s`}
                  </span>
                )}
              </span>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 hover:text-emerald-500"
                  onClick={() => onFeedback(message.id, 'positive')}
                  title="Respuesta útil"
                >
                  <IconThumbUp className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 hover:text-destructive"
                  onClick={() => onFeedback(message.id, 'negative')}
                  title="Respuesta no útil"
                >
                  <IconThumbDown className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // Document Forge result — analyze/render/persist
  if (message.type === 'forge_result' && message.forge) {
    const forgeSlmSteps = message.metadata?.slmThinkingSteps || []
    return (
      <div className="w-full">
        <div className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
          <div className="flex items-center gap-2">
            <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
            <span className="text-xs font-mono text-primary uppercase tracking-wide">EMMA:</span>
          </div>
          {forgeSlmSteps.length > 0 && (
            <ReasoningCollapsible
              steps={forgeSlmSteps.map((s: SLMThinkingStep) => ({
                type: s.type as ReasoningStep['type'],
                content: s.content,
                detail: s.detail,
                entities: s.entities,
                confidence: s.confidence,
              }))}
              isActive={false}
            />
          )}
          <ForgeResult metadata={message.forge} />
        </div>
      </div>
    )
  }

  // Clarification card — ambiguous query with clickable options
  if (message.type === 'clarification' && message.metadata?.clarification) {
    const clarification = message.metadata.clarification as ClarificationData
    // Hide chips once user has responded (this message is no longer the last)
    const answered = clarificationAnswered
    return (
      <div className="w-full">
        <Card className={cn(
          'space-y-3 p-3 rounded-lg border',
          answered
            ? 'bg-primary/5 border-primary/20'
            : 'bg-amber-500/5 border-amber-500/20'
        )}>
          {/* EMMA label */}
          <div className="flex items-center gap-2">
            <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
            <span className="text-xs font-mono text-primary uppercase tracking-wide">
              EMMA:
            </span>
            {!answered && <IconHelpCircle className="h-4 w-4 text-amber-500 ml-auto" />}
          </div>

          {/* Clarification question */}
          <p className="text-sm text-foreground/90">{clarification.question}</p>

          {/* Option chips — only shown when unanswered */}
          {!answered && clarification.options.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {clarification.options.map((opt, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  onClick={() => onSuggestionClick?.(opt.value)}
                  className="text-xs h-7 font-mono border-amber-500/30 hover:bg-amber-500/10 hover:border-amber-500/50"
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          )}

          {/* Hint — only when unanswered */}
          {!answered && (
            <p className="text-xs text-muted-foreground italic">
              o escribe tu propia búsqueda
            </p>
          )}
        </Card>
      </div>
    )
  }

  // Progress message with workflow steps
  if (isProgress) {
    return <ProgressBubble message={message} />
  }

  // Terminal/Log style - all messages aligned left with labels
  // Different card styles for each message type
  const getCardStyles = () => {
    if (isUser) return 'p-4 border border-border/50 bg-card/80 rounded-lg'
    if (isError) return 'p-4 border border-destructive/30 bg-destructive/5 rounded-lg'
    // Emma responses - special terminal style
    return 'space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20'
  }

  return (
    <div className="w-full">
      <Card className={getCardStyles()}>
        {/* Message Label */}
        {isUser ? (
          // USER_QUERY label
          <div className="space-y-2">
            <span className="text-xs font-mono text-emerald-500 uppercase tracking-wide">
              USER_QUERY:
            </span>

            {/* Attached documents */}
            {message.metadata?.documents && message.metadata.documents.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {message.metadata.documents.map((doc, idx) => (
                  <div
                    key={doc.id || idx}
                    className="flex items-center gap-1.5 px-2 py-1 bg-primary/10 text-primary border border-primary/20 rounded text-xs font-mono"
                  >
                    <IconPaperclip className="h-3 w-3" />
                    <span className="max-w-[150px] truncate">{doc.name}</span>
                  </div>
                ))}
              </div>
            )}

            <p className="text-sm italic text-foreground/90">"{message.content}"</p>
          </div>
        ) : isError ? (
          // ERROR label
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <IconAlertCircle className="h-4 w-4 text-destructive" />
              <span className="text-xs font-mono text-destructive uppercase tracking-wide">
                ERROR:
              </span>
            </div>
            <p className="text-sm text-destructive/80">{message.content}</p>

            {message.metadata?.canRetry && message.metadata?.failedQuery && onRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRetry(message.metadata!.failedQuery!)}
                className="mt-2 text-xs"
              >
                <IconRotate className="h-3 w-3 mr-1" />
                Reintentar
              </Button>
            )}
          </div>
        ) : (
          // EMMA response
          <>
            {/* EMMA label - always shown */}
            <div className="flex items-center gap-2">
              <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
              <span className="text-xs font-mono text-primary uppercase tracking-wide">
                EMMA:
              </span>
            </div>

            {/* Show agent decision if available */}
            {message.metadata?.agent && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">
                  {message.metadata.agent_reasoning || 'Procesando con'}
                </span>
                <IconArrowRight className="h-3.5 w-3.5 text-primary/60" />
                <span className="font-semibold text-primary font-mono">
                  {message.metadata.agent}
                </span>
              </div>
            )}

            {/* Reasoning steps (collapsed after completion, expandable) */}
            {(() => {
              const slmSteps = message.metadata?.slmThinkingSteps || []
              if (slmSteps.length === 0) return null
              const allSteps: ReasoningStep[] = slmSteps.map((s: SLMThinkingStep) => ({
                type: s.type as ReasoningStep['type'],
                content: s.content,
                detail: s.detail,
                entities: s.entities,
                confidence: s.confidence,
              }))
              return (
                <ReasoningCollapsible
                  steps={allSteps}
                  isActive={false}
                />
              )
            })()}

              {/* Response content */}
              <EmmaMarkdown content={message.content} />

              {/* Download button for generated documents */}
              {message.content && (() => {
                // Match gen_ doc ID from generate_document tool output
                // Handles: **ID de descarga**: gen_xxx, ID de descarga: gen_xxx, or bare gen_xxx
                const docIdMatch = message.content.match(/\b(gen_[a-f0-9]{8,})\b/)
                const docId = docIdMatch?.[1]
                if (!docId) return null
                return (
                  <GeneratedDocDownload docId={docId} />
                )
              })()}

              {/* Related documents */}
              {message.metadata?.documents && message.metadata.documents.length > 0 && (
                <div className="pt-3 border-t border-border/50">
                  <DocumentDisplay
                    documents={message.metadata.documents}
                    onDocumentClick={onDocumentClick}
                    onPreviewClick={onPreviewClick}
                  />
                </div>
              )}

            {/* Suggestions */}
            {message.suggestions && message.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-3 border-t border-border/50">
                {message.suggestions.map((suggestion, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    size="sm"
                    onClick={() => onSuggestionClick?.(suggestion)}
                    className="text-xs h-7 font-mono"
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            )}

            {/* Footer for Emma responses */}
            {onFeedback && (
              <div className="flex items-center justify-between pt-2 border-t border-primary/10">
                <span className="text-[10px] font-mono text-muted-foreground">
                  {message.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                  {message.metadata?.execution_time_ms && (
                    <span className="ml-2 text-emerald-500">
                      {message.metadata.execution_time_ms < 1000
                        ? `${Math.round(message.metadata.execution_time_ms)}ms`
                        : `${(message.metadata.execution_time_ms / 1000).toFixed(1)}s`}
                    </span>
                  )}
                </span>

                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 hover:text-emerald-500"
                    onClick={() => onFeedback(message.id, 'positive')}
                    title="Respuesta útil"
                  >
                    <IconThumbUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 hover:text-destructive"
                    onClick={() => onFeedback(message.id, 'negative')}
                    title="Respuesta no útil"
                  >
                    <IconThumbDown className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}


function ProgressBubble({ message }: { message: EmmaMessage }) {
  const workflowSteps = message.metadata?.workflow_steps || []
  const hasSteps = workflowSteps.length > 0
  const isStreaming = message.metadata?.isStreaming
  const hasContent = message.content && message.content.trim().length > 0
  const streamingText = message.metadata?.streaming_text || ''
  const hasStreamingText = streamingText.trim().length > 0

  // SLM thinking steps
  const slmThinkingSteps = message.metadata?.slmThinkingSteps || []
  const slmIsThinking = message.metadata?.slmIsThinking ?? false
  const hasSLMThinking = slmThinkingSteps.length > 0 || slmIsThinking

  // Get current agent name from metadata or steps
  const currentAgent = message.metadata?.agent ||
    workflowSteps.find(s => s.status === 'in_progress')?.agent ||
    'Emma'

  // Determine the content to display - use same rendering as final result
  const displayContent = hasStreamingText ? streamingText : (hasContent ? message.content : '')
  const showContent = displayContent.trim().length > 0

  return (
    <div className="w-full">
      {/* Same style as final Emma response - consistent structure prevents layout shift */}
      <Card className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
        {/* EMMA label - always shown (same as final response) */}
        <div className="flex items-center gap-2">
          <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
          <span className="text-xs font-mono text-primary uppercase tracking-wide">
            EMMA:
          </span>
          {/* Show streaming indicator next to label */}
          {(isStreaming || slmIsThinking) && (
            <span className="h-2 w-2 rounded-full bg-primary animate-pulse ml-auto" />
          )}
        </div>

        {/* Agent info - same as final result */}
        {currentAgent && currentAgent !== 'Emma' && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Procesando con</span>
            <IconArrowRight className="h-3.5 w-3.5 text-primary/60" />
            <span className="font-semibold text-primary font-mono">{currentAgent}</span>
          </div>
        )}

        {/* SLM Thinking Display - collapsible chain-of-thought */}
        {hasSLMThinking && (
          <ReasoningCollapsible
            steps={slmThinkingSteps.map((s: SLMThinkingStep) => ({
              type: s.type as ReasoningStep['type'],
              content: s.content,
              detail: s.detail,
              entities: s.entities,
              confidence: s.confidence,
            }))}
            isActive={slmIsThinking}
          />
        )}

        {/* Workflow steps - shown above content like reasoning */}
        {hasSteps && (
          <div className="space-y-2">
            {workflowSteps.map((step) => (
              <WorkflowStepItem key={step.index} step={step} />
            ))}
          </div>
        )}

        {/* Main content - ALWAYS use EmmaMarkdown for consistent doc formatting */}
        {showContent ? (
          <div className="relative min-h-[2rem]">
            <EmmaMarkdown content={displayContent} />
            {isStreaming && (
              <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse ml-0.5 align-middle" />
            )}
          </div>
        ) : !hasSLMThinking && !hasSteps ? (
          <ThinkingIndicator />
        ) : null}

        {/* Placeholder footer - maintains consistent height during streaming */}
        {showContent && (
          <div className="flex items-center justify-between pt-2 border-t border-primary/10 min-h-[28px]">
            <span className="text-[10px] font-mono text-muted-foreground">
              {isStreaming ? 'Generando respuesta...' : ''}
            </span>
          </div>
        )}
      </Card>
    </div>
  )
}

// Workflow Step Item (terminal style)
function WorkflowStepItem({ step }: { step: WorkflowStep }) {
  const getStatusIndicator = () => {
    switch (step.status) {
      case 'completed':
        return <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500" />
      case 'in_progress':
        return <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
      case 'error':
        return <IconAlertCircle className="h-3.5 w-3.5 text-destructive" />
      default:
        return <span className="h-2 w-2 rounded-full border border-muted-foreground/30" />
    }
  }

  const agentName = step.agent || 'Task'

  return (
    <div className={cn(
      'flex items-center gap-2 text-xs font-mono',
      step.status === 'pending' && 'text-muted-foreground/50',
      step.status === 'in_progress' && 'text-emerald-400',
      step.status === 'completed' && 'text-muted-foreground',
      step.status === 'error' && 'text-destructive'
    )}>
      {getStatusIndicator()}
      <span className="text-muted-foreground">[{agentName}]</span>
      <span>{step.description}</span>
      {step.status === 'in_progress' && (
        <span className="inline-block w-2 h-2 rounded-full bg-emerald-500/50 animate-pulse ml-1" />
      )}
      {step.execution_time_ms && step.status === 'completed' && (
        <span className="text-[10px] text-emerald-500/70 ml-auto">
          {step.execution_time_ms < 1000
            ? `${Math.round(step.execution_time_ms)}ms`
            : `${(step.execution_time_ms / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  )
}

// Thinking Indicator (simple text)
function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span>Procesando</span>
      <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />
    </div>
  )
}

// Loading Bubble (same style as Emma response)
function LoadingBubble() {
  return (
    <div className="w-full">
      <Card className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
        {/* EMMA label */}
        <div className="flex items-center gap-2">
          <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
          <span className="text-xs font-mono text-primary uppercase tracking-wide">
            EMMA:
          </span>
          <span className="h-2 w-2 rounded-full bg-primary animate-pulse ml-auto" />
        </div>

        {/* Loading skeleton */}
        <div className="space-y-2">
          <Skeleton className="h-4 w-full bg-primary/10" />
          <Skeleton className="h-4 w-3/4 bg-primary/10" />
          <Skeleton className="h-4 w-1/2 bg-primary/10" />
        </div>
      </Card>
    </div>
  )
}

// Generated Document Download Button (inline in responses)
function GeneratedDocDownload({ docId }: { docId: string }) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      const { apiClient } = await import('@/lib/api-client')
      const result = await apiClient.downloadBlob(`/emma/generated/${docId}/download`)
      if (result.error || !result.blob) throw new Error(result.error || 'Download failed')
      const blobUrl = URL.createObjectURL(result.blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = `documento_generado_${docId}.docx`
      a.click()
      URL.revokeObjectURL(blobUrl)
    } catch (err) {
      console.error('DOCX download failed:', err)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex items-center gap-2 mt-3 p-2.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
      <IconFileText className="h-5 w-5 text-violet-600 flex-shrink-0" />
      <span className="text-xs text-violet-700 dark:text-violet-400 flex-1">
        Documento DOCX generado y listo para descargar
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={handleDownload}
        disabled={downloading}
        className="gap-1.5 text-xs border-violet-500/30 text-violet-600 hover:bg-violet-500/10"
      >
        <IconDownload className="h-3.5 w-3.5" />
        {downloading ? 'Descargando...' : 'Descargar DOCX'}
      </Button>
    </div>
  )
}

// Error Bubble (terminal style)
function ErrorBubble({ error }: { error: string }) {
  return (
    <div className="w-full">
      <Card className="p-4 border border-destructive/30 bg-destructive/5 rounded-lg">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <IconAlertCircle className="h-4 w-4 text-destructive" />
            <span className="text-xs font-mono text-destructive uppercase tracking-wide">
              SYSTEM_ERROR:
            </span>
          </div>
          <p className="text-sm font-mono text-destructive/80">{error}</p>
        </div>
      </Card>
    </div>
  )
}
