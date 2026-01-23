"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import { getAgentConfig } from "./WorkflowProgress"

export interface DelegationBadgeProps {
  agent: string      // nexus_semantic_search, analyze_document, etc.
  message: string    // "Buscando documentos..."
  elapsedMs?: number
  isActive?: boolean // Currently running
  className?: string
}

export function DelegationBadge({
  agent,
  message,
  elapsedMs,
  isActive = false,
  className
}: DelegationBadgeProps) {
  const config = getAgentConfig(agent)

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-lg",
        "border transition-all duration-200",
        isActive
          ? cn(config.bgColor, "border-transparent")
          : "bg-muted/40 border-border/50",
        className
      )}
    >
      {/* Icon with animation when active */}
      <div className={cn(
        "flex-shrink-0",
        config.color,
        isActive && "animate-pulse"
      )}>
        {isActive ? (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
          >
            {config.icon}
          </motion.div>
        ) : (
          config.icon
        )}
      </div>

      {/* Message */}
      <span className={cn(
        "text-sm flex-1 min-w-0 truncate",
        isActive ? "text-foreground" : "text-muted-foreground"
      )}>
        {message}
      </span>

      {/* Elapsed time */}
      {elapsedMs !== undefined && (
        <span className="text-xs text-muted-foreground tabular-nums flex-shrink-0">
          {(elapsedMs / 1000).toFixed(1)}s
        </span>
      )}

      {/* Active indicator */}
      {isActive && (
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0"
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.7, 1, 0.7]
          }}
          transition={{
            duration: 1,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
      )}
    </motion.div>
  )
}
