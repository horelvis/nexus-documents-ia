"use client"

import React, { useState } from "react"
import { cn } from "../../../lib"
import { ChevronRight } from "lucide-react"

interface ExplanationPanelProps {
  explanation: string | null
  isLoading?: boolean
  title?: string
  className?: string
}

export function ExplanationPanel({ explanation, isLoading, title = "Así lo resolví", className }: ExplanationPanelProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (!explanation && !isLoading) return null

  return (
    <div className={cn("mt-2 rounded-lg border border-border/50 bg-muted/30", className)}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={isOpen}
      >
        <ChevronRight
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            isOpen && "rotate-90",
          )}
        />
        <span className="font-medium">{title}</span>
      </button>

      {isOpen && (
        <div className="px-3 pb-3 text-sm text-muted-foreground leading-relaxed animate-in fade-in-0 duration-200">
          {isLoading ? (
            <div className="space-y-2">
              <div className="h-3 w-3/4 rounded bg-muted animate-pulse" />
              <div className="h-3 w-1/2 rounded bg-muted animate-pulse" />
            </div>
          ) : (
            <p>{explanation}</p>
          )}
        </div>
      )}
    </div>
  )
}
