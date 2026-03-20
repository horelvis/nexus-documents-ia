'use client'

import { useState, useEffect, useRef } from 'react'
import {
  IconChevronDown,
  IconBrain,
  IconSearch,
  IconBulb,
  IconGitBranch,
  IconAlertCircle,
  IconCircleCheck,
  IconPlugConnected,
  IconDatabase,
  IconFileText,
  IconWorld,
  IconList,
  IconFileSearch,
  IconFileCheck,
  IconCheck,
  IconLoader2,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { ReasoningStep, ReasoningStepType } from '@/lib/types/emma'

interface ReasoningCollapsibleProps {
  steps: ReasoningStep[]
  /** Whether the agent is still actively producing steps */
  isActive?: boolean
  className?: string
}

/**
 * Timeline-based reasoning display with vertical connector line.
 *
 * Visual structure per step:
 *   [circular node] ---- text content ---- [status]
 *        |
 *   [vertical line]
 *        |
 *   [circular node] ---- text content ---- [status]
 *
 * - Auto-expand when reasoning starts
 * - Auto-collapse when done
 * - Click to re-expand
 */
export function ReasoningCollapsible({
  steps,
  isActive = true,
  className,
}: ReasoningCollapsibleProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [userInteracted, setUserInteracted] = useState(false)
  const prevStepCount = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-expand when new steps arrive (unless user manually toggled)
  useEffect(() => {
    if (steps.length > prevStepCount.current && steps.length > 0 && !userInteracted) {
      setIsExpanded(true)
    }
    prevStepCount.current = steps.length
  }, [steps.length, userInteracted])

  // Auto-collapse when analysis finishes (isActive goes false)
  useEffect(() => {
    if (!isActive && steps.length > 0 && !userInteracted) {
      const timer = setTimeout(() => {
        setIsExpanded(false)
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [isActive, steps.length, userInteracted])

  // Auto-scroll to bottom when new steps arrive
  useEffect(() => {
    if (isExpanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [steps.length, isExpanded])

  if (steps.length === 0) return null

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded)
    setUserInteracted(true)
  }

  return (
    <div className={cn('rounded-lg overflow-hidden', className)}>
      {/* Header */}
      <button
        onClick={toggleExpanded}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-left transition-all duration-200',
          'bg-muted/30 hover:bg-muted/50 border border-border/50 rounded-lg',
          isExpanded && 'rounded-b-none border-b-0',
        )}
      >
        <div className="flex-1 min-w-0">
          <span className="text-xs text-muted-foreground">
            {isActive ? `Analizando... (${steps.length})` : `Analisis completado (${steps.length} pasos)`}
          </span>
        </div>

        <IconChevronDown className={cn(
          'h-4 w-4 text-muted-foreground transition-transform duration-200',
          isExpanded && 'rotate-180'
        )} />
      </button>

      {/* Collapsible content */}
      <div className={cn(
        'transition-all duration-300 ease-in-out overflow-hidden',
        isExpanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'
      )}>
        <div
          ref={scrollRef}
          className="px-3 py-3 bg-muted/30 border border-t-0 border-border/50 rounded-b-lg overflow-y-auto max-h-[480px]"
        >
          {steps.map((step, idx) => (
            <TimelineStepItem
              key={`${step.type}-${idx}`}
              step={step}
              index={idx}
              isLast={idx === steps.length - 1}
              isActive={isActive}
            />
          ))}

          {/* Loading indicator at the end of the timeline */}
          {isActive && steps.length > 0 && (
            <div className="relative pl-7">
              <div className="absolute left-[7px] top-1 h-5 w-5 rounded-full bg-primary/10 border-2 border-primary/40 flex items-center justify-center">
                <IconLoader2 className="h-2.5 w-2.5 text-primary animate-spin" />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Individual timeline step with vertical connector line.
 *
 * Layout:
 *   [node circle]  step text              [status]
 *       |
 *   [connector line to next]
 */
function TimelineStepItem({
  step,
  index,
  isLast,
  isActive,
}: {
  step: ReasoningStep
  index: number
  isLast: boolean
  isActive: boolean
}) {
  const { icon: StepIcon, color, bgColor } = getStepConfig(step.type)
  const isThinking = step.type === 'thinking'
  const showConnector = !isLast || isActive

  return (
    <div className="relative pl-7 pb-3 last:pb-0 animate-in fade-in slide-in-from-top-1 duration-300">
      {/* Vertical connector line */}
      {showConnector && (
        <div
          className={cn(
            'absolute left-[9px] top-[18px] w-[2px] rounded-full',
            isLast ? 'h-[calc(100%)] bg-gradient-to-b from-border/60 to-transparent' : 'h-full bg-border/60',
          )}
        />
      )}

      {/* Timeline node (circle with icon) */}
      <div
        className={cn(
          'absolute left-0 top-[2px] h-5 w-5 rounded-full flex items-center justify-center',
          'border-2 transition-colors duration-300',
          isLast && isActive
            ? 'border-primary/60 bg-primary/10'
            : step.type === 'error'
              ? 'border-destructive/40 bg-destructive/10'
              : 'border-border bg-muted/80',
        )}
      >
        <StepIcon className={cn('h-2.5 w-2.5', color)} />
      </div>

      {/* Step content */}
      <div className="flex items-start gap-2 min-h-[20px]">
        <span className={cn(
          'flex-1 min-w-0 text-[13px] leading-snug',
          isThinking
            ? 'italic text-muted-foreground'
            : 'text-foreground/80'
        )}>
          {step.content}
        </span>

        {/* Status indicator */}
        <div className="shrink-0 w-4 h-4 flex items-center justify-center mt-0.5">
          {isLast && isActive ? (
            <span className="block w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          ) : (
            <IconCheck className="h-3 w-3 text-muted-foreground/50" />
          )}
        </div>
      </div>
    </div>
  )
}

// Semantic step type -> icon + color
function getStepConfig(type: ReasoningStepType): {
  icon: typeof IconBrain
  color: string
  bgColor: string
} {
  switch (type) {
    case 'searching':
      return { icon: IconSearch, color: 'text-blue-500', bgColor: 'bg-blue-500/10' }
    case 'reading':
      return { icon: IconFileText, color: 'text-amber-500', bgColor: 'bg-amber-500/10' }
    case 'analyzing':
      return { icon: IconBrain, color: 'text-purple-500', bgColor: 'bg-purple-500/10' }
    case 'querying':
      return { icon: IconDatabase, color: 'text-teal-500', bgColor: 'bg-teal-500/10' }
    case 'browsing':
      return { icon: IconWorld, color: 'text-blue-400', bgColor: 'bg-blue-400/10' }
    case 'listing':
      return { icon: IconList, color: 'text-gray-500', bgColor: 'bg-gray-500/10' }
    case 'connecting':
      return { icon: IconPlugConnected, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10' }
    case 'preparing':
      return { icon: IconCircleCheck, color: 'text-green-500', bgColor: 'bg-green-500/10' }
    case 'search_result':
      return { icon: IconFileSearch, color: 'text-blue-500', bgColor: 'bg-blue-500/10' }
    case 'doc_read':
      return { icon: IconFileCheck, color: 'text-amber-500', bgColor: 'bg-amber-500/10' }
    case 'thinking':
      return { icon: IconBrain, color: 'text-muted-foreground', bgColor: 'bg-muted' }
    case 'error':
      return { icon: IconAlertCircle, color: 'text-destructive', bgColor: 'bg-destructive/10' }
    case 'swarm_decompose':
      return { icon: IconGitBranch, color: 'text-purple-500', bgColor: 'bg-purple-500/10' }
    case 'swarm_worker':
      return { icon: IconBrain, color: 'text-primary', bgColor: 'bg-primary/10' }
    case 'swarm_worker_done':
      return { icon: IconCircleCheck, color: 'text-emerald-500', bgColor: 'bg-emerald-500/10' }
    case 'swarm_synthesize':
      return { icon: IconBrain, color: 'text-indigo-500', bgColor: 'bg-indigo-500/10' }
    default:
      return { icon: IconBulb, color: 'text-muted-foreground', bgColor: 'bg-muted' }
  }
}

export default ReasoningCollapsible
