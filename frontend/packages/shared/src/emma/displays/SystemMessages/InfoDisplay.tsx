"use client"

import { motion } from "framer-motion"
import { Info, CheckCircle, AlertCircle, XCircle } from "lucide-react"
import { cn } from "@/lib/utils"

interface InfoDisplayProps {
  content: string
  type?: "info" | "success" | "warning" | "error"
  className?: string
}

export function InfoDisplay({ content, type = "info", className }: InfoDisplayProps) {
  const configs = {
    info: {
      icon: Info,
      bgColor: "bg-blue-50 dark:bg-blue-950/20",
      borderColor: "border-blue-200 dark:border-blue-800",
      textColor: "text-blue-800 dark:text-blue-200",
      iconColor: "text-blue-600 dark:text-blue-400"
    },
    success: {
      icon: CheckCircle,
      bgColor: "bg-green-50 dark:bg-green-950/20",
      borderColor: "border-green-200 dark:border-green-800",
      textColor: "text-green-800 dark:text-green-200",
      iconColor: "text-green-600 dark:text-green-400"
    },
    warning: {
      icon: AlertCircle,
      bgColor: "bg-yellow-50 dark:bg-yellow-950/20",
      borderColor: "border-yellow-200 dark:border-yellow-800",
      textColor: "text-yellow-800 dark:text-yellow-200",
      iconColor: "text-yellow-600 dark:text-yellow-400"
    },
    error: {
      icon: XCircle,
      bgColor: "bg-red-50 dark:bg-red-950/20",
      borderColor: "border-red-200 dark:border-red-800",
      textColor: "text-red-800 dark:text-red-200",
      iconColor: "text-red-600 dark:text-red-400"
    }
  }

  const config = configs[type]
  const Icon = config.icon

  return (
    <motion.div
      className={cn(
        "w-full p-3 rounded-lg border flex items-start gap-3",
        config.bgColor,
        config.borderColor,
        className
      )}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", damping: 20, stiffness: 300 }}
    >
      <Icon className={cn("h-4 w-4 mt-0.5 flex-shrink-0", config.iconColor)} />
      <p className={cn("text-sm", config.textColor)}>
        {content}
      </p>
    </motion.div>
  )
}