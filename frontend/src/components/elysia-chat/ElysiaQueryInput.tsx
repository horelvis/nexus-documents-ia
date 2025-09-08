"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2, Paperclip } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { TextareaWithMentions } from "@/components/ui/input-with-mentions"
import { RichTextInput } from "@/components/ui/rich-text-input"
import { cn } from "@/lib/utils"

interface ElysiaQueryInputProps {
  onSendQuery: (query: string) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  className?: string
  placeholder?: string
  addDisplacement?: (value: number) => void
  addDistortion?: (value: number) => void
  documentId?: string // For entity search context
  enableMentions?: boolean
}

export function ElysiaQueryInput({
  onSendQuery,
  isLoading = false,
  disabled = false,
  className,
  placeholder = "Pregúntame sobre tus documentos... (usa @ para mencionar entidades)",
  addDisplacement,
  addDistortion,
  documentId,
  enableMentions = true
}: ElysiaQueryInputProps) {
  const [query, setQuery] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Focus textarea when component mounts
  useEffect(() => {
    if (textareaRef.current && !disabled) {
      textareaRef.current.focus()
    }
  }, [disabled])

  const triggerQuery = async () => {
    if (!query.trim() || isLoading) return
    
    try {
      await onSendQuery(query)
      setQuery("")
      // Reset height after sending
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    } catch (error) {
      console.error("Error sending query:", error)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      triggerQuery()
    }
  }

  // Handle input change for both regular textarea and mentions textarea
  const handleInputChange = (value: string, element?: HTMLTextAreaElement) => {
    setQuery(value)
    
    // Trigger 3D animations when typing
    if (addDisplacement) addDisplacement(0.035)
    if (addDistortion) addDistortion(0.02)
    
    // Auto-resize functionality
    if (element) {
      // Reset height to auto to get proper scrollHeight
      element.style.height = 'auto'
      // Set height based on scrollHeight, with min and max limits
      const newHeight = Math.min(Math.max(element.scrollHeight, 60), 200)
      element.style.height = `${newHeight}px`
    }
  }

  // Legacy handler for regular textarea (when mentions disabled)
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    handleInputChange(e.target.value, e.target)
  }

  // Handler for mentions component
  const handleMentionsChange = (value: string) => {
    handleInputChange(value, textareaRef.current || undefined)
  }

  // Handle entity selection
  const handleEntitySelect = (entity: any) => {
    console.log("Entity selected in chat:", entity)
    // Optional: Add additional logic when entity is selected
  }

  return (
    <div className={cn("space-y-4", className)}>

      {/* Query Input */}
      <div className="relative">
        {enableMentions && documentId ? (
          <RichTextInput
            value={query}
            onChange={setQuery}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || isLoading}
            className="pr-24 min-h-[60px] border-2 focus:border-primary/50"
            documentId={documentId}
            onEntitySelect={handleEntitySelect}
          />
        ) : (
          <Textarea
            ref={textareaRef}
            value={query}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled || isLoading}
            className="pr-24 min-h-[60px] resize-none border-2 focus:border-primary/50"
            rows={1}
          />
        )}
        
        {/* Action Buttons */}
        <div className="absolute right-2 bottom-2 flex gap-1">
          {/* Attachment Button */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            disabled={disabled || isLoading}
            title="Adjuntar archivo"
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          
          {/* Send Button */}
          <Button
            onClick={triggerQuery}
            disabled={!query.trim() || disabled || isLoading}
            size="icon"
            className="h-8 w-8"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Helper Text */}
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {query.length > 0 && `${query.length} caracteres`}
        </span>
        <span>
          Enter para enviar • Shift+Enter para nueva línea
        </span>
      </div>
    </div>
  )
}