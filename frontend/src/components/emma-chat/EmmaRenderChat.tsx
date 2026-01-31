"use client"

import { useRef, useEffect } from "react"
import { User, Bot, AlertCircle, Info, ThumbsUp, ThumbsDown, Code, BarChart3, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { EmmaMarkdownFormat } from "./EmmaMarkdownFormat"
import { DisplayRenderer } from "./displays/DisplayRenderer"
import { EmmaClarificationUI } from "./EmmaClarificationUI"
import { EmmaRenderChatProps, EmmaMessage } from "./types"
import { useTranslation } from "@/lib/i18n/hooks"
import { TTSControls } from "./TTSControls"
import { useTTSPreferences } from "@/contexts/tts-context"

export function EmmaRenderChat(props: EmmaRenderChatProps) {
  const {
    messages,
    isLoading = false,
    error = null,
    socketStatus = "connected",
    onFeedback,
    onSuggestionClick,
    onDocumentClick,
    onPreviewClick,
    onRetry,
    onClarificationSubmit,
    currentView = "chat",
    onViewChange,
    className,
    isAdmin = false
  } = props

  // Defensive handlers - ensure they're always functions
  const safeOnDocumentClick = typeof onDocumentClick === 'function' ? onDocumentClick : () => {}
  const safeOnPreviewClick = typeof onPreviewClick === 'function' ? onPreviewClick : () => {}
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Process messages for display (merge similar messages)
  const processedMessages = processMessages(messages)

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* View Controls */}
      {onViewChange && (
        <div className="flex items-center gap-2 p-4 border-b bg-muted/30">
          <div className="flex items-center gap-1 border rounded-md p-1">
            <Button
              variant={currentView === "chat" ? "default" : "ghost"}
              size="sm"
              onClick={() => onViewChange("chat")}
              className="h-8"
            >
              <Bot className="h-4 w-4 mr-2" />
              Chat
            </Button>
            <Button
              variant={currentView === "code" ? "default" : "ghost"}
              size="sm"
              onClick={() => onViewChange("code")}
              className="h-8"
            >
              <Code className="h-4 w-4 mr-2" />
              Código
            </Button>
            <Button
              variant={currentView === "result" ? "default" : "ghost"}
              size="sm"
              onClick={() => onViewChange("result")}
              className="h-8"
            >
              <BarChart3 className="h-4 w-4 mr-2" />
              Resultado
            </Button>
          </div>

          {/* Connection Status */}
          <div className="ml-auto flex items-center gap-2">
            <div className={cn(
              "flex items-center gap-1 text-xs px-2 py-1 rounded-full",
              socketStatus === "connected" && "bg-green-100 text-green-700",
              socketStatus === "connecting" && "bg-yellow-100 text-yellow-700",
              socketStatus === "disconnected" && "bg-red-100 text-red-700"
            )}>
              <div className={cn(
                "w-2 h-2 rounded-full",
                socketStatus === "connected" && "bg-green-500",
                socketStatus === "connecting" && "bg-yellow-500 animate-pulse",
                socketStatus === "disconnected" && "bg-red-500"
              )} />
              {socketStatus}
            </div>
          </div>
        </div>
      )}

      {/* Messages Area */}
      <ScrollArea className="flex-1 p-4" ref={scrollAreaRef}>
        <div className="space-y-6">
          {processedMessages.map((message, index) => {
            // Check if this is the latest "result" message (for auto-play)
            const isLatestResult = message.type === "result" &&
              index === processedMessages.length - 1;

            return (
              <MessageDisplay
                key={message.id}
                message={message}
                onFeedback={onFeedback}
                onSuggestionClick={onSuggestionClick}
                onDocumentClick={safeOnDocumentClick}
                onPreviewClick={safeOnPreviewClick}
                onRetry={onRetry}
                onClarificationSubmit={onClarificationSubmit}
                isAdmin={isAdmin}
                isLatestResult={isLatestResult}
              />
            );
          })}

          {/* Loading State - only show if no progress message exists */}
          {isLoading && !processedMessages.some(m => m.type === 'progress') && <LoadingMessage />}

          {/* Error State */}
          {error && <ErrorMessage error={error} />}

          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>
    </div>
  )
}

// Individual Message Display Component
interface MessageDisplayProps {
  message: EmmaMessage
  onFeedback?: (messageId: string, feedback: "positive" | "negative") => void
  onSuggestionClick?: (suggestion: string) => void
  onDocumentClick?: (doc: any) => void
  onPreviewClick?: (doc: any) => void
  onRetry?: (failedQuery: string) => void
  onClarificationSubmit?: (messageId: string, selectedValues: string[]) => void
  isAdmin?: boolean
  isLatestResult?: boolean  // True if this is the latest result message (for auto-play)
}

function MessageDisplay({
  message,
  onFeedback,
  onSuggestionClick,
  onDocumentClick,
  onPreviewClick,
  onRetry,
  onClarificationSubmit,
  isAdmin = false,
  isLatestResult = false
}: MessageDisplayProps) {
  const { t } = useTranslation()
  const { preferences: ttsPreferences } = useTTSPreferences()

  // Check if this is a "thinking" state (progress without workflow steps)
  const isThinkingState = message.type === "progress" && !message.metadata?.workflow_steps?.length

  const getMessageIcon = () => {
    switch (message.type) {
      case "user":
        return <User className="h-4 w-4" />
      case "result":
      case "text":
        return <Bot className="h-4 w-4" />
      case "clarification":
        return <Info className="h-4 w-4" />
      case "error":
      case "self_healing_error":
        return <AlertCircle className="h-4 w-4" />
      case "warning":
        return <Info className="h-4 w-4" />
      default:
        return <Bot className="h-4 w-4" />
    }
  }

  const getMessageColor = () => {
    switch (message.type) {
      case "user":
        return "bg-secondary border border-secondary"
      case "clarification":
        return "bg-blue-50 dark:bg-blue-950/50 text-blue-900 dark:text-blue-100 border border-blue-200 dark:border-blue-800"
      case "error":
      case "self_healing_error":
        return "bg-red-50 dark:bg-red-950/50 text-red-900 dark:text-red-100 border border-red-200 dark:border-red-800"
      case "warning":
        return "bg-yellow-50 dark:bg-yellow-950/50 text-yellow-800 dark:text-yellow-200 border border-yellow-200 dark:border-yellow-800"
      default:
        return "bg-background border"
    }
  }

  // Special rendering for "thinking" state - just avatar + animated dots
  if (isThinkingState) {
    return (
      <div className="flex gap-3 items-center">
        <Avatar className="h-8 w-8 flex-shrink-0">
          <AvatarFallback className="bg-primary text-primary-foreground">
            <Bot className="h-4 w-4" />
          </AvatarFallback>
        </Avatar>
        <DisplayRenderer
          message={message}
          onDocumentClick={onDocumentClick}
          onPreviewClick={onPreviewClick}
          isAdmin={isAdmin}
        />
      </div>
    )
  }

  return (
    <div className={cn(
      "flex gap-3",
      message.type === "user" && "flex-row-reverse"
    )}>
      {/* Avatar */}
      <Avatar className="h-8 w-8 flex-shrink-0">
        {message.type === "user" ? (
          <AvatarFallback className="bg-primary text-primary-foreground">
            {getMessageIcon()}
          </AvatarFallback>
        ) : (
          <AvatarFallback className="bg-primary text-primary-foreground">
            {getMessageIcon()}
          </AvatarFallback>
        )}
      </Avatar>

      {/* Message Content */}
      <div className="flex-1 max-w-[85%]">
        <Card className={cn("p-4", getMessageColor())}>
          {/* Message Content */}
          <div className="space-y-3">
            {/* Human-in-the-Loop Clarification UI */}
            {message.type === "clarification" && message.metadata?.clarification ? (
              <EmmaClarificationUI
                question={message.metadata.clarification.question}
                header={message.metadata.clarification.header}
                options={message.metadata.clarification.options}
                multiSelect={message.metadata.clarification.multi_select}
                severity={message.metadata.clarification.severity}
                type={message.metadata.clarification.type}
                onSubmit={(selectedValues) => onClarificationSubmit?.(message.id, selectedValues)}
                className="my-2"
              />
            ) : (
              <DisplayRenderer
                message={message}
                onDocumentClick={onDocumentClick}
                onPreviewClick={onPreviewClick}
                isAdmin={isAdmin}
              />
            )}

              {/* Decision Path */}
              {message.metadata?.decision_path && (
                <div className="text-xs text-muted-foreground">
                  <strong>Ruta de decisión:</strong> {message.metadata.decision_path.join(" → ")}
                </div>
              )}

              {/* Tools Used */}
              {message.metadata?.tools_used && message.metadata.tools_used.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {message.metadata.tools_used.map((tool, index) => (
                    <Badge key={index} variant="outline" className="text-xs">
                      {tool}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Suggestions */}
              {message.suggestions && message.suggestions.length > 0 && (
                <div className="space-y-2">
                  <div className="text-sm font-medium text-muted-foreground">
                    Sugerencias:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {message.suggestions.map((suggestion, index) => (
                      <Button
                        key={index}
                        variant="outline"
                        size="sm"
                        onClick={() => onSuggestionClick?.(suggestion)}
                        className="h-8 text-xs"
                      >
                        {suggestion}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
          </div>

          {/* Message Footer */}
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-border/50">
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>
                {message.timestamp.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
              {message.type !== "user" && message.metadata?.execution_time_ms && (
                <span className="flex items-center gap-1">
                  <span className="opacity-50">•</span>
                  {message.metadata.execution_time_ms < 1000
                    ? `${Math.round(message.metadata.execution_time_ms)}ms`
                    : `${(message.metadata.execution_time_ms / 1000).toFixed(1)}s`
                  }
                </span>
              )}
            </div>

            <div className="flex gap-2">
              {/* Retry Button for recoverable errors */}
              {message.type === "error" && message.metadata?.canRetry && message.metadata?.failedQuery && onRetry && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onRetry(message.metadata!.failedQuery!)}
                  className="h-7 px-3 text-xs gap-1"
                >
                  <RotateCcw className="h-3 w-3" />
                  {t('emma.errors.retry')}
                </Button>
              )}

              {/* TTS Button - Read response aloud */}
              {message.type !== "user" && message.type !== "error" && message.type !== "progress" && message.content && ttsPreferences.enabled && (
                <TTSControls
                  text={message.content}
                  size="sm"
                  iconOnly
                  voiceId={ttsPreferences.voiceId}
                  language={ttsPreferences.language}
                  autoPlayOnMount={isLatestResult && ttsPreferences.autoPlay}
                />
              )}

              {/* Feedback Buttons */}
              {onFeedback && message.type !== "user" && message.type !== "error" && (
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onFeedback(message.id, "positive")}
                    className="h-6 w-6 p-0"
                    title="Respuesta útil"
                  >
                    <ThumbsUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onFeedback(message.id, "negative")}
                    className="h-6 w-6 p-0"
                    title="Respuesta no útil"
                  >
                    <ThumbsDown className="h-3 w-3" />
                  </Button>
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

// Loading Message Component
function LoadingMessage() {
  const { t } = useTranslation()

  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8">
        <AvatarImage src="/emma-avatar.svg" />
        <AvatarFallback className="bg-primary text-primary-foreground">
          <Bot className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <Card className="p-4 bg-muted border max-w-[85%]">
        <div className="flex items-center gap-3 mb-3">
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce"></div>
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
            <div className="w-2 h-2 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
          </div>
          <span className="text-sm text-muted-foreground">{t('chatPage.emmaResponding')}</span>
        </div>
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </Card>
    </div>
  )
}

// Error Message Component
function ErrorMessage({ error }: { error: string }) {
  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8">
        <AvatarFallback className="bg-red-500 text-white">
          <AlertCircle className="h-4 w-4" />
        </AvatarFallback>
      </Avatar>
      <Card className="p-4 bg-red-50 dark:bg-red-950/50 text-red-900 dark:text-red-100 border border-red-200 dark:border-red-800 max-w-[85%]">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm font-medium">Error</span>
        </div>
        <p className="text-sm mt-2">{error}</p>
      </Card>
    </div>
  )
}

// Helper function to process and merge messages
function processMessages(messages: EmmaMessage[]): EmmaMessage[] {
  // For now, return messages as-is
  // In a full implementation, you might want to merge similar consecutive messages
  return messages.filter(message => {
    // Don't render streaming messages that are empty
    if (message.isStreaming && !message.content) {
      return false
    }
    return true
  })
}

// Backward compatibility alias
export { EmmaRenderChat as ElysiaRenderChat }
