'use client'

import { useRef, useEffect } from 'react'
import { IconAlertCircle, IconThumbUp, IconThumbDown, IconRotate, IconCircleCheck, IconPaperclip, IconSearch, IconBulb, IconGitBranch, IconBrain, IconArrowRight } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { EmmaMessage, WorkflowStep, DocumentInfo, SLMThinkingStep, SLMPlan } from '@/lib/types/emma'
import { EmmaMarkdown } from './EmmaMarkdown'
import { DocumentDisplay } from './DocumentDisplay'

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

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onFeedback={onFeedback}
              onSuggestionClick={onSuggestionClick}
              onRetry={onRetry}
              onDocumentClick={onDocumentClick}
              onPreviewClick={onPreviewClick}
            />
          ))}

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
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onDocumentClick?: (doc: DocumentInfo) => void
  onPreviewClick?: (doc: DocumentInfo) => void
}

function MessageBubble({
  message,
  onFeedback,
  onSuggestionClick,
  onRetry,
  onDocumentClick,
  onPreviewClick,
}: MessageBubbleProps) {
  const isUser = message.type === 'user'
  const isProgress = message.type === 'progress'
  const isError = message.type === 'error'

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
            <span className="text-xs font-mono text-primary uppercase tracking-wide">
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
              <IconBrain className="h-5 w-5 text-primary" />
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

              {/* Response content */}
              <EmmaMarkdown content={message.content} />

              {/* Tools used */}
              {message.metadata?.tools_used && message.metadata.tools_used.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-2">
                  {message.metadata.tools_used.map((tool, idx) => (
                    <Badge key={idx} variant="secondary" className="text-[10px] font-mono">
                      {tool}
                    </Badge>
                  ))}
                </div>
              )}

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

// Progress Bubble with Workflow Steps and Streaming Content
// SLM Thinking Step Display (terminal style)
function SLMThinkingStepItem({ step, isLast }: { step: SLMThinkingStep; isLast: boolean }) {
  const getStepIcon = () => {
    switch (step.type) {
      case 'entity_detection':
        return <IconSearch className="h-3 w-3" />
      case 'intent_detection':
        return <IconBulb className="h-3 w-3" />
      case 'route_decision':
        return <IconGitBranch className="h-3 w-3" />
    }
  }

  const getStepLabel = () => {
    switch (step.type) {
      case 'entity_detection':
        return 'ENTITIES'
      case 'intent_detection':
        return 'INTENT'
      case 'route_decision':
        return 'ROUTE'
    }
  }

  return (
    <div className="flex items-start gap-2 animate-in fade-in slide-in-from-left-2 duration-300">
      <div className="flex items-center justify-center h-4 w-4 text-primary/70 shrink-0 mt-0.5">
        {getStepIcon()}
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-primary/70">{getStepLabel()}:</span>{' '}
        <span className="text-foreground/70">{step.content}</span>
        {step.entities && step.entities.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {step.entities.map((entity, idx) => (
              <Badge key={idx} variant="outline" className="text-[10px] py-0 font-mono bg-primary/10 text-primary border-primary/20">
                {entity}
              </Badge>
            ))}
          </div>
        )}
        {isLast && (
          <span className="inline-block w-2 h-2 rounded-full bg-primary/50 animate-pulse ml-1 align-middle" />
        )}
      </div>
    </div>
  )
}

function SLMThinkingDisplay({
  steps,
  isThinking,
  plan
}: {
  steps: SLMThinkingStep[]
  isThinking: boolean
  plan?: SLMPlan
}) {
  if (steps.length === 0 && !isThinking) return null

  return (
    <div className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
      {/* EMMA DECIDE header */}
      <div className="flex items-center gap-2">
        <IconBrain className="h-5 w-5 text-primary" />
        <span className="text-xs font-mono text-primary uppercase tracking-wide">
          EMMA DECIDE:
        </span>
        {isThinking && (
          <span className="h-2 w-2 bg-primary rounded-full animate-pulse ml-auto" />
        )}
      </div>

      {/* Thinking steps */}
      {steps.length > 0 && (
        <div className="space-y-1.5 ml-1 font-mono text-xs">
          {steps.map((step, idx) => (
            <SLMThinkingStepItem key={step.step} step={step} isLast={idx === steps.length - 1} />
          ))}
        </div>
      )}

      {/* Plan result with arrow to agent */}
      {plan && !isThinking && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-primary/20">
          <span className="text-xs text-muted-foreground font-mono">
            {plan.reasoning || 'Procesando consulta'}
          </span>
          <IconArrowRight className="h-4 w-4 text-primary/60 ml-auto" />
          <Badge variant="outline" className="text-[10px] font-mono bg-primary/10 text-primary border-primary/30">
            {plan.route.replace('_', ' ')}
          </Badge>
        </div>
      )}
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
  const slmPlan = message.metadata?.slmPlan
  const hasSLMThinking = slmThinkingSteps.length > 0 || slmIsThinking

  // Get current agent name from metadata or steps
  const currentAgent = message.metadata?.agent ||
    workflowSteps.find(s => s.status === 'in_progress')?.agent ||
    'Emma'

  return (
    <div className="w-full">
      {/* Same style as final Emma response */}
      <Card className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
        {/* EMMA label - always shown (same as final response) */}
        <div className="flex items-center gap-2">
          <IconBrain className="h-5 w-5 text-primary" />
          <span className="text-xs font-mono text-primary uppercase tracking-wide">
            EMMA:
          </span>
          {/* Show streaming indicator next to label */}
          {(isStreaming || slmIsThinking) && (
            <span className="h-2 w-2 rounded-full bg-primary animate-pulse ml-auto" />
          )}
        </div>

        {/* SLM Thinking Display - visible chain-of-thought */}
        {hasSLMThinking && (
          <SLMThinkingDisplay
            steps={slmThinkingSteps}
            isThinking={slmIsThinking}
            plan={slmPlan}
          />
        )}

        {hasSteps ? (
          <>
            {/* Current step message */}
            {hasContent && !hasSLMThinking && (
              <p className="text-sm text-muted-foreground font-mono">{message.content}</p>
            )}

            {/* Workflow steps */}
            <div className="space-y-2">
              {workflowSteps.map((step) => (
                <WorkflowStepItem key={step.index} step={step} />
              ))}
            </div>

            {/* Streaming answer while steps run */}
            {(isStreaming || hasStreamingText) && (
              <div className="pt-2 border-t border-primary/10 space-y-2">
                {/* Streaming text with cursor */}
                {hasStreamingText && (
                  <div className="relative">
                    <EmmaMarkdown content={streamingText} />
                    {isStreaming && (
                      <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse ml-0.5 align-middle" />
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        ) : isStreaming && (hasContent || hasStreamingText) ? (
          // Streaming content without workflow steps (direct response)
          <div className="relative">
            <EmmaMarkdown content={hasStreamingText ? streamingText : message.content} />
            <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse ml-0.5 align-middle" />
          </div>
        ) : !hasSLMThinking ? (
          <ThinkingIndicator />
        ) : null}
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
          <IconBrain className="h-5 w-5 text-primary" />
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
