"use client"

import { useState, Fragment } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "../../../lib"
import {
  Brain,
  ChevronDown,
  ListChecks,
  FileText,
  Route,
  ArrowRight,
  Check,
  Loader2,
  AlertCircle,
  Search,
  Database,
  FileSearch,
  Sparkles,
  Clock
} from "lucide-react"
import { Badge } from "../../../ui/badge"
import type { Citation, WorkflowStep, SLMPlanReady } from "../../types"

// =============================================================================
// Types
// =============================================================================

export interface ReasoningDisplayProps {
  /** Pasos del proceso (workflow) */
  workflowSteps?: WorkflowStep[]

  /** Fuentes/contexto usado */
  sources?: Citation[]

  /** Ruta de decisión (SLM Router) */
  decisionPath?: string[]

  /** Plan del SLM Router */
  slmPlan?: SLMPlanReady

  /** Tiempo total de ejecución */
  executionTimeMs?: number

  /** Puntuación de confianza */
  confidence?: number

  /** Expandido por defecto */
  defaultExpanded?: boolean

  /** Clases CSS adicionales */
  className?: string
}

// =============================================================================
// Step Status Config
// =============================================================================

const stepStatusConfig: Record<WorkflowStep['status'], {
  icon: React.ReactNode
  color: string
  bgColor: string
}> = {
  completed: {
    icon: <Check className="h-3 w-3" />,
    color: "text-green-500 dark:text-green-400",
    bgColor: "bg-green-500 border-green-500"
  },
  in_progress: {
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    color: "text-primary",
    bgColor: "bg-primary border-primary animate-pulse"
  },
  pending: {
    icon: null,
    color: "text-muted-foreground",
    bgColor: "bg-background border-border"
  },
  error: {
    icon: <AlertCircle className="h-3 w-3" />,
    color: "text-destructive",
    bgColor: "bg-destructive border-destructive"
  }
}

// Route type icons for decision path
const routeIcons: Record<string, React.ReactNode> = {
  'GRAPH_ONLY': <Database className="h-3 w-3" />,
  'VECTOR_ONLY': <FileSearch className="h-3 w-3" />,
  'HYBRID': <Sparkles className="h-3 w-3" />,
  'SLM Router': <Brain className="h-3 w-3" />,
  'Weaviate': <Search className="h-3 w-3" />,
  'AGE': <Database className="h-3 w-3" />,
  'Qwen3': <Sparkles className="h-3 w-3" />,
  'Emma': <Brain className="h-3 w-3" />
}

// =============================================================================
// Main Component
// =============================================================================

export function ReasoningDisplay({
  workflowSteps,
  sources,
  decisionPath,
  slmPlan,
  executionTimeMs,
  confidence,
  defaultExpanded = false,
  className
}: ReasoningDisplayProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)

  // Check if we have any content to show
  const hasWorkflow = workflowSteps && workflowSteps.length > 0
  const hasSources = sources && sources.length > 0
  const hasDecisionPath = decisionPath && decisionPath.length > 0
  const hasContent = hasWorkflow || hasSources || hasDecisionPath || slmPlan

  // Don't render if no content
  if (!hasContent) {
    return null
  }

  const toggleExpanded = () => setIsExpanded(!isExpanded)

  return (
    <div className={cn("mt-3", className)}>
      {/* Header - Always visible */}
      <button
        onClick={toggleExpanded}
        className={cn(
          "w-full flex items-center justify-between p-3",
          "bg-muted/30 hover:bg-muted/50",
          "rounded-lg border border-border/50",
          "transition-colors duration-200",
          isExpanded && "rounded-b-none border-b-0"
        )}
      >
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">Razonamiento</span>
          {!isExpanded && hasSources && (
            <Badge variant="secondary" className="text-xs">
              {sources.length} {sources.length === 1 ? 'fuente' : 'fuentes'}
            </Badge>
          )}
          {!isExpanded && executionTimeMs && (
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {executionTimeMs < 1000
                ? `${Math.round(executionTimeMs)}ms`
                : `${(executionTimeMs / 1000).toFixed(1)}s`
              }
            </span>
          )}
        </div>
        <ChevronDown className={cn(
          "h-4 w-4 text-muted-foreground transition-transform duration-200",
          isExpanded && "rotate-180"
        )} />
      </button>

      {/* Expandable Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className={cn(
              "p-4 space-y-4",
              "bg-muted/30 rounded-b-lg border border-t-0 border-border/50"
            )}>
              {/* Process Section */}
              {hasWorkflow && (
                <ProcessSection
                  steps={workflowSteps}
                  executionTimeMs={executionTimeMs}
                />
              )}

              {/* Sources/Context Section */}
              {hasSources && (
                <SourcesSection sources={sources} />
              )}

              {/* Decision Path Section */}
              {(hasDecisionPath || slmPlan) && (
                <DecisionPathSection
                  path={decisionPath}
                  slmPlan={slmPlan}
                  confidence={confidence}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// =============================================================================
// Process Section - Timeline of workflow steps
// =============================================================================

interface ProcessSectionProps {
  steps: WorkflowStep[]
  executionTimeMs?: number
}

function ProcessSection({ steps, executionTimeMs }: ProcessSectionProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5 uppercase tracking-wide">
        <ListChecks className="h-3.5 w-3.5" />
        Proceso
        {executionTimeMs && (
          <span className="ml-auto font-normal normal-case">
            Total: {executionTimeMs < 1000
              ? `${Math.round(executionTimeMs)}ms`
              : `${(executionTimeMs / 1000).toFixed(1)}s`
            }
          </span>
        )}
      </h4>

      <div className="relative pl-4 border-l-2 border-border space-y-3">
        {steps.map((step, i) => {
          const config = stepStatusConfig[step.status]

          return (
            <div key={i} className="relative">
              {/* Dot indicator */}
              <div className={cn(
                "absolute -left-[9px] w-4 h-4 rounded-full border-2 flex items-center justify-center",
                config.bgColor
              )}>
                {config.icon && (
                  <span className="text-white">{config.icon}</span>
                )}
              </div>

              {/* Step content */}
              <div className="ml-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={cn("text-sm", config.color)}>
                    {step.description}
                  </span>
                  {step.execution_time_ms && (
                    <span className="text-xs text-muted-foreground">
                      ({(step.execution_time_ms / 1000).toFixed(1)}s)
                    </span>
                  )}
                  {step.findings_count !== undefined && step.findings_count > 0 && (
                    <Badge variant="outline" className="text-xs">
                      {step.findings_count} {step.findings_count === 1 ? 'resultado' : 'resultados'}
                    </Badge>
                  )}
                </div>
                {step.error && (
                  <p className="text-xs text-destructive mt-1">{step.error}</p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// =============================================================================
// Sources Section - Context/documents used
// =============================================================================

interface SourcesSectionProps {
  sources: Citation[]
}

function SourcesSection({ sources }: SourcesSectionProps) {
  const [showAll, setShowAll] = useState(false)
  const displayedSources = showAll ? sources : sources.slice(0, 3)
  const hasMore = sources.length > 3

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5 uppercase tracking-wide">
        <FileText className="h-3.5 w-3.5" />
        Contexto usado ({sources.length} {sources.length === 1 ? 'fuente' : 'fuentes'})
      </h4>

      <div className="space-y-2">
        {displayedSources.map((source, i) => (
          <motion.div
            key={source.id || i}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className={cn(
              "p-2.5 rounded-md",
              "bg-background border border-border/50",
              "text-sm"
            )}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="font-medium truncate flex-1 mr-2">
                {source.title || source.document || 'Documento'}
              </span>
              {source.relevance !== undefined && (
                <Badge
                  variant={source.relevance > 0.8 ? "default" : "secondary"}
                  className="text-xs flex-shrink-0"
                >
                  {Math.round(source.relevance * 100)}%
                </Badge>
              )}
            </div>
            {source.excerpt && (
              <p className="text-xs text-muted-foreground line-clamp-2 italic">
                &quot;{source.excerpt}&quot;
              </p>
            )}
            {source.page && (
              <span className="text-xs text-muted-foreground mt-1 block">
                Página {source.page}
              </span>
            )}
          </motion.div>
        ))}

        {hasMore && (
          <button
            onClick={() => setShowAll(!showAll)}
            className="text-xs text-primary hover:underline"
          >
            {showAll
              ? 'Mostrar menos'
              : `Ver ${sources.length - 3} ${sources.length - 3 === 1 ? 'fuente' : 'fuentes'} más...`
            }
          </button>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// Decision Path Section - Routing breadcrumb
// =============================================================================

interface DecisionPathSectionProps {
  path?: string[]
  slmPlan?: SLMPlanReady
  confidence?: number
}

function DecisionPathSection({ path, slmPlan, confidence }: DecisionPathSectionProps) {
  // Build decision path from SLM plan if not provided
  const effectivePath = path || (slmPlan ? [
    'SLM Router',
    slmPlan.route,
    slmPlan.route === 'HYBRID' ? 'Weaviate + AGE' :
    slmPlan.route === 'GRAPH_ONLY' ? 'AGE' : 'Weaviate',
    'Emma'
  ] : [])

  const effectiveConfidence = confidence ?? slmPlan?.confidence

  if (effectivePath.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1.5 uppercase tracking-wide">
        <Route className="h-3.5 w-3.5" />
        Ruta de decisión
        {effectiveConfidence !== undefined && (
          <span className={cn(
            "ml-auto font-normal normal-case",
            effectiveConfidence >= 0.8 ? "text-green-600 dark:text-green-400" :
            effectiveConfidence >= 0.6 ? "text-yellow-600 dark:text-yellow-400" :
            "text-orange-600 dark:text-orange-400"
          )}>
            Confianza: {Math.round(effectiveConfidence * 100)}%
          </span>
        )}
      </h4>

      <div className="flex items-center gap-1 flex-wrap">
        {effectivePath.map((step, i) => (
          <Fragment key={i}>
            <Badge
              variant="outline"
              className="font-mono text-xs flex items-center gap-1"
            >
              {routeIcons[step] || null}
              {step}
            </Badge>
            {i < effectivePath.length - 1 && (
              <ArrowRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
            )}
          </Fragment>
        ))}
      </div>

      {/* SLM Plan reasoning if available */}
      {slmPlan?.reasoning && (
        <p className="text-xs text-muted-foreground mt-2 italic">
          {slmPlan.reasoning}
        </p>
      )}
    </div>
  )
}

export default ReasoningDisplay
