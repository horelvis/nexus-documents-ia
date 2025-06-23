"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent } from "@/components/ui/popover"
import { IconUser, IconBuilding, IconMail, IconRobot, IconLoader2 } from "@tabler/icons-react"
import { cn } from "@/lib/utils"
import { useEntityService } from "@/lib/services/entity.service"

interface Entity {
  id: string
  name: string
  email: string
  type: 'contact' | 'organization' | 'user' | 'agent'  // TODO: Only 'user' and 'agent' are currently implemented in backend
  role?: string
}

interface EntitySearchMenuProps {
  open: boolean
  onSelect: (entity: Entity) => void
  onClose: () => void
  searchQuery: string
  anchorRef: HTMLElement | null
  documentId: string
}

export function EntitySearchMenu({
  open,
  onSelect,
  onClose,
  searchQuery,
  anchorRef,
  documentId
}: EntitySearchMenuProps) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const popoverRef = useRef<HTMLDivElement>(null)
  const entityService = useEntityService()

  // Search entities when query changes
  useEffect(() => {
    if (!open || !searchQuery) return

    let cancelled = false
    setLoading(true)
    
    const searchEntities = async () => {
      try {
        // First try to get document-specific entities
        const response = await entityService.searchEntities({
          query: searchQuery,
          documentId: documentId,
          limit: 10
        })
        
        if (!cancelled) {
          if (response.data?.entities) {
            // Type cast the entities to ensure type safety
            const typedEntities = response.data.entities.map(entity => ({
              ...entity,
              type: entity.type as Entity['type']
            }))
            setEntities(typedEntities)
          } else {
            // Fallback to mock data if API is not available
            const mockEntities: Entity[] = [
              {
                id: '1',
                name: 'John Doe',
                email: 'john.doe@example.com',
                type: 'user',
                role: 'Manager'
              },
              {
                id: '2',
                name: 'Jane Smith',
                email: 'jane.smith@example.com',
                type: 'user',
                role: 'Director'
              },
              {
                id: '3',
                name: 'AI Assistant',
                email: 'ai.assistant@agent.ai',
                type: 'agent',
                role: 'Document Analyzer'
              }
            ].filter(e => 
              e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
              e.email.toLowerCase().includes(searchQuery.toLowerCase())
            )
            setEntities(mockEntities)
          }
          setLoading(false)
        }
      } catch (error) {
        console.error('Failed to search entities:', error)
        if (!cancelled) {
          setEntities([])
          setLoading(false)
        }
      }
    }
    
    // Debounce the search
    const timer = setTimeout(searchEntities, 300)
    
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [searchQuery, open, documentId, entityService])

  // Reset selected index when entities change
  useEffect(() => {
    setSelectedIndex(0)
  }, [entities])

  // Handle keyboard navigation
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(prev => (prev + 1) % entities.length)
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(prev => (prev - 1 + entities.length) % entities.length)
          break
        case 'Enter':
          e.preventDefault()
          if (entities[selectedIndex]) {
            onSelect(entities[selectedIndex])
            onClose()
          }
          break
        case 'Escape':
          e.preventDefault()
          onClose()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, entities, selectedIndex, onSelect, onClose])

  if (!anchorRef) return null

  const rect = anchorRef.getBoundingClientRect()

  return (
    <div
      className="fixed z-50"
      style={{
        top: rect.bottom + window.scrollY + 4,
        left: rect.left + window.scrollX,
        width: rect.width
      }}
    >
      {open && (
        <Command className="rounded-lg border shadow-md bg-popover">
          <CommandList>
            {loading ? (
              <CommandEmpty>
                <div className="flex items-center justify-center gap-2">
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  <span>Searching...</span>
                </div>
              </CommandEmpty>
            ) : entities.length === 0 ? (
              <CommandEmpty>No entities found</CommandEmpty>
            ) : (
              <CommandGroup heading="Suggested Entities">
                {entities.map((entity, index) => {
                  const Icon = entity.type === 'organization' ? IconBuilding : 
                              entity.type === 'agent' ? IconRobot : IconUser
                  
                  return (
                    <CommandItem
                      key={entity.id}
                      onSelect={() => {
                        onSelect(entity)
                        onClose()
                      }}
                      className={cn(
                        "cursor-pointer",
                        index === selectedIndex && "bg-accent"
                      )}
                    >
                      <Icon className="mr-2 h-4 w-4" />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{entity.name}</span>
                          {entity.role && (
                            <span className="text-xs text-muted-foreground">
                              {entity.role}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 text-xs text-muted-foreground">
                          <IconMail className="h-3 w-3" />
                          {entity.email}
                        </div>
                      </div>
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      )}
    </div>
  )
}