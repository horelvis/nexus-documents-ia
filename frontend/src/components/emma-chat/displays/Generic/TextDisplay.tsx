"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"

interface TextDisplayProps {
  content: string
  variant?: "primary" | "secondary"
  className?: string
}

export function TextDisplay({ content, variant = "primary", className }: TextDisplayProps) {
  // Clean and format the content
  const formatContent = (text: string) => {
    return text
      .replace(/\\n/g, '\n') // Convert literal \n to actual newlines
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // Convert **bold** to <strong>
      .replace(/\*(.*?)\*/g, '<em>$1</em>') // Convert *italic* to <em>
      .replace(/(\d+\.\s+\*\*.*?\*\*:)/g, '<div class="mt-4 mb-2">$1</div>') // Format numbered lists with bold headers
  }

  return (
    <motion.div
      className={cn(
        "w-full flex flex-col items-start justify-start",
        className
      )}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", damping: 20, stiffness: 300 }}
    >
      <div className={cn(
        "prose prose-sm max-w-none",
        variant === "primary" ? "text-foreground" : "text-muted-foreground",
        "prose-headings:text-foreground prose-strong:text-foreground",
        "prose-code:text-foreground prose-code:bg-muted prose-code:px-1 prose-code:rounded"
      )}>
        <div 
          className="whitespace-pre-wrap"
          dangerouslySetInnerHTML={{ __html: formatContent(content) }}
        />
      </div>
    </motion.div>
  )
}