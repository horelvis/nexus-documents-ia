"use client"

import React from "react"
import { cn } from "../../../lib"
import { Brain, Search, BarChart3, PenLine, Check } from "lucide-react"

export type PhaseId = "understanding" | "searching" | "analyzing" | "responding"
export type PhaseStatus = "pending" | "active" | "completed"

export interface Phase {
  id: PhaseId
  label: string
  status: PhaseStatus
}

interface PhaseBreadcrumbProps {
  phases: Phase[]
  currentPhase: string | null
  className?: string
}

const PHASE_ICONS: Record<PhaseId, React.ElementType> = {
  understanding: Brain,
  searching: Search,
  analyzing: BarChart3,
  responding: PenLine,
}

export function PhaseBreadcrumb({ phases, currentPhase, className }: PhaseBreadcrumbProps) {
  if (!currentPhase) return null

  return (
    <div className={cn("flex items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground", className)}>
      {phases.map((phase, idx) => {
        const Icon = PHASE_ICONS[phase.id]
        return (
          <React.Fragment key={phase.id}>
            {idx > 0 && (
              <span className="text-muted-foreground/40">&rarr;</span>
            )}
            <span
              className={cn(
                "flex items-center gap-1 transition-all duration-300",
                phase.status === "active" && "text-foreground font-medium",
                phase.status === "completed" && "text-muted-foreground/60",
                phase.status === "pending" && "text-muted-foreground/30",
              )}
            >
              {phase.status === "completed" ? (
                <Check className="h-3 w-3 text-green-500/60" />
              ) : (
                <Icon className="h-3 w-3" />
              )}
              {phase.status === "active" && (
                <>
                  <span>{phase.label}</span>
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                </>
              )}
            </span>
          </React.Fragment>
        )
      })}
    </div>
  )
}
