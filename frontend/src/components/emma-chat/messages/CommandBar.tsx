'use client'

import { Button } from '@/components/ui/button'
import { RotateCcw, Copy, Check } from 'lucide-react'
import { useState } from 'react'

interface CommandBarProps {
  content: string
  isLoading?: boolean
  onRegenerate?: () => void
}

export function CommandBar({ content, isLoading, onRegenerate }: CommandBarProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
      {onRegenerate && (
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          disabled={isLoading}
          onClick={onRegenerate}
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
      )}
      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCopy}>
        {copied ? (
          <Check className="h-3.5 w-3.5 text-green-500" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </Button>
    </div>
  )
}
