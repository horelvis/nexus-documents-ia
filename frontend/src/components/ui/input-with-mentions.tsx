"use client"

import { useState, useRef, forwardRef } from "react"
import { Input, InputProps } from "@/components/ui/input"
import { Textarea, TextareaProps } from "@/components/ui/textarea"
import { EntitySearchMenu } from "@/components/documents/entity-search-menu"
import { createEntityTag, findEntityAtPosition } from "@/components/ui/entity-renderer"

interface Entity {
  id: string
  name: string
  email: string
  type: 'contact' | 'organization' | 'user' | 'agent'
  role?: string
}

interface InputWithMentionsProps extends Omit<InputProps, 'onChange' | 'value'> {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string // Default: '@'
}

interface TextareaWithMentionsProps extends Omit<TextareaProps, 'onChange' | 'value'> {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string // Default: '@'
  variant?: 'input' | 'textarea'
}

const InputWithMentions = forwardRef<HTMLInputElement, InputWithMentionsProps>(
  ({ value, onChange, documentId, placeholder, onEntitySelect, mentionTrigger = '@', ...props }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const inputRef = useRef<HTMLInputElement>(null)
    
    // Use forwarded ref or internal ref
    const actualRef = ref || inputRef

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value
      const cursorPosition = e.target.selectionStart || 0
      
      onChange(newValue)
      
      // Check for mention trigger only if cursor is after a @
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
      
      // Close search if no valid mention found or cursor moved away from @
      if (entitySearchOpen) {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
      }
    }

    const handleEntitySelect = (entity: Entity) => {
      if (mentionStart === -1) return
      
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
      
      // Focus back to input
      if (actualRef && 'current' in actualRef && actualRef.current) {
        actualRef.current.focus()
      }
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (entitySearchOpen && e.key === 'Escape') {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        e.preventDefault()
        
        // Return focus to input after closing dropdown
        setTimeout(() => {
          if (actualRef && 'current' in actualRef && actualRef.current) {
            actualRef.current.focus()
          }
        }, 0)
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
            if (actualRef && 'current' in actualRef && actualRef.current) {
              actualRef.current.setSelectionRange(entityAtPosition.start, entityAtPosition.start)
            }
          }, 0)
          
          return
        }
      }
      
      // Call original onKeyDown if provided
      if (props.onKeyDown) {
        props.onKeyDown(e)
      }
    }

    return (
      <div className="relative">
        <Input
          ref={actualRef}
          value={value}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || `Type ${mentionTrigger} to mention entities`}
          {...props}
        />
        
        {/* Entity Search Menu */}
        {entitySearchOpen && documentId && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelect}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              
              // Return focus to input when closed from dropdown
              setTimeout(() => {
                if (actualRef && 'current' in actualRef && actualRef.current) {
                  actualRef.current.focus()
                }
              }, 0)
            }}
            searchQuery={entitySearchQuery}
            anchorRef={actualRef && 'current' in actualRef ? actualRef.current : null}
            documentId={documentId}
          />
        )}
      </div>
    )
  }
)

InputWithMentions.displayName = "InputWithMentions"

const TextareaWithMentions = forwardRef<HTMLTextAreaElement, TextareaWithMentionsProps>(
  ({ value, onChange, documentId, placeholder, onEntitySelect, mentionTrigger = '@', ...props }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    
    // Use forwarded ref or internal ref
    const actualRef = ref || textareaRef

    const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value
      const cursorPosition = e.target.selectionStart || 0
      
      onChange(newValue)
      
      // Check for mention trigger only if cursor is after a @
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

    const handleEntitySelect = (entity: Entity) => {
      if (mentionStart === -1) return
      
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
      
      // Focus back to textarea
      if (actualRef && 'current' in actualRef && actualRef.current) {
        actualRef.current.focus()
      }
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (entitySearchOpen && e.key === 'Escape') {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        e.preventDefault()
        
        // Return focus to textarea after closing dropdown
        setTimeout(() => {
          if (actualRef && 'current' in actualRef && actualRef.current) {
            actualRef.current.focus()
          }
        }, 0)
      }
      
      // Handle backspace to delete entire entity
      if (e.key === 'Backspace' && !entitySearchOpen) {
        const cursorPosition = e.currentTarget.selectionStart || 0
        
        // Find if cursor is at the end of an entity mention
        const beforeCursor = value.substring(0, cursorPosition)
        const entityMatch = beforeCursor.match(new RegExp(`${mentionTrigger}[^\\s${mentionTrigger}\\n]+$`))
        
        if (entityMatch) {
          e.preventDefault()
          
          // Remove the entire entity
          const entityStart = cursorPosition - entityMatch[0].length
          const newValue = value.substring(0, entityStart) + value.substring(cursorPosition)
          onChange(newValue)
          
          // Set cursor position after the removal
          setTimeout(() => {
            if (actualRef && 'current' in actualRef && actualRef.current) {
              actualRef.current.setSelectionRange(entityStart, entityStart)
            }
          }, 0)
          
          return
        }
      }
      
      // Call original onKeyDown if provided
      if (props.onKeyDown) {
        props.onKeyDown(e)
      }
    }

    return (
      <div className="relative">
        <Textarea
          ref={actualRef}
          value={value}
          onChange={handleTextareaChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || `Type ${mentionTrigger} to mention entities`}
          {...props}
        />
        
        {/* Entity Search Menu */}
        {entitySearchOpen && documentId && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelect}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              
              // Return focus to input when closed from dropdown
              setTimeout(() => {
                if (actualRef && 'current' in actualRef && actualRef.current) {
                  actualRef.current.focus()
                }
              }, 0)
            }}
            searchQuery={entitySearchQuery}
            anchorRef={actualRef && 'current' in actualRef ? actualRef.current : null}
            documentId={documentId}
          />
        )}
      </div>
    )
  }
)

TextareaWithMentions.displayName = "TextareaWithMentions"

export { InputWithMentions, TextareaWithMentions }
export type { Entity, InputWithMentionsProps, TextareaWithMentionsProps }