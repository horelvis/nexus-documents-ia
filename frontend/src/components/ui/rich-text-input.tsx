"use client"

import { useState, useRef, useEffect, forwardRef } from "react"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { IconUser, IconBuilding, IconRobot, IconX } from "@tabler/icons-react"
import { parseEntityTags, findEntityAtPosition } from "./entity-renderer"
import { EntitySearchMenu } from "@/components/documents/entity-search-menu"
import { createEntityTag } from "./entity-renderer"

interface Entity {
  id: string
  name: string
  email: string
  type: 'contact' | 'organization' | 'user' | 'agent'
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
    onKeyDown,
    ...props 
  }, ref) => {
    const [isEditing, setIsEditing] = useState(false)
    const [inputValue, setInputValue] = useState("")
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    
    const inputRef = useRef<HTMLInputElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    // Parse the value to show entities as badges
    const parts = parseEntityTags(value)

    const handleContainerClick = () => {
      if (!disabled) {
        setIsEditing(true)
        setInputValue(value)
        setTimeout(() => {
          inputRef.current?.focus()
        }, 0)
      }
    }


    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value
      const cursorPosition = e.target.selectionStart || 0
      
      onChange(newValue)
      
      // Check for mention trigger
      const triggerIndex = newValue.lastIndexOf(mentionTrigger, cursorPosition - 1)
      
      // Only process if @ is found and cursor is after it
      if (triggerIndex !== -1 && cursorPosition > triggerIndex) {
        // Check if this is a valid mention (not inside a word)
        const beforeTrigger = triggerIndex === 0 ? '' : newValue[triggerIndex - 1]
        const isValidMention = triggerIndex === 0 || /\s/.test(beforeTrigger)
        
        if (isValidMention) {
          const query = newValue.substring(triggerIndex + 1, cursorPosition)
          
          // Only open if query doesn't contain spaces and has at least 1 character
          if (!query.includes(' ') && !query.includes('\n') && query.length > 0) {
            setEntitySearchQuery(query)
            setMentionStart(triggerIndex)
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
      }
    }

    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (entitySearchOpen && e.key === 'Escape') {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
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
      
      // Create entity tag
      const entityTag = createEntityTag({
        type: entity.type,
        id: entity.id,
        name: entity.name
      })
      
      const newValue = beforeMention + entityTag + afterMention
      
      onChange(newValue)
      setEntitySearchOpen(false)
      setEntitySearchQuery('')
      setMentionStart(-1)
      
      if (onEntitySelect) {
        onEntitySelect(entity)
      }
    }

    const removeEntity = (partIndex: number) => {
      const part = parts[partIndex]
      if (part && part.type === 'entity') {
        const newValue = value.substring(0, part.start) + value.substring(part.end)
        onChange(newValue)
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
            }}
            searchQuery={entitySearchQuery}
            anchorRef={inputRef.current}
            documentId={documentId}
          />
        )}
        
        {/* Preview with badges */}
        {value.includes('<@') && (
          <div className="flex items-center flex-wrap gap-1 p-2 bg-muted/30 border rounded-md">
            <span className="text-xs text-muted-foreground mr-2">Preview:</span>
            {parts.map((part, index) => {
              if (part.type === 'text' && part.content) {
                return (
                  <span key={index} className="whitespace-pre-wrap">
                    {part.content}
                  </span>
                )
              }

              if (part.type === 'entity' && part.entity) {
                const { type, name } = part.entity
                const Icon = type === 'organization' ? IconBuilding : 
                            type === 'agent' ? IconRobot : IconUser

                return (
                  <Badge 
                    key={index} 
                    variant="secondary" 
                    className="inline-flex items-center gap-1 bg-primary/10 text-primary hover:bg-primary/20 border-primary/20"
                  >
                    <Icon className="h-3 w-3" />
                    <span>{name}</span>
                  </Badge>
                )
              }

              return null
            })}
          </div>
        )}
      </div>
    )
  }
)

RichTextInput.displayName = "RichTextInput"