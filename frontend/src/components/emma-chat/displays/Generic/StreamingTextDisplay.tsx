"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import { EmmaMarkdownFormat } from "../../EmmaMarkdownFormat"

export interface StreamingTextDisplayProps {
  text: string
  isStreaming: boolean
  showCursor?: boolean
  className?: string
}

export function StreamingTextDisplay({
  text,
  isStreaming,
  showCursor = true,
  className
}: StreamingTextDisplayProps) {
  // Don't render if no text
  if (!text) return null

  return (
    <div className={cn("relative", className)}>
      {/* Markdown rendered text */}
      <EmmaMarkdownFormat content={text} />

      {/* Blinking cursor when streaming */}
      {isStreaming && showCursor && (
        <motion.span
          className="inline-block w-2 h-5 bg-primary ml-0.5 align-middle rounded-sm"
          animate={{
            opacity: [1, 0, 1]
          }}
          transition={{
            duration: 0.8,
            repeat: Infinity,
            ease: "linear"
          }}
          aria-hidden="true"
        />
      )}
    </div>
  )
}
