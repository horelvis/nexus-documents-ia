'use client'

import { useState, useRef, useEffect } from 'react'
import { IconSend, IconLoader2 } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface EmmaQueryInputProps {
  onSendQuery: (query: string) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  placeholder?: string
  className?: string
}

export function EmmaQueryInput({
  onSendQuery,
  isLoading = false,
  disabled = false,
  placeholder = 'Pregúntame sobre tus documentos...',
  className,
}: EmmaQueryInputProps) {
  const [query, setQuery] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Focus textarea on mount
  useEffect(() => {
    if (textareaRef.current && !disabled) {
      textareaRef.current.focus()
    }
  }, [disabled])

  const handleSubmit = async () => {
    if (!query.trim() || isLoading || disabled) return

    const queryToSend = query.trim()
    setQuery('')

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    await onSendQuery(queryToSend)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuery(e.target.value)

    // Auto-resize
    const textarea = e.target
    textarea.style.height = 'auto'
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 52), 200)
    textarea.style.height = `${newHeight}px`
  }

  return (
    <div className={cn('space-y-3', className)}>
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="pr-14 min-h-[52px] max-h-[200px] resize-none rounded-xl border-2 border-input bg-background transition-colors focus:border-primary/50"
          rows={1}
        />
        <Button
          onClick={handleSubmit}
          disabled={!query.trim() || disabled || isLoading}
          size="icon"
          className="absolute right-2 bottom-2 h-9 w-9 rounded-lg"
        >
          {isLoading ? (
            <IconLoader2 className="h-4 w-4 animate-spin" />
          ) : (
            <IconSend className="h-4 w-4" />
          )}
        </Button>
      </div>

      <div className="flex justify-between text-xs text-muted-foreground px-1">
        <span>{query.length > 0 && `${query.length} caracteres`}</span>
        <span>Enter para enviar • Shift+Enter para nueva línea</span>
      </div>
    </div>
  )
}
