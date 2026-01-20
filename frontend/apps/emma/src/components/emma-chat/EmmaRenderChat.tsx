'use client'

import { useRef, useEffect } from 'react'
import { User, Bot, AlertCircle, ThumbsUp, ThumbsDown, RotateCcw, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { EmmaMessage, WorkflowStep, DocumentInfo } from '@/lib/types/emma'
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
}: EmmaRenderChatProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <ScrollArea className={cn('h-full', className)} ref={scrollRef}>
      <div className="space-y-4 p-4">
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

  const getMessageStyles = () => {
    if (isUser) return 'bg-primary text-primary-foreground'
    if (isError) return 'bg-destructive/10 text-destructive border-destructive/20'
    return 'bg-muted'
  }

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback
          className={cn(
            isUser
              ? 'bg-primary text-primary-foreground'
              : 'bg-gradient-to-br from-primary to-primary/70 text-primary-foreground'
          )}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      <div className={cn('flex-1 max-w-[85%]', isUser && 'flex justify-end')}>
        <Card className={cn('p-4 border', getMessageStyles())}>
          {/* Content */}
          <div className="space-y-3">
            {isUser ? (
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
            ) : (
              <EmmaMarkdown content={message.content} />
            )}

            {/* Error retry */}
            {isError && message.metadata?.canRetry && message.metadata?.failedQuery && onRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRetry(message.metadata!.failedQuery!)}
                className="mt-2"
              >
                <RotateCcw className="h-3 w-3 mr-1" />
                Reintentar
              </Button>
            )}

            {/* Tools used */}
            {message.metadata?.tools_used && message.metadata.tools_used.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {message.metadata.tools_used.map((tool, idx) => (
                  <Badge key={idx} variant="secondary" className="text-[10px]">
                    {tool}
                  </Badge>
                ))}
              </div>
            )}

            {/* Related documents */}
            {!isUser && message.metadata?.documents && message.metadata.documents.length > 0 && (
              <div className="mt-3 pt-3 border-t">
                <DocumentDisplay
                  documents={message.metadata.documents}
                  onDocumentClick={onDocumentClick}
                  onPreviewClick={onPreviewClick}
                />
              </div>
            )}

            {/* Suggestions */}
            {message.suggestions && message.suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t">
                {message.suggestions.map((suggestion, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    size="sm"
                    onClick={() => onSuggestionClick?.(suggestion)}
                    className="text-xs h-7"
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {!isUser && !isError && (
            <div className="flex items-center justify-between mt-3 pt-2 border-t border-border/50">
              <span className="text-[10px] text-muted-foreground">
                {message.timestamp.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
                {message.metadata?.execution_time_ms && (
                  <span className="ml-2">
                    {message.metadata.execution_time_ms < 1000
                      ? `${Math.round(message.metadata.execution_time_ms)}ms`
                      : `${(message.metadata.execution_time_ms / 1000).toFixed(1)}s`}
                  </span>
                )}
              </span>

              {onFeedback && (
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => onFeedback(message.id, 'positive')}
                    title="Respuesta útil"
                  >
                    <ThumbsUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => onFeedback(message.id, 'negative')}
                    title="Respuesta no útil"
                  >
                    <ThumbsDown className="h-3 w-3" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

// Progress Bubble with Workflow Steps and Streaming Content
function ProgressBubble({ message }: { message: EmmaMessage }) {
  const workflowSteps = message.metadata?.workflow_steps || []
  const hasSteps = workflowSteps.length > 0
  const isStreaming = message.metadata?.isStreaming
  const hasContent = message.content && message.content.trim().length > 0
  const streamingText = message.metadata?.streaming_text || ''
  const hasStreamingText = streamingText.trim().length > 0

  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="bg-gradient-to-br from-primary to-primary/70 text-primary-foreground">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>

      <div className="flex-1 max-w-[85%]">
        <Card className="p-4 bg-muted/50 border">
          {hasSteps ? (
            <div className="space-y-3">
              {/* Current step message */}
              {hasContent && (
                <p className="text-sm text-muted-foreground">{message.content}</p>
              )}

              {/* Workflow steps */}
              <div className="space-y-2">
                {workflowSteps.map((step) => (
                  <WorkflowStepItem key={step.index} step={step} />
                ))}
              </div>

              {/* Streaming answer while steps run */}
              {(isStreaming || hasStreamingText) && (
                <div className="pt-3 border-t space-y-2">
                  {hasStreamingText && <EmmaMarkdown content={streamingText} />}
                  {isStreaming && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <div className="h-2 w-2 bg-primary rounded-full animate-pulse" />
                      <span>Escribiendo...</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : isStreaming && (hasContent || hasStreamingText) ? (
            // Streaming content without workflow steps (direct response)
            <div className="space-y-2">
              <EmmaMarkdown content={hasStreamingText ? streamingText : message.content} />
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <div className="h-2 w-2 bg-primary rounded-full animate-pulse" />
                <span>Escribiendo...</span>
              </div>
            </div>
          ) : (
            <ThinkingIndicator />
          )}
        </Card>
      </div>
    </div>
  )
}

// Workflow Step Item
function WorkflowStepItem({ step }: { step: WorkflowStep }) {
  const getStatusIcon = () => {
    switch (step.status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-500" />
      case 'in_progress':
        return (
          <div className="h-4 w-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        )
      case 'error':
        return <AlertCircle className="h-4 w-4 text-destructive" />
      default:
        return <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
    }
  }

  return (
    <div className={cn(
      'flex items-center gap-2 text-sm',
      step.status === 'pending' && 'text-muted-foreground/50',
      step.status === 'in_progress' && 'text-primary font-medium',
      step.status === 'completed' && 'text-muted-foreground',
      step.status === 'error' && 'text-destructive'
    )}>
      {getStatusIcon()}
      <span>{step.description}</span>
      {step.execution_time_ms && step.status === 'completed' && (
        <span className="text-[10px] text-muted-foreground ml-auto">
          {step.execution_time_ms < 1000
            ? `${Math.round(step.execution_time_ms)}ms`
            : `${(step.execution_time_ms / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  )
}

// Thinking Indicator (animated dots)
function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-3">
      <div className="flex space-x-1">
        <div className="w-2 h-2 bg-primary rounded-full animate-bounce" />
        <div
          className="w-2 h-2 bg-primary rounded-full animate-bounce"
          style={{ animationDelay: '0.1s' }}
        />
        <div
          className="w-2 h-2 bg-primary rounded-full animate-bounce"
          style={{ animationDelay: '0.2s' }}
        />
      </div>
      <span className="text-sm text-muted-foreground">Emma está pensando...</span>
    </div>
  )
}

// Loading Bubble
function LoadingBubble() {
  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="bg-gradient-to-br from-primary to-primary/70 text-primary-foreground">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>

      <Card className="p-4 bg-muted border max-w-[85%]">
        <ThinkingIndicator />
        <div className="space-y-2 mt-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </Card>
    </div>
  )
}

// Error Bubble
function ErrorBubble({ error }: { error: string }) {
  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="bg-destructive text-destructive-foreground">
          <AlertCircle className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>

      <Card className="p-4 bg-destructive/10 border-destructive/20 max-w-[85%]">
        <div className="flex items-center gap-2 text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span className="font-medium text-sm">Error</span>
        </div>
        <p className="text-sm mt-2 text-destructive/80">{error}</p>
      </Card>
    </div>
  )
}
