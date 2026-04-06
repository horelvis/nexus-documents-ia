'use client'

import { IconAlertCircle, IconThumbUp, IconThumbDown, IconCopy, IconCheck, IconRotate, IconPaperclip, IconArrowRight, IconHelpCircle, IconRoute } from '@tabler/icons-react'
import { useState } from 'react'
import ReasoningModal from '../ReasoningModal'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAuth } from '@/contexts/auth-context'
import type { EmmaMessage, DocumentInfo, ClarificationData } from '@/lib/types/emma'
import { ActivityTimeline } from '../ActivityTimeline'
import { humanizeSteps } from '../utils/humanizeStep'
import { EmmaMarkdown } from '../EmmaMarkdown'
import { InlineSourceCard } from '../InlineSourceCard'
import { ExplanationPanel } from '../ExplanationPanel'
import { VerifiedDocumentResult } from '../VerifiedDocumentResult'
import { PredictionResult } from '../PredictionResult'
import { DocGenResult } from '../DocGenResult'
import { ForgeResult } from '../ForgeResult'
import { useStreamingText } from '../hooks/useStreamingText'
import { GeneratedDocDownload } from './GeneratedDocDownload'
import { ProgressBubble } from './ProgressBubble'
import { EntityTags } from '../EntityTags'
import { SourceEvidence } from '../SourceEvidence'
import { ReportPanel } from '../ReportPanel'

export interface MessageBubbleProps {
  message: EmmaMessage
  isLastMessage?: boolean
  clarificationAnswered?: boolean
  onFeedback?: (messageId: string, feedback: 'positive' | 'negative') => void
  onSuggestionClick?: (suggestion: string) => void
  onRetry?: (failedQuery: string) => void
  onOpenFullscreen?: (doc: DocumentInfo) => void
  renderHITLReview?: (request: any, messageId: string) => React.ReactNode
  renderBranchSwitcher?: (messageId: string) => React.ReactNode
  renderCommandBar?: (messageId: string, content: string) => React.ReactNode
}

export function MessageBubble({
  message,
  isLastMessage = false,
  clarificationAnswered = false,
  onFeedback,
  onSuggestionClick,
  onRetry,
  onOpenFullscreen,
  renderHITLReview,
  renderBranchSwitcher,
  renderCommandBar,
}: MessageBubbleProps) {
  const isNewResult = isLastMessage && message.type === 'result'
  const { displayText: streamedContent, isRevealing } = useStreamingText(
    message.content,
    isNewResult,
  )

  // ── Special types with their own layout ──
  if (message.type === 'verified_progress') return null
  if (message.type === 'verified_result' && message.verified) {
    return <VerifiedDocumentResult content={message.content} verified={message.verified} />
  }
  if (message.type === 'predictive_result' && message.predictive) {
    return <PredictionResult metadata={message.predictive} />
  }
  if (message.type === 'progress') {
    return <ProgressBubble message={message} />
  }

  // ── Forge result (island block) ──
  if (message.type === 'forge_result' && message.forge) {
    return (
      <EmmaMessageFlow>
        <div className="mt-2 rounded-xl border border-border/40 bg-card/40 p-4 overflow-hidden">
          <ForgeResult metadata={message.forge} />
        </div>
        {message.metadata?.explanation && (
          <ExplanationPanel explanation={message.metadata.explanation} />
        )}
      </EmmaMessageFlow>
    )
  }

  // ── DocGen result (island block) ──
  if (message.type === 'docgen_result' && message.docgen) {
    return (
      <EmmaMessageFlow>
        <div className="mt-2 rounded-xl border border-border/40 bg-card/40 p-4 overflow-hidden">
          <DocGenResult metadata={message.docgen} />
        </div>
        {message.suggestions && message.suggestions.length > 0 && (
          <SuggestionChips suggestions={message.suggestions} onClick={onSuggestionClick} />
        )}
        {onFeedback && <ActionBar message={message} onFeedback={onFeedback} />}
      </EmmaMessageFlow>
    )
  }

  // ── Knowledge Report result ──
  if (message.report) {
    return (
      <EmmaMessageFlow>
        <div className="max-w-none">
          <ReportPanel report={message.report} content={message.content} />
        </div>
        {message.metadata?.explanation && (
          <ExplanationPanel explanation={message.metadata.explanation} />
        )}
      </EmmaMessageFlow>
    )
  }

  // ── HITL Review ──
  if (message.type === 'clarification' && message.metadata?.hitl_review && renderHITLReview) {
    return (
      <EmmaMessageFlow>
        {clarificationAnswered ? (
          <p className="text-sm text-muted-foreground/60 italic">{message.content}</p>
        ) : (
          renderHITLReview(message.metadata.hitl_review, message.id)
        )}
      </EmmaMessageFlow>
    )
  }

  // ── Clarification ──
  if (message.type === 'clarification' && message.metadata?.clarification) {
    const clarification = message.metadata.clarification as ClarificationData
    return (
      <EmmaMessageFlow>
        <p className="text-sm text-foreground/80 leading-relaxed">{clarification.question}</p>
        {!clarificationAnswered && clarification.options.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {clarification.options.map((opt, idx) => (
              <Button
                key={idx}
                variant="outline"
                size="sm"
                onClick={() => onSuggestionClick?.(opt.value)}
                className="text-xs h-7 border-amber-500/20 hover:bg-amber-500/5 hover:border-amber-500/30 transition-all"
              >
                {opt.label}
              </Button>
            ))}
          </div>
        )}
        {!clarificationAnswered && (
          <p className="text-[11px] text-muted-foreground/40 italic mt-1">
            o escribe tu propia búsqueda
          </p>
        )}
      </EmmaMessageFlow>
    )
  }

  // ── Error ──
  if (message.type === 'error') {
    return (
      <div className="w-full emma-message-enter py-2">
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center h-6 w-6 rounded-full bg-destructive/10 mt-0.5 shrink-0">
            <IconAlertCircle className="h-3.5 w-3.5 text-destructive" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-destructive/80 leading-relaxed">{message.content}</p>
            {message.metadata?.canRetry && message.metadata?.failedQuery && onRetry && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRetry(message.metadata!.failedQuery!)}
                className="mt-2 text-xs border-destructive/20 hover:bg-destructive/5"
              >
                <IconRotate className="h-3 w-3 mr-1.5" />
                Reintentar
              </Button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── User message ──
  if (message.type === 'user') {
    return <UserBubble message={message} />
  }

  // ── Emma response (main flow) ──
  // ── Emma response (main flow) ──
  return (
    <EmmaMessageFlow>
      {/* Activity timeline — island block */}
      {(message.metadata?.rawReasoningSteps?.length ?? 0) > 0 && (
        <ActivityTimeline
          steps={humanizeSteps(message.metadata!.rawReasoningSteps!)}
          isStreaming={false}
          executionTimeMs={message.metadata?.execution_time_ms}
        />
      )}

      {/* Agent routing */}
      {message.metadata?.agent && (
        <div className="flex items-center gap-2 text-xs mb-1">
          <span className="text-muted-foreground/40">
            {message.metadata.agent_reasoning || 'Procesado con'}
          </span>
          <IconArrowRight className="h-3 w-3 text-muted-foreground/20" />
          <span className="font-mono text-[11px] text-primary/60">
            {message.metadata.agent}
          </span>
        </div>
      )}

      {/* Response text — free-flowing, no card */}
      <EmmaMarkdown content={isNewResult ? streamedContent : message.content} />
      {isRevealing && (
        <span className="inline-block w-[3px] h-4 bg-primary/50 animate-pulse ml-0.5 align-middle rounded-full" />
      )}

      {/* Generated doc download — island block */}
      {message.content && (() => {
        const docIdMatch = message.content.match(/\b(gen_[a-f0-9]{8,})\b/)
        return docIdMatch?.[1] ? <GeneratedDocDownload docId={docIdMatch[1]} /> : null
      })()}

      {/* Related documents — inline source cards */}
      {message.metadata?.documents && message.metadata.documents.length > 0 && (
        <div className="mt-3 flex flex-col gap-3">
          {message.metadata.documents.map((doc, idx) => (
            <InlineSourceCard
              key={doc.id || idx}
              document={doc}
              onOpenFullscreen={onOpenFullscreen}
            />
          ))}
        </div>
      )}

      {/* Source evidence from graph_rag provenance */}
      {message.metadata?.sourceEvidence && message.metadata.sourceEvidence.length > 0 && (
        <SourceEvidence
          sources={message.metadata.sourceEvidence}
          onDocumentClick={(docId) => {
            const doc = { name: docId, id: docId } as DocumentInfo
            onOpenFullscreen?.(doc)
          }}
        />
      )}

      {/* Entity tags from graph_rag — clickable → knowledge graph */}
      {message.metadata?.entityTags && message.metadata.entityTags.length > 0 && (
        <EntityTags entities={message.metadata.entityTags} />
      )}

      {/* Explanation — island block */}
      {message.metadata?.explanation && (
        <ExplanationPanel explanation={message.metadata.explanation} />
      )}

      {/* Suggestions */}
      {message.suggestions && message.suggestions.length > 0 && (
        <SuggestionChips suggestions={message.suggestions} onClick={onSuggestionClick} />
      )}

      {/* Action bar */}
      {onFeedback && <ActionBar message={message} onFeedback={onFeedback} />}

      {/* Branch / command bar on hover */}
      {(renderBranchSwitcher || renderCommandBar) && (
        <div className="flex items-center gap-2 pt-1 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          {renderBranchSwitcher?.(message.id)}
          {renderCommandBar?.(message.id, message.content)}
        </div>
      )}
    </EmmaMessageFlow>
  )
}

// ── User message — right-aligned bubble ──

function UserBubble({ message }: { message: EmmaMessage }) {
  const { user } = useAuth()

  const initial = (() => {
    const name = user?.full_name || user?.email || ''
    if (!name) return 'U'
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    return name[0].toUpperCase()
  })()

  return (
    <div className="w-full emma-message-enter py-2">
      <div className="flex justify-end">
        <div className="flex items-end gap-2.5 max-w-[85%] sm:max-w-[75%]">
          <div className="min-w-0">
            {/* Attached documents */}
            {message.metadata?.documents && message.metadata.documents.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2 justify-end">
                {message.metadata.documents.map((doc, idx) => (
                  <div
                    key={doc.id || idx}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 bg-primary/5 border border-primary/10 rounded-lg text-[11px] font-mono text-muted-foreground"
                  >
                    <IconPaperclip className="h-3 w-3 shrink-0" />
                    <span className="max-w-[160px] truncate">{doc.name}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="rounded-2xl rounded-br-sm bg-primary/10 px-4 py-2.5">
              <p className="text-sm text-foreground leading-relaxed">{message.content}</p>
            </div>
          </div>
          <div
            className="h-7 w-7 rounded-full bg-primary/15 flex items-center justify-center shrink-0 mb-0.5"
            title={user?.full_name || user?.email || ''}
          >
            <span className="text-[11px] font-semibold text-primary/70 select-none">{initial}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Layout wrapper: Emma message with avatar ──

function EmmaMessageFlow({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full emma-message-enter py-2">
      <div className="group flex items-start gap-2.5 w-full">
        <img
          src="/emma-avatar.png"
          alt="Emma"
          className="h-7 w-7 rounded-full object-cover object-top shrink-0 mt-0.5"
        />
        <div className="min-w-0 flex-1 space-y-2 pt-0.5">
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Action bar: copy, feedback — appears on hover ──

function ActionBar({ message, onFeedback }: { message: EmmaMessage; onFeedback: (id: string, fb: 'positive' | 'negative') => void }) {
  const [copied, setCopied] = useState(false)
  const [showReasoning, setShowReasoning] = useState(false)

  const hasReasoningSteps = (message.metadata?.rawReasoningSteps?.length ?? 0) > 0

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <>
      <div className="flex items-center gap-1 pt-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground/30 hover:text-foreground/60 transition-colors"
          onClick={handleCopy}
          title={copied ? 'Copiado' : 'Copiar'}
        >
          {copied ? <IconCheck className="h-3.5 w-3.5 text-emerald-500" /> : <IconCopy className="h-3.5 w-3.5" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground/30 hover:text-emerald-500 transition-colors"
          onClick={() => onFeedback(message.id, 'positive')}
          title="Útil"
        >
          <IconThumbUp className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground/30 hover:text-destructive transition-colors"
          onClick={() => onFeedback(message.id, 'negative')}
          title="No útil"
        >
          <IconThumbDown className="h-3.5 w-3.5" />
        </Button>
        {hasReasoningSteps && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1 text-muted-foreground/30 hover:text-foreground/60 transition-colors px-2"
            onClick={() => setShowReasoning(true)}
            title="Ver razonamiento"
          >
            <IconRoute size={14} />
            Ver Razonamiento
          </Button>
        )}
        {message.metadata?.execution_time_ms && (
          <span className="text-[10px] font-mono text-muted-foreground/25 ml-auto tabular-nums">
            {message.metadata.execution_time_ms < 1000
              ? `${Math.round(message.metadata.execution_time_ms)}ms`
              : `${(message.metadata.execution_time_ms / 1000).toFixed(1)}s`}
          </span>
        )}
      </div>
      {showReasoning && (
        <ReasoningModal
          reasoningSteps={message.metadata!.rawReasoningSteps!}
          sources={message.metadata?.documents}
          executionTimeMs={message.metadata?.execution_time_ms}
          onClose={() => setShowReasoning(false)}
        />
      )}
    </>
  )
}

// ── Suggestion chips ──

function SuggestionChips({ suggestions, onClick }: { suggestions: string[]; onClick?: (s: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {suggestions.map((suggestion, idx) => (
        <Button
          key={idx}
          variant="outline"
          size="sm"
          onClick={() => onClick?.(suggestion)}
          className="text-xs h-7 border-border/50 hover:bg-accent/50 transition-all"
        >
          {suggestion}
        </Button>
      ))}
    </div>
  )
}
