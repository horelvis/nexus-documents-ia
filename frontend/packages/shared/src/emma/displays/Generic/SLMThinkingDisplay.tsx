"use client"

import { motion, AnimatePresence } from "framer-motion"
import { cn } from "../../../lib"
import {
  Search,
  Lightbulb,
  GitBranch,
  Database,
  FileSearch,
  HelpCircle,
  Check,
  Loader2,
  Brain
} from "lucide-react"
import type { SLMThinkingStep, SLMPlanReady } from "../../types"

// =============================================================================
// Step Configuration - Icons and colors for each thinking step type
// =============================================================================

const stepConfig: Record<string, {
  icon: React.ReactNode
  color: string
  bgColor: string
  label: string
}> = {
  entity_detection: {
    icon: <Search className="h-4 w-4" />,
    color: "text-cyan-500 dark:text-cyan-400",
    bgColor: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Entidades"
  },
  intent_detection: {
    icon: <Lightbulb className="h-4 w-4" />,
    color: "text-yellow-500 dark:text-yellow-400",
    bgColor: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "Intención"
  },
  route_decision: {
    icon: <GitBranch className="h-4 w-4" />,
    color: "text-purple-500 dark:text-purple-400",
    bgColor: "bg-purple-100 dark:bg-purple-900/40",
    label: "Decisión"
  }
}

// Route badges with icons
const routeConfig: Record<string, {
  icon: React.ReactNode
  color: string
  bgColor: string
  label: string
}> = {
  GRAPH_ONLY: {
    icon: <Database className="h-3.5 w-3.5" />,
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Graph"
  },
  VECTOR_ONLY: {
    icon: <FileSearch className="h-3.5 w-3.5" />,
    color: "text-blue-600 dark:text-blue-400",
    bgColor: "bg-blue-100 dark:bg-blue-900/40",
    label: "Semántico"
  },
  HYBRID: {
    icon: <Brain className="h-3.5 w-3.5" />,
    color: "text-violet-600 dark:text-violet-400",
    bgColor: "bg-violet-100 dark:bg-violet-900/40",
    label: "Híbrido"
  },
  ASK_CLARIFY: {
    icon: <HelpCircle className="h-3.5 w-3.5" />,
    color: "text-orange-600 dark:text-orange-400",
    bgColor: "bg-orange-100 dark:bg-orange-900/40",
    label: "Clarificar"
  }
}

// =============================================================================
// Component Props
// =============================================================================

interface SLMThinkingDisplayProps {
  /** Current thinking steps being displayed */
  thinkingSteps: SLMThinkingStep[]
  /** Whether thinking is in progress */
  isThinking: boolean
  /** The generated plan (when ready) */
  planReady?: SLMPlanReady | null
  /** Whether execution is in progress */
  isExecuting?: boolean
  /** Additional CSS classes */
  className?: string
}

// =============================================================================
// Main Component
// =============================================================================

export function SLMThinkingDisplay({
  thinkingSteps,
  isThinking,
  planReady,
  isExecuting = false,
  className
}: SLMThinkingDisplayProps) {
  const hasSteps = thinkingSteps.length > 0

  // If no steps and not thinking, don't render anything
  if (!hasSteps && !isThinking && !planReady) {
    return null
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-lg border border-border/50 overflow-hidden",
        "bg-muted/30",
        className
      )}
    >
      {/* Header with brain icon */}
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <motion.div
          animate={isThinking ? { rotate: [0, 10, -10, 0] } : {}}
          transition={{ duration: 0.5, repeat: isThinking ? Infinity : 0 }}
          className="text-primary"
        >
          <Brain className="h-4 w-4" />
        </motion.div>
        <span className="text-xs font-medium text-muted-foreground">
          {isThinking ? "Razonando..." : planReady ? "Plan generado" : "Análisis"}
        </span>
        {isThinking && (
          <Loader2 className="h-3 w-3 ml-auto animate-spin text-muted-foreground" />
        )}
      </div>

      {/* Thinking Steps */}
      <div className="p-3 space-y-2">
        <AnimatePresence mode="popLayout">
          {thinkingSteps.map((step, idx) => {
            const config = stepConfig[step.type] || stepConfig.entity_detection
            const isLast = idx === thinkingSteps.length - 1 && isThinking

            return (
              <motion.div
                key={`${step.step}-${step.type}`}
                initial={{ opacity: 0, x: -10, height: 0 }}
                animate={{ opacity: 1, x: 0, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2, delay: idx * 0.05 }}
                className="flex items-start gap-2"
              >
                {/* Step icon */}
                <div className={cn(
                  "flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center",
                  config.bgColor, config.color
                )}>
                  {isLast ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                    >
                      {config.icon}
                    </motion.div>
                  ) : (
                    config.icon
                  )}
                </div>

                {/* Step content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={cn(
                      "text-xs font-medium px-1.5 py-0.5 rounded",
                      config.bgColor, config.color
                    )}>
                      {config.label}
                    </span>
                    {step.entities.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {step.entities.slice(0, 3).map((entity, i) => (
                          <span
                            key={i}
                            className="text-xs px-1.5 py-0.5 rounded bg-background border border-border text-foreground"
                          >
                            {entity}
                          </span>
                        ))}
                        {step.entities.length > 3 && (
                          <span className="text-xs text-muted-foreground">
                            +{step.entities.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                    {step.content}
                  </p>
                </div>

                {/* Completion check */}
                {!isLast && (
                  <Check className="h-3.5 w-3.5 text-green-500 flex-shrink-0 mt-1" />
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>

        {/* Plan Ready Badge */}
        <AnimatePresence>
          {planReady && (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mt-3 pt-3 border-t border-border/50"
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                {/* Route badge */}
                <div className="flex items-center gap-2">
                  {(() => {
                    const routeCfg = routeConfig[planReady.route] || routeConfig.VECTOR_ONLY
                    return (
                      <span className={cn(
                        "inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full",
                        routeCfg.bgColor, routeCfg.color
                      )}>
                        {routeCfg.icon}
                        {routeCfg.label}
                      </span>
                    )
                  })()}

                  {/* Entities count */}
                  {planReady.entities_count > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {planReady.entities_count} entidades
                    </span>
                  )}
                </div>

                {/* Confidence */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">
                    Confianza:
                  </span>
                  <span className={cn(
                    "text-xs font-medium",
                    planReady.confidence >= 0.8 ? "text-green-600 dark:text-green-400" :
                    planReady.confidence >= 0.6 ? "text-yellow-600 dark:text-yellow-400" :
                    "text-orange-600 dark:text-orange-400"
                  )}>
                    {Math.round(planReady.confidence * 100)}%
                  </span>
                </div>
              </div>

              {/* Executing indicator */}
              {isExecuting && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"
                >
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Ejecutando consulta...
                </motion.div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
