"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
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
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Search entities when query changes
  useEffect(() => {
    if (!open || !searchQuery) {
      setEntities([])
      setLoading(false)
      return
    }

    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    // Only set loading true if we're actually going to search
    if (searchQuery.length > 0) {
      setLoading(true)
      
      // Debounce the search
      searchTimeoutRef.current = setTimeout(async () => {
        try {
          const timestamp = Date.now()
          console.log(`[${timestamp}] Starting entity search - Query: '${searchQuery}', DocumentId: ${documentId}`)
          
          // Search for entities
          const response = await entityService.searchEntities({
            query: searchQuery,
            documentId: documentId,
            limit: 10
          })
          
          console.log(`[${timestamp}] Entity search response:`, response)
          
          if (response.data?.entities && response.data.entities.length > 0) {
            // Type cast the entities to ensure type safety
            const typedEntities = response.data.entities.map(entity => ({
              ...entity,
              type: entity.type as Entity['type']
            }))
            setEntities(typedEntities)
            console.log(`[${timestamp}] Found ${typedEntities.length} entities`)
          } else {
            // No results found
            console.log(`[${timestamp}] No entities found for query '${searchQuery}'`)
            setEntities([])
          }
        } catch (error) {
          console.error(`Failed to search entities for query '${searchQuery}':`, error)
          setEntities([])
        } finally {
          setLoading(false)
        }
      }, 300)
    }
    
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [searchQuery, open, documentId]) // Remove entityService from dependencies

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

  if (!anchorRef || !open) return null

  // Calculate positioning for the dropdown
  const rect = anchorRef.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  
  // Calculate available space above and below
  const spaceBelow = viewportHeight - rect.bottom
  const spaceAbove = rect.top
  
  // Estimate dropdown height (max 6 items * ~48px per item + padding)
  const estimatedDropdownHeight = Math.min(entities.length, 6) * 48 + 60
  
  // Decide if dropdown should open upward or downward
  const shouldOpenUpward = spaceBelow < estimatedDropdownHeight && spaceAbove > spaceBelow

  return (
    <div
      className="fixed z-50"
      style={{
        top: shouldOpenUpward 
          ? rect.top + window.scrollY - estimatedDropdownHeight - 4
          : rect.bottom + window.scrollY + 4,
        left: rect.left + window.scrollX,
        width: rect.width,
        maxHeight: shouldOpenUpward 
          ? Math.min(spaceAbove - 8, 300)
          : Math.min(spaceBelow - 8, 300)
      }}
    >
      {open && (
        <Command className="rounded-lg border shadow-md bg-popover">
          <CommandList className="max-h-full overflow-y-auto">
            {loading ? (
              <CommandEmpty>
                <div className="flex items-center justify-center gap-2">
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  <span>Searching...</span>
                </div>
              </CommandEmpty>
            ) : entities.length === 0 ? (
              <CommandEmpty>No entities found for "{searchQuery}"</CommandEmpty>
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