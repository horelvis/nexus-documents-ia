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
  IconChevronRight,
  IconListCheck,
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
  if (ms < 1000) return `${Math.round(ms)}ms`
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
          "text-xs leading-tight",
          isCompleted ? "text-muted-foreground" : "font-semibold text-foreground",
        )}
      >
        {step.text}
      </span>
    </div>
  )
}

export function ActivityTimeline({ steps, isStreaming, executionTimeMs, className }: ActivityTimelineProps) {
  // During streaming: auto-expanded; after completion: collapsed by default
  const [isOpen, setIsOpen] = useState(isStreaming)

  if (steps.length === 0) return null

  const allCompleted = steps.every((s) => s.status === "completed")

  // Build header text
  const headerText = isStreaming
    ? "Proceso de análisis"
    : (() => {
        const parts = [`${steps.length} paso${steps.length !== 1 ? "s" : ""}`]
        if (executionTimeMs !== undefined) parts.push(formatTime(executionTimeMs))
        return `Proceso de análisis · ${parts.join(" · ")}`
      })()

  return (
    <div className={cn("mt-2 rounded-lg border border-border/50 bg-muted/30", className)}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={isOpen}
      >
        <IconChevronRight
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            isOpen && "rotate-90",
          )}
        />
        <IconListCheck className="h-3.5 w-3.5" />
        <span className="font-medium">{headerText}</span>
        {isStreaming && (
          <span className="ml-auto h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
        )}
      </button>

      {isOpen && (
        <div className="px-3 pb-3 space-y-1.5 animate-in fade-in-0 duration-200">
          {steps.map((step) => (
            <StepRow key={step.id} step={step} />
          ))}
          {isStreaming && allCompleted && (
            <div className="flex items-center gap-2 animate-in fade-in-50 duration-300">
              <div className="relative flex-shrink-0">
                <IconPencil className="h-3.5 w-3.5 text-blue-400" />
                <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-blue-400 animate-pulse" />
              </div>
              <span className="text-xs font-semibold text-foreground leading-tight">
                Redactando respuesta...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
