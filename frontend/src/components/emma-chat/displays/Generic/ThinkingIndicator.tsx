"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import {
  Sparkles,
  FileText,
  Brain,
  Database,
  Lightbulb,
  Search,
  Wand2
} from "lucide-react"
import type { ProgressStage } from "../../types"

// Stage configuration with icons and labels
const stageConfig: Record<ProgressStage, {
  icon: React.ReactNode
  label: string
  color: string
}> = {
  init: {
    icon: <Sparkles className="h-4 w-4" />,
    label: "Iniciando...",
    color: "text-primary"
  },
  loading_document: {
    icon: <FileText className="h-4 w-4" />,
    label: "Cargando documento...",
    color: "text-blue-500"
  },
  analyzing: {
    icon: <Brain className="h-4 w-4" />,
    label: "Analizando...",
    color: "text-orange-500"
  },
  context_preparation: {
    icon: <Database className="h-4 w-4" />,
    label: "Preparando contexto...",
    color: "text-emerald-500"
  },
  thinking: {
    icon: <Lightbulb className="h-4 w-4" />,
    label: "Pensando...",
    color: "text-yellow-500"
  },
  searching: {
    icon: <Search className="h-4 w-4" />,
    label: "Buscando...",
    color: "text-cyan-500"
  },
  generating: {
    icon: <Wand2 className="h-4 w-4" />,
    label: "Generando respuesta...",
    color: "text-violet-500"
  }
}

interface ThinkingIndicatorProps {
  className?: string
  stage?: ProgressStage
  message?: string
}

export function ThinkingIndicator({
  className,
  stage,
  message
}: ThinkingIndicatorProps) {
  // Get stage config or default
  const config = stage ? stageConfig[stage] : null
  const displayMessage = message || config?.label

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-3 py-1.5 bg-muted/60",
        className
      )}
      aria-label={displayMessage || "Emma está procesando"}
    >
      {/* Icon with rotation when showing stage */}
      {config ? (
        <motion.div
          className={cn("flex-shrink-0", config.color)}
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
        >
          {config.icon}
        </motion.div>
      ) : (
        /* Default animated dots */
        <div className="flex space-x-1">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-primary"
              animate={{
                y: [0, -4, 0],
                opacity: [0.4, 1, 0.4],
              }}
              transition={{
                duration: 0.8,
                repeat: Infinity,
                delay: i * 0.15,
                ease: "easeInOut",
              }}
            />
          ))}
        </div>
      )}

      {/* Stage message if available */}
      {displayMessage && (
        <motion.span
          key={displayMessage}
          initial={{ opacity: 0, x: -5 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-sm text-muted-foreground"
        >
          {displayMessage}
        </motion.span>
      )}
    </div>
  )
}
