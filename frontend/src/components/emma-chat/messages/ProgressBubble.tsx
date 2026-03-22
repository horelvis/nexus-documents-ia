'use client'

import { IconArrowRight } from '@tabler/icons-react'
import type { EmmaMessage } from '@/lib/types/emma'
import { ActivityTimeline } from '../ActivityTimeline'
import { humanizeSteps } from '../utils/humanizeStep'
import { EmmaMarkdown } from '../EmmaMarkdown'
import { WorkflowStepItem } from './WorkflowStepItem'

export function ProgressBubble({ message }: { message: EmmaMessage }) {
  const workflowSteps = message.metadata?.workflow_steps || []
  const hasSteps = workflowSteps.length > 0
  const isStreaming = message.metadata?.isStreaming
  const hasContent = message.content && message.content.trim().length > 0
  const streamingText = message.metadata?.streaming_text || ''
  const hasStreamingText = streamingText.trim().length > 0
  const slmIsThinking = message.metadata?.slmIsThinking ?? false

  const currentAgent = message.metadata?.agent ||
    workflowSteps.find(s => s.status === 'in_progress')?.agent ||
    'Emma'

  const displayContent = hasStreamingText ? streamingText : (hasContent ? message.content : '')
  const showContent = displayContent.trim().length > 0

  return (
    <div className="w-full emma-message-enter py-3">
      <div className="flex items-start gap-3">
        <div className="relative shrink-0 mt-0.5">
          <img src="/emma-avatar.png" alt="Emma" className="h-7 w-7 rounded-full object-cover object-top" />
          <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-primary ring-2 ring-background animate-pulse" />
        </div>

        <div className="min-w-0 flex-1 space-y-2 pt-0.5">
          {/* Agent routing */}
          {currentAgent && currentAgent !== 'Emma' && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground/40">Procesando con</span>
              <IconArrowRight className="h-3 w-3 text-muted-foreground/20" />
              <span className="font-mono text-[11px] text-primary/60">{currentAgent}</span>
            </div>
          )}

          {/* Activity timeline */}
          {(message.metadata?.rawReasoningSteps?.length ?? 0) > 0 && (
            <ActivityTimeline
              steps={humanizeSteps(message.metadata!.rawReasoningSteps!)}
              isStreaming={true}
            />
          )}

          {/* Workflow steps */}
          {hasSteps && (
            <div className="space-y-1.5">
              {workflowSteps.map((step, idx) => (
                <WorkflowStepItem key={step.index} step={step} index={idx} />
              ))}
            </div>
          )}

          {/* Content */}
          {showContent ? (
            <div className="relative">
              <EmmaMarkdown content={displayContent} />
              {isStreaming && (
                <span className="inline-block w-[3px] h-4 bg-primary/50 animate-pulse ml-0.5 align-middle rounded-full" />
              )}
            </div>
          ) : !slmIsThinking && !hasSteps ? (
            <ThinkingDots />
          ) : null}
        </div>
      </div>
    </div>
  )
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5">
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 emma-typing-dot" />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 emma-typing-dot" style={{ animationDelay: '0.2s' }} />
      <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 emma-typing-dot" style={{ animationDelay: '0.4s' }} />
    </div>
  )
}
