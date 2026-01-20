"use client"

import { motion, AnimatePresence } from "framer-motion"
import {
  Check,
  Loader2,
  AlertCircle,
  Clock,
  Brain,
  FileSearch,
  Shield,
  FileText,
  Scale,
  Building2,
  Landmark,
  Home,
  Lock,
  GraduationCap,
  Search,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Lightbulb,
  MessageSquare,
  Wand2
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useState } from "react"
import { ThinkingIndicator } from "./ThinkingIndicator"

export interface WorkflowStep {
  index: number
  description: string
  agent: string
  status: 'pending' | 'in_progress' | 'completed' | 'error'
  findings_count?: number
  execution_time_ms?: number
  error?: string
}

interface WorkflowProgressProps {
  message: string
  progress: number
  currentStep?: number
  totalSteps?: number
  currentAgent?: string
  steps?: WorkflowStep[]
  planId?: string
  className?: string
}

// Map agent names to icons and colors
const agentConfig: Record<string, { icon: React.ReactNode; color: string; bgColor: string; label: string }> = {
  // ===== ReAct Agent workflow steps (new) =====
  reasoning: {
    icon: <Lightbulb className="h-4 w-4" />,
    color: "text-yellow-500 dark:text-yellow-400",
    bgColor: "bg-yellow-100 dark:bg-yellow-900/40",
    label: "Razonando"
  },
  search: {
    icon: <Search className="h-4 w-4" />,
    color: "text-cyan-500 dark:text-cyan-400",
    bgColor: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Buscando"
  },
  analysis: {
    icon: <Brain className="h-4 w-4" />,
    color: "text-orange-500 dark:text-orange-400",
    bgColor: "bg-orange-100 dark:bg-orange-900/40",
    label: "Analizando"
  },
  synthesis: {
    icon: <Wand2 className="h-4 w-4" />,
    color: "text-violet-500 dark:text-violet-400",
    bgColor: "bg-violet-100 dark:bg-violet-900/40",
    label: "Generando"
  },
  // ===== PlanningFlow Agent types =====
  ContractAgent: {
    icon: <Scale className="h-4 w-4" />,
    color: "text-purple-500 dark:text-purple-400",
    bgColor: "bg-purple-100 dark:bg-purple-900/40",
    label: "Contratos"
  },
  ComplianceAgent: {
    icon: <Shield className="h-4 w-4" />,
    color: "text-green-500 dark:text-green-400",
    bgColor: "bg-green-100 dark:bg-green-900/40",
    label: "Cumplimiento"
  },
  SummarizerAgent: {
    icon: <FileText className="h-4 w-4" />,
    color: "text-blue-500 dark:text-blue-400",
    bgColor: "bg-blue-100 dark:bg-blue-900/40",
    label: "Resumen"
  },
  SearchAgent: {
    icon: <Search className="h-4 w-4" />,
    color: "text-cyan-500 dark:text-cyan-400",
    bgColor: "bg-cyan-100 dark:bg-cyan-900/40",
    label: "Búsqueda"
  },
  AnalystAgent: {
    icon: <Brain className="h-4 w-4" />,
    color: "text-orange-500 dark:text-orange-400",
    bgColor: "bg-orange-100 dark:bg-orange-900/40",
    label: "Análisis"
  },
  LaborAgent: {
    icon: <Building2 className="h-4 w-4" />,
    color: "text-amber-500 dark:text-amber-400",
    bgColor: "bg-amber-100 dark:bg-amber-900/40",
    label: "Laboral"
  },
  FiscalAgent: {
    icon: <Landmark className="h-4 w-4" />,
    color: "text-emerald-500 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40",
    label: "Fiscal"
  },
  RealEstateAgent: {
    icon: <Home className="h-4 w-4" />,
    color: "text-rose-500 dark:text-rose-400",
    bgColor: "bg-rose-100 dark:bg-rose-900/40",
    label: "Inmobiliario"
  },
  PrivacyAgent: {
    icon: <Lock className="h-4 w-4" />,
    color: "text-indigo-500 dark:text-indigo-400",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/40",
    label: "Privacidad"
  },
  EducationAgent: {
    icon: <GraduationCap className="h-4 w-4" />,
    color: "text-teal-500 dark:text-teal-400",
    bgColor: "bg-teal-100 dark:bg-teal-900/40",
    label: "Educación"
  },
  // Tool-related configs
  clarification: {
    icon: <MessageSquare className="h-4 w-4" />,
    color: "text-purple-500 dark:text-purple-400",
    bgColor: "bg-purple-100 dark:bg-purple-900/40",
    label: "Clarificación"
  },
}

// Exported for reuse in DelegationBadge and other components
export function getAgentConfig(agentName: string) {
  // Handle tool names (snake_case) by mapping to agent config
  const toolToAgentMap: Record<string, string> = {
    'nexus_semantic_search': 'search',
    'nexus_hybrid_search': 'search',
    'nexus_search': 'search',
    'analyze_document': 'analysis',
    'ask_user_clarification': 'clarification',
    'share_insights': 'synthesis',
    'plan_tasks': 'reasoning',
  }

  const mappedName = toolToAgentMap[agentName] || agentName

  return agentConfig[mappedName] || {
    icon: <Brain className="h-4 w-4" />,
    color: "text-gray-500 dark:text-gray-400",
    bgColor: "bg-gray-100 dark:bg-gray-800",
    label: agentName?.replace('Agent', '').replace(/_/g, ' ') || "Agente"
  }
}

function StepIcon({ status, agent }: { status: WorkflowStep['status']; agent: string }) {
  const config = getAgentConfig(agent)

  if (status === 'completed') {
    return (
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        className="flex items-center justify-center w-8 h-8 rounded-full bg-green-500 text-white"
      >
        <Check className="h-4 w-4" />
      </motion.div>
    )
  }

  if (status === 'in_progress') {
    return (
      <motion.div
        animate={{
          boxShadow: [
            "0 0 0 0 rgba(59, 130, 246, 0)",
            "0 0 0 8px rgba(59, 130, 246, 0.2)",
            "0 0 0 0 rgba(59, 130, 246, 0)"
          ]
        }}
        transition={{ duration: 1.5, repeat: Infinity }}
        className={cn(
          "flex items-center justify-center w-8 h-8 rounded-full",
          config.bgColor, config.color
        )}
      >
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
        >
          {config.icon}
        </motion.div>
      </motion.div>
    )
  }

  if (status === 'error') {
    return (
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-destructive/10 text-destructive">
        <AlertCircle className="h-4 w-4" />
      </div>
    )
  }

  // Pending
  return (
    <div className="flex items-center justify-center w-8 h-8 rounded-full border-2 border-dashed border-border text-muted-foreground">
      <Clock className="h-3.5 w-3.5" />
    </div>
  )
}

// Simple loading indicator before plan is created - now uses ThinkingIndicator
function InitialLoading() {
  return <ThinkingIndicator />
}

export function WorkflowProgress({
  message,
  progress,
  currentStep,
  totalSteps,
  currentAgent,
  steps = [],
  planId,
  className
}: WorkflowProgressProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasSteps = steps.length > 0

  // Show thinking indicator until plan is created (has steps)
  if (!hasSteps) {
    return <InitialLoading />
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "rounded-xl border overflow-hidden",
        "bg-card",
        "border-border",
        "shadow-sm",
        className
      )}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <motion.div
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
              className="flex items-center justify-center w-9 h-9 rounded-lg bg-primary text-primary-foreground"
            >
              <Sparkles className="h-5 w-5" />
            </motion.div>
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                Emma procesando
              </h4>
              <p className="text-xs text-muted-foreground">
                {currentStep && totalSteps
                  ? `Paso ${currentStep} de ${totalSteps}`
                  : "Iniciando análisis..."}
              </p>
            </div>
          </div>

          {hasSteps && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-1.5 rounded-md hover:bg-muted transition-colors"
            >
              {isExpanded
                ? <ChevronUp className="h-4 w-4 text-muted-foreground" />
                : <ChevronDown className="h-4 w-4 text-muted-foreground" />
              }
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="mt-3 relative h-1.5 bg-muted rounded-full overflow-hidden">
          <motion.div
            className="absolute inset-y-0 left-0 bg-primary rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>

        {/* Current action message */}
        <motion.p
          key={message}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="mt-2 text-sm text-muted-foreground flex items-center gap-2"
        >
          <Loader2 className="h-3 w-3 animate-spin text-primary" />
          {message}
        </motion.p>
      </div>

      {/* Steps Timeline */}
      <AnimatePresence>
        {isExpanded && hasSteps && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="p-4 space-y-1">
              {steps.map((step, idx) => {
                const config = getAgentConfig(step.agent)
                const isLast = idx === steps.length - 1

                return (
                  <motion.div
                    key={step.index}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1 }}
                    className="flex gap-3"
                  >
                    {/* Timeline connector */}
                    <div className="flex flex-col items-center">
                      <StepIcon status={step.status} agent={step.agent} />
                      {!isLast && (
                        <div className={cn(
                          "w-0.5 flex-1 my-1 min-h-[20px]",
                          step.status === 'completed'
                            ? "bg-green-500"
                            : "bg-border"
                        )} />
                      )}
                    </div>

                    {/* Step content */}
                    <div className={cn(
                      "flex-1 pb-3 min-w-0",
                      step.status === 'in_progress' && "animate-pulse"
                    )}>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={cn(
                          "text-xs font-medium px-2 py-0.5 rounded-full",
                          config.bgColor, config.color
                        )}>
                          {config.label}
                        </span>
                        {step.status === 'completed' && step.findings_count !== undefined && (
                          <span className="text-xs text-green-600">
                            {step.findings_count} hallazgos
                          </span>
                        )}
                        {step.status === 'completed' && step.execution_time_ms && (
                          <span className="text-xs text-muted-foreground">
                            {(step.execution_time_ms / 1000).toFixed(1)}s
                          </span>
                        )}
                      </div>
                      <p className={cn(
                        "text-sm mt-1 leading-relaxed",
                        step.status === 'pending'
                          ? "text-muted-foreground"
                          : "text-foreground"
                      )}>
                        {step.description}
                      </p>
                      {step.status === 'error' && step.error && (
                        <p className="text-xs text-destructive mt-1">
                          {step.error}
                        </p>
                      )}
                    </div>
                  </motion.div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Footer with percentage */}
      <div className="px-4 py-2 bg-muted/50 border-t border-border">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            {planId && `Plan: ${planId.slice(0, 8)}...`}
          </span>
          <span className="font-medium text-primary">
            {progress}% completado
          </span>
        </div>
      </div>
    </motion.div>
  )
}
