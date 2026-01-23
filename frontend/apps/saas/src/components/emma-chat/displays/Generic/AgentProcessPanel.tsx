"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
  Brain,
  Cpu,
  Scale,
  Search,
  FileText,
  Zap,
  Clock,
  ChevronRight,
  ChevronDown,
  Sparkles,
  Database,
  Network,
  Gavel,
  TrendingDown,
  Check,
  Loader2,
  AlertCircle,
  BookOpen,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger
} from "@/components/ui/tooltip"
import type { AgentProcessInfo, ReasoningType, LegalContext } from "../../types"

interface AgentProcessPanelProps {
  processInfo: AgentProcessInfo
  isActive?: boolean
  className?: string
}

// Reasoning type configuration
const reasoningConfig: Record<ReasoningType, {
  icon: React.ReactNode
  label: string
  description: string
  color: string
  bgColor: string
}> = {
  STRUCTURAL: {
    icon: <Database className="h-4 w-4" />,
    label: "SIL Estructural",
    description: "Respuesta directa desde el grafo de conocimiento",
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40"
  },
  STRUCTURAL_COUNT: {
    icon: <Database className="h-4 w-4" />,
    label: "SIL Conteo",
    description: "Conteo directo via Cypher",
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40"
  },
  STRUCTURAL_EXISTS: {
    icon: <Database className="h-4 w-4" />,
    label: "SIL Existencia",
    description: "Verificacion de existencia via grafo",
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40"
  },
  STRUCTURAL_LOCATION: {
    icon: <Database className="h-4 w-4" />,
    label: "SIL Ubicacion",
    description: "Localizacion de documentos via grafo",
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-100 dark:bg-emerald-900/40"
  },
  TEMPORAL: {
    icon: <Clock className="h-4 w-4" />,
    label: "SIL Temporal",
    description: "Consulta basada en tiempo y evolucion",
    color: "text-blue-600 dark:text-blue-400",
    bgColor: "bg-blue-100 dark:bg-blue-900/40"
  },
  MULTIHOP: {
    icon: <Network className="h-4 w-4" />,
    label: "SIL Multi-hop",
    description: "Navegacion de relaciones en el grafo",
    color: "text-purple-600 dark:text-purple-400",
    bgColor: "bg-purple-100 dark:bg-purple-900/40"
  },
  LEGAL: {
    icon: <Gavel className="h-4 w-4" />,
    label: "Legal Graph",
    description: "Conocimiento legal desde el grafo juridico",
    color: "text-amber-600 dark:text-amber-400",
    bgColor: "bg-amber-100 dark:bg-amber-900/40"
  },
  LEGAL_ENRICHED: {
    icon: <Scale className="h-4 w-4" />,
    label: "RAG + Legal",
    description: "RAG enriquecido con contexto legal",
    color: "text-orange-600 dark:text-orange-400",
    bgColor: "bg-orange-100 dark:bg-orange-900/40"
  },
  SEMANTIC: {
    icon: <Brain className="h-4 w-4" />,
    label: "RAG Semantico",
    description: "Busqueda semantica tradicional",
    color: "text-cyan-600 dark:text-cyan-400",
    bgColor: "bg-cyan-100 dark:bg-cyan-900/40"
  },
  FOCUSED_RAG: {
    icon: <FileText className="h-4 w-4" />,
    label: "RAG Enfocado",
    description: "RAG sobre documentos especificos",
    color: "text-indigo-600 dark:text-indigo-400",
    bgColor: "bg-indigo-100 dark:bg-indigo-900/40"
  },
  FULL_RAG: {
    icon: <Search className="h-4 w-4" />,
    label: "RAG Completo",
    description: "Busqueda en todo el corpus",
    color: "text-gray-600 dark:text-gray-400",
    bgColor: "bg-gray-100 dark:bg-gray-800"
  }
}

// Tool status icons
function ToolStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'running':
      return <Loader2 className="h-3 w-3 animate-spin text-primary" />
    case 'completed':
      return <Check className="h-3 w-3 text-green-500" />
    case 'error':
      return <AlertCircle className="h-3 w-3 text-destructive" />
    default:
      return <Clock className="h-3 w-3 text-muted-foreground" />
  }
}

// Legal Context Section
function LegalContextSection({ legalContext }: { legalContext: LegalContext }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="border-t border-border pt-3 mt-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between w-full text-left"
      >
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-amber-500" />
          <span className="text-sm font-medium">Contexto Legal</span>
          <Badge variant="secondary" className="text-xs">
            {legalContext.applicable_laws.length} leyes
          </Badge>
        </div>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-2">
              {/* Domain badge */}
              {legalContext.legal_domain && (
                <Badge variant="outline" className="text-xs">
                  Dominio: {legalContext.legal_domain}
                </Badge>
              )}

              {/* Applicable laws */}
              <div className="space-y-1">
                {legalContext.applicable_laws.map((law, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between text-xs p-2 rounded bg-muted/50"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Gavel className="h-3 w-3 text-amber-500 flex-shrink-0" />
                      <span className="truncate">{law.name}</span>
                    </div>
                    {law.boe_id && (
                      <Badge variant="secondary" className="text-[10px] ml-2 flex-shrink-0">
                        {law.boe_id}
                      </Badge>
                    )}
                  </div>
                ))}
              </div>

              {/* Compliance hints */}
              {legalContext.compliance_hints && legalContext.compliance_hints.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground mb-1">Aspectos a verificar:</p>
                  <ul className="text-xs space-y-1">
                    {legalContext.compliance_hints.map((hint, idx) => (
                      <li key={idx} className="flex items-start gap-1">
                        <span className="text-primary">-</span>
                        <span>{hint}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function AgentProcessPanel({
  processInfo,
  isActive = false,
  className
}: AgentProcessPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  const reasoningType = processInfo.reasoning_type || 'SEMANTIC'
  const config = reasoningConfig[reasoningType] || reasoningConfig.SEMANTIC

  // Calculate efficiency
  const tokensSaved = processInfo.tokens_saved || 0
  const tokensUsed = processInfo.tokens_used || 0
  const efficiency = tokensSaved > 0
    ? Math.round((tokensSaved / (tokensSaved + tokensUsed)) * 100)
    : 0

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className={cn(
        "rounded-lg border overflow-hidden",
        "bg-card/95 backdrop-blur-sm",
        isActive && "ring-2 ring-primary/20",
        className
      )}
    >
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={cn(
            "flex items-center justify-center w-8 h-8 rounded-lg",
            config.bgColor
          )}>
            {isActive ? (
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                className={config.color}
              >
                {config.icon}
              </motion.div>
            ) : (
              <span className={config.color}>{config.icon}</span>
            )}
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{config.label}</span>
              {processInfo.sil_used && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <Badge
                        variant="secondary"
                        className="text-[10px] px-1.5 py-0 h-4 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400"
                      >
                        <Zap className="h-2.5 w-2.5 mr-0.5" />
                        SIL
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="text-xs">Pre-LLM Reasoning activo</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{config.description}</p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {/* Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3">
              {/* Efficiency metrics */}
              {(tokensSaved > 0 || processInfo.execution_time_ms) && (
                <div className="flex items-center gap-4 text-xs">
                  {tokensSaved > 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                          <TrendingDown className="h-3 w-3" />
                          <span>{tokensSaved.toLocaleString()} tokens ahorrados</span>
                          <Badge variant="secondary" className="text-[10px] ml-1">
                            {efficiency}%
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>SIL evito {tokensSaved} tokens de procesamiento LLM</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                  {processInfo.execution_time_ms && (
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {(processInfo.execution_time_ms / 1000).toFixed(2)}s
                    </span>
                  )}
                </div>
              )}

              {/* Active tools */}
              {processInfo.active_tools.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    Tools activos
                  </p>
                  <div className="space-y-1">
                    {processInfo.active_tools.map((tool, idx) => (
                      <motion.div
                        key={idx}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: idx * 0.05 }}
                        className={cn(
                          "flex items-center justify-between px-2 py-1.5 rounded text-xs",
                          tool.status === 'running' && "bg-primary/10",
                          tool.status === 'completed' && "bg-muted/50",
                          tool.status === 'error' && "bg-destructive/10"
                        )}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <ToolStatusIcon status={tool.status} />
                          <span className="font-mono truncate">{tool.name}</span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {tool.message && (
                            <span className="text-muted-foreground truncate max-w-[120px]">
                              {tool.message}
                            </span>
                          )}
                          {tool.elapsed_ms && (
                            <span className="text-muted-foreground tabular-nums">
                              {(tool.elapsed_ms / 1000).toFixed(1)}s
                            </span>
                          )}
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}

              {/* Legal context */}
              {processInfo.legal_context && (
                <LegalContextSection legalContext={processInfo.legal_context} />
              )}

              {/* Reasoning message */}
              {processInfo.reasoning_message && (
                <div className="text-xs text-muted-foreground italic border-l-2 border-primary/30 pl-2">
                  {processInfo.reasoning_message}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

// Export helper function
export { reasoningConfig }
export function getReasoningConfig(type: ReasoningType) {
  return reasoningConfig[type] || reasoningConfig.SEMANTIC
}
