'use client'

import { useState, useEffect, useRef } from 'react'
import {
  IconChevronDown,
  IconBrain,
  IconSearch,
  IconBulb,
  IconGitBranch,
  IconTool,
  IconEye,
  IconMessageCircle,
  IconAlertCircle,
  IconCircleCheck,
  IconPlugConnected,
  IconDatabase,
  IconTransform,
  IconShieldCheck,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { ReasoningStep, ReasoningStepType } from '@/lib/types/emma'

interface ReasoningCollapsibleProps {
  steps: ReasoningStep[]
  className?: string
}

/**
 * Collapsible reasoning display with Shadcn-like behavior:
 * - Auto-expand when reasoning starts
 * - Shimmer effect during active thinking
 * - Duration tracking ("Thought for X seconds")
 * - Auto-collapse when done
 * - Click to re-expand
 */
export function ReasoningCollapsible({
  steps,
  className,
}: ReasoningCollapsibleProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [userInteracted, setUserInteracted] = useState(false) // Track if user manually toggled
  const prevStepCount = useRef(0)

  // Auto-expand when new steps arrive (unless user manually toggled)
  useEffect(() => {
    if (steps.length > prevStepCount.current && steps.length > 0 && !userInteracted) {
      setIsExpanded(true)
    }
    prevStepCount.current = steps.length
  }, [steps.length, userInteracted])

  // Auto-collapse after steps stabilize (reasoning done) — 1.5s debounce
  useEffect(() => {
    if (steps.length === 0 || userInteracted) return
    const timer = setTimeout(() => {
      setIsExpanded(false)
    }, 1500)
    return () => clearTimeout(timer)
  }, [steps.length, userInteracted])

  // Don't render if no steps
  if (steps.length === 0) return null

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded)
    setUserInteracted(true) // User manually toggled, disable auto-collapse
  }

  return (
    <div className={cn('rounded-lg overflow-hidden', className)}>
      {/* Header - always visible, clickable to expand/collapse */}
      <button
        onClick={toggleExpanded}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-left transition-all duration-200',
          'bg-primary/5 hover:bg-primary/10 border border-primary/20 rounded-lg',
          isExpanded && 'rounded-b-none border-b-0',
        )}
      >
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-primary/70 block">
            Plan de ejecución
          </span>
          {steps.length > 0 && (
            <span className="text-[11px] font-mono text-foreground/80 block truncate">
              {steps[steps.length - 1].content}
            </span>
          )}
        </div>

        {/* Steps count */}
        {steps.length > 0 && (
          <Badge variant="outline" className="text-[10px] font-mono shrink-0">
            {steps.length}
          </Badge>
        )}

        {/* Expand/collapse indicator */}
        <IconChevronDown className={cn(
          'h-4 w-4 text-primary/60 transition-transform duration-200',
          isExpanded && 'rotate-180'
        )} />
      </button>

      {/* Collapsible content */}
      <div className={cn(
        'transition-all duration-300 ease-in-out overflow-hidden',
        isExpanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'
      )}>
        <div className="px-3 py-2 space-y-1.5 bg-primary/5 border border-t-0 border-primary/20 rounded-b-lg">
          {steps.map((step, idx) => (
            <ReasoningStepItem
              key={`${step.type}-${idx}`}
              step={step}
              isLast={idx === steps.length - 1}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// Typewriter effect hook for streaming-like text display
function useTypewriter(text: string, speed: number = 15, enabled: boolean = true) {
  const [displayedText, setDisplayedText] = useState('')
  const [isComplete, setIsComplete] = useState(false)

  useEffect(() => {
    if (!enabled) {
      setDisplayedText(text)
      setIsComplete(true)
      return
    }

    setDisplayedText('')
    setIsComplete(false)

    if (!text) return

    let currentIndex = 0
    const interval = setInterval(() => {
      if (currentIndex < text.length) {
        // Add characters in small chunks for smoother effect
        const chunkSize = Math.min(3, text.length - currentIndex)
        setDisplayedText(text.slice(0, currentIndex + chunkSize))
        currentIndex += chunkSize
      } else {
        setIsComplete(true)
        clearInterval(interval)
      }
    }, speed)

    return () => clearInterval(interval)
  }, [text, speed, enabled])

  return { displayedText, isComplete }
}

// Individual reasoning step display
function ReasoningStepItem({ step, isLast }: { step: ReasoningStep; isLast: boolean }) {
  const { icon: StepIcon, label, color } = getStepConfig(step.type)
  const { displayedText, isComplete } = useTypewriter(step.content, 15, isLast)

  // Show full text for completed steps, animated text for current step
  const textToShow = isLast ? displayedText : step.content
  const showCursor = isLast && !isComplete

  return (
    <div className="flex items-start gap-2 animate-in fade-in slide-in-from-left-2 duration-200">
      <div className={cn('flex items-center justify-center h-4 w-4 shrink-0 mt-0.5', color)}>
        <StepIcon className="h-3 w-3" />
      </div>

      <div className="flex-1 min-w-0 text-xs font-mono">
        <span className={cn('uppercase', color)}>{label}:</span>{' '}
        <span className="text-foreground/70">{textToShow}</span>
        {showCursor && (
          <span className="inline-block w-1.5 h-3.5 bg-primary/70 animate-pulse ml-0.5 align-middle" />
        )}

        {/* Entities if present - show after typing completes */}
        {step.entities && step.entities.length > 0 && (!isLast || isComplete) && (
          <div className="flex flex-wrap gap-1 mt-1">
            {step.entities.map((entity, idx) => (
              <Badge
                key={idx}
                variant="outline"
                className="text-[10px] py-0 font-mono bg-primary/10 text-primary border-primary/20"
              >
                {entity}
              </Badge>
            ))}
          </div>
        )}

        {/* Confidence indicator - show after typing completes */}
        {step.confidence !== undefined && step.confidence < 1.0 && (!isLast || isComplete) && (
          <span className="ml-2 text-[10px] text-muted-foreground">
            ({Math.round(step.confidence * 100)}%)
          </span>
        )}
      </div>
    </div>
  )
}

// Configuration for step type icons and labels
function getStepConfig(type: ReasoningStepType): { icon: typeof IconBrain; label: string; color: string } {
  switch (type) {
    case 'query_analysis':
      return { icon: IconSearch, label: 'Analysis', color: 'text-blue-500' }
    case 'routing':
      return { icon: IconGitBranch, label: 'Route', color: 'text-purple-500' }
    case 'thinking':
      return { icon: IconBrain, label: 'Thinking', color: 'text-primary' }
    case 'tool_call':
      return { icon: IconTool, label: 'Tool', color: 'text-amber-500' }
    case 'tool_execution':
      return { icon: IconTool, label: 'Executing', color: 'text-amber-500' }
    case 'observation':
      return { icon: IconEye, label: 'Observed', color: 'text-cyan-500' }
    case 'reflection':
      return { icon: IconMessageCircle, label: 'Reflection', color: 'text-indigo-500' }
    case 'connection':
      return { icon: IconPlugConnected, label: 'Connect', color: 'text-emerald-500' }
    case 'connector':
      return { icon: IconDatabase, label: 'Connector', color: 'text-emerald-500' }
    case 'search':
      return { icon: IconSearch, label: 'Search', color: 'text-blue-500' }
    case 'data_extraction':
      return { icon: IconDatabase, label: 'Extract', color: 'text-teal-500' }
    case 'transformation':
      return { icon: IconTransform, label: 'Transform', color: 'text-orange-500' }
    case 'validation':
      return { icon: IconShieldCheck, label: 'Validate', color: 'text-green-500' }
    case 'response':
      return { icon: IconCircleCheck, label: 'Response', color: 'text-emerald-500' }
    case 'error':
      return { icon: IconAlertCircle, label: 'Error', color: 'text-destructive' }
    // LangGraph specific types
    case 'retrieval':
      return { icon: IconSearch, label: 'Retrieval', color: 'text-blue-500' }
    case 'domain_detection':
      return { icon: IconBulb, label: 'Domain', color: 'text-indigo-500' }
    case 'agent_selection':
      return { icon: IconGitBranch, label: 'Agents', color: 'text-purple-500' }
    case 'agent_execution':
      return { icon: IconBrain, label: 'Exec', color: 'text-primary' }
    case 'structural':
      return { icon: IconDatabase, label: 'Structural', color: 'text-teal-500' }
    case 'entity_detection':
      return { icon: IconSearch, label: 'Entities', color: 'text-blue-500' }
    case 'intent_detection':
      return { icon: IconBulb, label: 'Intent', color: 'text-amber-500' }
    case 'route_decision':
      return { icon: IconGitBranch, label: 'Route', color: 'text-purple-500' }
    case 'custom':
    default:
      return { icon: IconBulb, label: 'Step', color: 'text-muted-foreground' }
  }
}

export default ReasoningCollapsible
