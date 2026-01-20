"use client"

import { useState, useRef, forwardRef } from "react"
import { cn } from "@/lib/utils"
import { findEntityAtPosition } from "./entity-renderer"
import { EntitySearchMenu } from "@/components/documents/entity-search-menu"
import { createEntityTag } from "./entity-renderer"
import { getCharacterCoordinates } from "@/lib/caret-utils"

interface Entity {
  id: string
  name: string
  email: string
  type: string
  role?: string
}

interface RichTextInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  disabled?: boolean
  documentId?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string
  autoInsertEntityTag?: boolean
  onKeyDown?: (e: React.KeyboardEvent) => void
}

export const RichTextInput = forwardRef<HTMLDivElement, RichTextInputProps>(
  ({ 
    value, 
    onChange, 
    placeholder = "Type @ to mention entities...", 
    className, 
    disabled = false,
    documentId,
    onEntitySelect,
    mentionTrigger = '@',
    autoInsertEntityTag = true,
    onKeyDown,
    ...props 
  }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const [cursorPosition, setCursorPosition] = useState<{ top: number; left: number } | null>(null)
    const inputRef = useRef<HTMLInputElement>(null)


    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value
      const cursorPos = e.target.selectionStart || 0

      onChange(newValue)

      // Check for mention trigger
      const triggerIndex = newValue.lastIndexOf(mentionTrigger, cursorPos - 1)

      // Only process if @ is found and cursor is after it
      if (triggerIndex !== -1 && cursorPos > triggerIndex) {
        // Check if this is a valid mention (not inside a word)
        const beforeTrigger = triggerIndex === 0 ? '' : newValue[triggerIndex - 1]
        const isValidMention = triggerIndex === 0 || /\s/.test(beforeTrigger)

        if (isValidMention) {
          const query = newValue.substring(triggerIndex + 1, cursorPos)

          // Open dropdown immediately when @ is typed (allow empty query)
          // Close only if query contains spaces or newlines
          if (!query.includes(' ') && !query.includes('\n')) {
            setEntitySearchQuery(query)
            setMentionStart(triggerIndex)

            // Calculate cursor position for dropdown placement
            const coords = getCharacterCoordinates(e.target, triggerIndex)
            setCursorPosition(coords)

            setEntitySearchOpen(true)
            return
          }
        }
      }

      // Close search if no valid mention found
      if (entitySearchOpen) {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        setCursorPosition(null)
      }
    }

    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (entitySearchOpen && e.key === 'Escape') {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        setCursorPosition(null)
        e.preventDefault()
        return
      }

      // Handle backspace to delete entire entity tag
      if (e.key === 'Backspace' && !entitySearchOpen) {
        const cursorPosition = e.currentTarget.selectionStart || 0
        
        // Check if cursor is at the end of an entity tag
        const entityAtPosition = findEntityAtPosition(value, cursorPosition)
        
        if (entityAtPosition && cursorPosition === entityAtPosition.end) {
          e.preventDefault()
          
          // Remove the entire entity tag
          const newValue = value.substring(0, entityAtPosition.start) + value.substring(entityAtPosition.end)
          onChange(newValue)
          
          // Set cursor position after the removal
          setTimeout(() => {
            if (inputRef.current) {
              inputRef.current.setSelectionRange(entityAtPosition.start, entityAtPosition.start)
            }
          }, 0)
          
          return
        }
      }
      
      if (onKeyDown) {
        onKeyDown(e)
      }
    }


    const handleEntitySelectInternal = (entity: Entity) => {
      if (mentionStart === -1) return

      const beforeMention = value.substring(0, mentionStart)
      const afterMention = value.substring(mentionStart + entitySearchQuery.length + 1)

      const newValue = autoInsertEntityTag
        ? beforeMention + createEntityTag({ type: entity.type, id: entity.id, name: entity.name }) + afterMention
        : beforeMention + afterMention

      onChange(newValue)
      setEntitySearchOpen(false)
      setEntitySearchQuery('')
      setMentionStart(-1)
      setCursorPosition(null)

      if (onEntitySelect) {
        onEntitySelect(entity)
      }
    }

    return (
      <div className="relative space-y-2">
        {/* Always show the input for now */}
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleInputKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className={cn(
            "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
            className
          )}
        />
        
        {/* Entity Search Menu */}
        {entitySearchOpen && documentId && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelectInternal}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              setCursorPosition(null)
            }}
            searchQuery={entitySearchQuery}
            anchorRef={inputRef.current}
            documentId={documentId}
            cursorPosition={cursorPosition}
          />
        )}
        
      </div>
    )
  }
)

RichTextInput.displayName = "RichTextInput"
