"use client"

import { motion } from "framer-motion"
import { Loader2, Brain, FileSearch, Shield, FileText } from "lucide-react"
import { cn } from "@/lib/utils"

interface ProgressDisplayProps {
  message: string
  progress: number
  step?: number
  totalSteps?: number
  agent?: string
  className?: string
}

// Map agent names to icons
const agentIcons: Record<string, React.ReactNode> = {
  ContractAgent: <FileSearch className="h-4 w-4" />,
  ComplianceAgent: <Shield className="h-4 w-4" />,
  SummarizerAgent: <FileText className="h-4 w-4" />,
  SearchAgent: <FileSearch className="h-4 w-4" />,
  AnalystAgent: <Brain className="h-4 w-4" />,
}

export function ProgressDisplay({
  message,
  progress,
  step,
  totalSteps,
  agent,
  className
}: ProgressDisplayProps) {
  const AgentIcon = agent ? agentIcons[agent] || <Brain className="h-4 w-4" /> : <Loader2 className="h-4 w-4 animate-spin" />

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30",
        "border border-blue-200 dark:border-blue-800 rounded-lg p-4",
        className
      )}
    >
      {/* Header with agent info */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-400">
          {AgentIcon}
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
              {agent || "Procesando"}
            </span>
            {step && totalSteps && (
              <span className="text-xs text-blue-600 dark:text-blue-400">
                Paso {step}/{totalSteps}
              </span>
            )}
          </div>
          <p className="text-sm text-blue-700 dark:text-blue-300 mt-0.5">
            {message}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="relative h-2 bg-blue-100 dark:bg-blue-900 rounded-full overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        />
        {/* Animated shimmer effect */}
        <motion.div
          className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/30 to-transparent"
          animate={{ x: ["-100%", "400%"] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
        />
      </div>

      {/* Progress percentage */}
      <div className="flex justify-end mt-1">
        <span className="text-xs text-blue-600 dark:text-blue-400">
          {progress}%
        </span>
      </div>
    </motion.div>
  )
}
