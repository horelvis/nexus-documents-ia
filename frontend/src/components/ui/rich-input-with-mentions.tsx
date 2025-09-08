"use client"

import { useState, useRef, forwardRef, useEffect } from "react"
import { cn } from "@/lib/utils"
import { EntitySearchMenu } from "@/components/documents/entity-search-menu"
import { createEntityTag, findEntityAtPosition, parseEntityTags } from "@/components/ui/entity-renderer"
import { Badge } from "@/components/ui/badge"
import { IconUser, IconBuilding, IconRobot } from "@tabler/icons-react"

interface Entity {
  id: string
  name: string
  email: string
  type: 'contact' | 'organization' | 'user' | 'agent'
  role?: string
}

interface RichInputWithMentionsProps {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string
  className?: string
  disabled?: boolean
}

export const RichInputWithMentions = forwardRef<HTMLDivElement, RichInputWithMentionsProps>(
  ({ value, onChange, documentId, placeholder, onEntitySelect, mentionTrigger = '@', className, disabled = false, ...props }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const [isEditing, setIsEditing] = useState(false)
    const [cursorPosition, setCursorPosition] = useState(0)
    
    const editableRef = useRef<HTMLDivElement>(null)
    const hiddenInputRef = useRef<HTMLInputElement>(null)
    
    // Parse entities for rendering
    const parts = parseEntityTags(value)

    // Handle input changes
    const handleInput = (e: React.FormEvent<HTMLDivElement>) => {
      const target = e.currentTarget
      const newValue = target.innerText || ''
      const selection = window.getSelection()
      const cursorPos = selection?.anchorOffset || 0
      
      setCursorPosition(cursorPos)
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

    const handleEntitySelect = (entity: Entity) => {
      if (mentionStart === -1 || !editableRef.current) return
      
      const beforeMention = value.substring(0, mentionStart)
      const afterMention = value.substring(mentionStart + entitySearchQuery.length + 1)
      
      // Create entity tag instead of plain text
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
      
      // Call custom entity select handler if provided
      if (onEntitySelect) {
        onEntitySelect(entity)
      }
      
      // Focus back to editable div
      setTimeout(() => {
        if (editableRef.current) {
          editableRef.current.focus()
        }
      }, 0)
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (entitySearchOpen && e.key === 'Escape') {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        e.preventDefault()
        
        setTimeout(() => {
          if (editableRef.current) {
            editableRef.current.focus()
          }
        }, 0)
      }
      
      // Handle backspace to delete entire entity tag
      if (e.key === 'Backspace' && !entitySearchOpen) {
        const selection = window.getSelection()
        const cursorPos = selection?.anchorOffset || 0
        
        // Check if cursor is at the end of an entity tag
        const entityAtPosition = findEntityAtPosition(value, cursorPos)
        
        if (entityAtPosition && cursorPos === entityAtPosition.end) {
          e.preventDefault()
          
          // Remove the entire entity tag
          const newValue = value.substring(0, entityAtPosition.start) + value.substring(entityAtPosition.end)
          onChange(newValue)
          
          return
        }
      }
    }

    const handleFocus = () => {
      setIsEditing(true)
    }

    const handleBlur = () => {
      setIsEditing(false)
    }

    return (
      <div className="relative">
        {/* Visual representation when not editing */}
        {!isEditing && (
          <div 
            className={cn(
              "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
              "cursor-text min-h-[36px] items-center flex-wrap gap-1",
              disabled && "cursor-not-allowed opacity-50",
              className
            )}
            onClick={() => {
              if (!disabled && editableRef.current) {
                editableRef.current.focus()
              }
            }}
          >
            {parts.length === 0 ? (
              <span className="text-muted-foreground">{placeholder}</span>
            ) : (
              parts.map((part, index) => {
                if (part.type === 'text') {
                  return <span key={index}>{part.content}</span>
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
                      {name}
                    </Badge>
                  )
                }

                return null
              })
            )}
          </div>
        )}

        {/* Editable input when focused */}
        {isEditing && (
          <input
            ref={hiddenInputRef}
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={handleFocus}
            onBlur={handleBlur}
            placeholder={placeholder}
            disabled={disabled}
            className={cn(
              "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
              className
            )}
          />
        )}

        {/* Hidden div for editing (simplified version) */}
        <div
          ref={editableRef}
          contentEditable={!disabled}
          suppressContentEditableWarning={true}
          onInput={handleInput}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          onBlur={handleBlur}
          className="sr-only"
          style={{ position: 'absolute', left: '-9999px' }}
        >
          {value}
        </div>

        {/* Entity Search Menu */}
        {entitySearchOpen && documentId && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelect}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              
              setTimeout(() => {
                if (editableRef.current) {
                  editableRef.current.focus()
                }
              }, 0)
            }}
            searchQuery={entitySearchQuery}
            anchorRef={editableRef.current}
            documentId={documentId}
          />
        )}
      </div>
    )
  }
)

RichInputWithMentions.displayName = "RichInputWithMentions"