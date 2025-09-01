"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Loader2, Settings, Paperclip } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

interface ElysiaQueryInputProps {
  onSendQuery: (query: string, route?: string, mimick?: boolean) => Promise<void>
  isLoading?: boolean
  disabled?: boolean
  className?: string
  placeholder?: string
}

export function ElysiaQueryInput({
  onSendQuery,
  isLoading = false,
  disabled = false,
  className,
  placeholder = "Pregúntame sobre tus documentos..."
}: ElysiaQueryInputProps) {
  const [query, setQuery] = useState("")
  const [route, setRoute] = useState("")
  const [mimick, setMimick] = useState(false)
  const [showRoute, setShowRoute] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
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
      await onSendQuery(query, route || undefined, mimick)
      setQuery("")
      setRoute("")
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

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuery(e.target.value)
    
    // Reset height to auto to get proper scrollHeight
    e.target.style.height = 'auto'
    // Set height based on scrollHeight, with min and max limits
    const newHeight = Math.min(Math.max(e.target.scrollHeight, 60), 200)
    e.target.style.height = `${newHeight}px`
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* Advanced Settings Toggle */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-muted-foreground"
        >
          <Settings className="h-4 w-4 mr-2" />
          Configuración avanzada
        </Button>
      </div>

      {/* Advanced Settings Panel */}
      {showAdvanced && (
        <Card className="p-4 space-y-4 bg-muted/50">
          <div className="space-y-3">
            {/* Route Configuration */}
            <div className="flex items-center gap-2">
              <Switch
                checked={showRoute}
                onCheckedChange={setShowRoute}
                id="route-toggle"
              />
              <label htmlFor="route-toggle" className="text-sm">
                Usar ruta personalizada
              </label>
            </div>

            {showRoute && (
              <div>
                <label className="text-sm text-muted-foreground">
                  Ruta personalizada (desarrollo):
                </label>
                <Textarea
                  value={route}
                  onChange={(e) => setRoute(e.target.value)}
                  placeholder="/api/custom-route"
                  className="mt-1"
                  rows={1}
                />
              </div>
            )}

            {/* Mimick Configuration */}
            <div className="flex items-center gap-2">
              <Switch
                checked={mimick}
                onCheckedChange={setMimick}
                id="mimick-toggle"
              />
              <label htmlFor="mimick-toggle" className="text-sm">
                Modo imitación (debugging)
              </label>
            </div>
          </div>
        </Card>
      )}

      {/* Query Input */}
      <div className="relative">
        <Textarea
          ref={textareaRef}
          value={query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          className="pr-24 min-h-[60px] resize-none border-2 focus:border-primary/50"
          rows={1}
        />
        
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