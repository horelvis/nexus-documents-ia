"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
  IconSearch,
  IconFileText,
  IconChartBar,
  IconWorld,
  IconScale,
  IconPencil,
  IconCircleCheck,
  IconChevronDown,
} from "@tabler/icons-react"
import type { ActivityIcon, ActivityStep } from "./utils/humanizeStep"

interface ActivityTimelineProps {
  steps: ActivityStep[]
  isStreaming: boolean
  executionTimeMs?: number
  className?: string
}

const ICON_MAP: Record<ActivityIcon, React.ComponentType<{ className?: string }>> = {
  search: IconSearch,
  read: IconFileText,
  analyze: IconChartBar,
  web: IconWorld,
  legal: IconScale,
  write: IconPencil,
  done: IconCircleCheck,
}

function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function StepRow({ step }: { step: ActivityStep }) {
  const Icon = ICON_MAP[step.icon]
  const isCompleted = step.status === "completed"

  return (
    <div className="flex items-center gap-2 animate-in fade-in-50 duration-300">
      <div className="relative flex-shrink-0">
        {isCompleted ? (
          <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500/60" />
        ) : (
          <>
            <Icon className="h-3.5 w-3.5 text-blue-400" />
            <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
          </>
        )}
      </div>
      <span
        className={cn(
          "text-xs leading-none",
          isCompleted ? "text-muted-foreground" : "font-semibold text-foreground",
        )}
      >
        {step.text}
      </span>
    </div>
  )
}

export function ActivityTimeline({ steps, isStreaming, executionTimeMs, className }: ActivityTimelineProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (steps.length === 0) return null

  const allCompleted = steps.every((s) => s.status === "completed")

  if (isStreaming) {
    return (
      <div className={cn("flex flex-col gap-1.5", className)}>
        {steps.map((step) => (
          <StepRow key={step.id} step={step} />
        ))}
        {allCompleted && (
          <div className="flex items-center gap-2 animate-in fade-in-50 duration-300">
            <div className="relative flex-shrink-0">
              <IconPencil className="h-3.5 w-3.5 text-blue-400" />
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
            </div>
            <span className="text-xs font-semibold text-foreground leading-none">
              Redactando respuesta...
            </span>
          </div>
        )}
      </div>
    )
  }

  // Post-streaming: collapsible
  const summary = [
    `${steps.length} paso${steps.length !== 1 ? "s" : ""}`,
    executionTimeMs !== undefined ? formatTime(executionTimeMs) : null,
  ]
    .filter(Boolean)
    .join(" · ")

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {!isExpanded ? (
        <button
          onClick={() => setIsExpanded(true)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
        >
          <IconChevronDown className="h-3 w-3" />
          <span>{summary}</span>
        </button>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            {steps.map((step) => (
              <StepRow key={step.id} step={step} />
            ))}
          </div>
          <button
            onClick={() => setIsExpanded(false)}
            className="mt-1 text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
          >
            colapsar
          </button>
        </>
      )}
    </div>
  )
}
