"use client"

import { useState, useRef, forwardRef, ComponentType } from "react"
import { Input, InputProps } from "./input"
import { Textarea, TextareaProps } from "./textarea"
import { createEntityTag, findEntityAtPosition } from "./entity-renderer"

export interface Entity {
  id: string
  name: string
  email: string
  type: string
  role?: string
}

// Props for EntitySearchMenu component (to be provided by the app)
export interface EntitySearchMenuProps {
  open: boolean
  onSelect: (entity: Entity) => void
  onClose: () => void
  searchQuery: string
  anchorRef: HTMLInputElement | HTMLTextAreaElement | null
  documentId: string
  cursorPosition?: { top: number; left: number } | null
}

// Default fallback for getCharacterCoordinates when not provided
const defaultGetCharacterCoordinates = (_element: HTMLElement, _position: number): { top: number; left: number } => {
  return { top: 0, left: 0 }
}

export interface InputWithMentionsProps extends Omit<InputProps, 'onChange' | 'value'> {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string // Default: '@'
  autoInsertEntityTag?: boolean
  /** Optional EntitySearchMenu component - pass from app if entity search is needed */
  EntitySearchMenu?: ComponentType<EntitySearchMenuProps>
  /** Optional function to calculate cursor position for dropdown placement */
  getCharacterCoordinates?: (element: HTMLElement, position: number) => { top: number; left: number }
}

export interface TextareaWithMentionsProps extends Omit<TextareaProps, 'onChange' | 'value'> {
  value: string
  onChange: (value: string) => void
  documentId?: string
  placeholder?: string
  onEntitySelect?: (entity: Entity) => void
  mentionTrigger?: string // Default: '@'
  variant?: 'input' | 'textarea'
  autoInsertEntityTag?: boolean
  /** Optional EntitySearchMenu component - pass from app if entity search is needed */
  EntitySearchMenu?: ComponentType<EntitySearchMenuProps>
  /** Optional function to calculate cursor position for dropdown placement */
  getCharacterCoordinates?: (element: HTMLElement, position: number) => { top: number; left: number }
}

const InputWithMentions = forwardRef<HTMLInputElement, InputWithMentionsProps>(
  ({ value, onChange, documentId, placeholder, onEntitySelect, mentionTrigger = '@', autoInsertEntityTag = true, EntitySearchMenu, getCharacterCoordinates = defaultGetCharacterCoordinates, ...props }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const [cursorPosition, setCursorPosition] = useState<{ top: number; left: number } | null>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    // Use forwarded ref or internal ref
    const actualRef = ref || inputRef

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const newValue = e.target.value
      const cursorPos = e.target.selectionStart || 0

      onChange(newValue)

      // Check for mention trigger only if cursor is after a @
      const triggerIndex = newValue.lastIndexOf(mentionTrigger, cursorPos - 1)

      // Only process if @ is found and cursor is after it
      if (triggerIndex !== -1 && cursorPos > triggerIndex) {
        // Check if this is a valid mention (not inside a word)
        const beforeTrigger = triggerIndex === 0 ? '' : newValue[triggerIndex - 1]
        const isValidMention = triggerIndex === 0 || /\s/.test(beforeTrigger)

        if (isValidMention) {
          const query = newValue.substring(triggerIndex + 1, cursorPos)

          // Open dropdown immediately when @ is typed (allow empty query)
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

      // Close search if no valid mention found or cursor moved away from @
      if (entitySearchOpen) {
        setEntitySearchOpen(false)
        setEntitySearchQuery('')
        setMentionStart(-1)
        setCursorPosition(null)
      }
    }

    const handleEntitySelect = (entity: Entity) => {
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
        setCursorPosition(null)
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
        
        {/* Entity Search Menu - only rendered if component is provided */}
        {entitySearchOpen && documentId && EntitySearchMenu && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelect}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              setCursorPosition(null)

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
            cursorPosition={cursorPosition}
          />
        )}
      </div>
    )
  }
)

InputWithMentions.displayName = "InputWithMentions"

const TextareaWithMentions = forwardRef<HTMLTextAreaElement, TextareaWithMentionsProps>(
  ({ value, onChange, documentId, placeholder, onEntitySelect, mentionTrigger = '@', autoInsertEntityTag = true, EntitySearchMenu, getCharacterCoordinates = defaultGetCharacterCoordinates, ...props }, ref) => {
    const [entitySearchOpen, setEntitySearchOpen] = useState(false)
    const [entitySearchQuery, setEntitySearchQuery] = useState('')
    const [mentionStart, setMentionStart] = useState(-1)
    const [cursorPosition, setCursorPosition] = useState<{ top: number; left: number } | null>(null)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // Use forwarded ref or internal ref
    const actualRef = ref || textareaRef

    const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value
      const cursorPos = e.target.selectionStart || 0

      onChange(newValue)

      // Check for mention trigger only if cursor is after a @
      const triggerIndex = newValue.lastIndexOf(mentionTrigger, cursorPos - 1)

      // Only process if @ is found and cursor is after it
      if (triggerIndex !== -1 && cursorPos > triggerIndex) {
        // Check if this is a valid mention (not inside a word)
        const beforeTrigger = triggerIndex === 0 ? '' : newValue[triggerIndex - 1]
        const isValidMention = triggerIndex === 0 || /\s/.test(beforeTrigger)

        if (isValidMention) {
          const query = newValue.substring(triggerIndex + 1, cursorPos)

          // Open dropdown immediately when @ is typed (allow empty query)
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

    const handleEntitySelect = (entity: Entity) => {
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
        setCursorPosition(null)
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
        
        {/* Entity Search Menu - only rendered if component is provided */}
        {entitySearchOpen && documentId && EntitySearchMenu && (
          <EntitySearchMenu
            open={entitySearchOpen}
            onSelect={handleEntitySelect}
            onClose={() => {
              setEntitySearchOpen(false)
              setEntitySearchQuery('')
              setMentionStart(-1)
              setCursorPosition(null)

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
            cursorPosition={cursorPosition}
          />
        )}
      </div>
    )
  }
)

TextareaWithMentions.displayName = "TextareaWithMentions"

export { InputWithMentions, TextareaWithMentions }
export type { Entity, InputWithMentionsProps, TextareaWithMentionsProps }
