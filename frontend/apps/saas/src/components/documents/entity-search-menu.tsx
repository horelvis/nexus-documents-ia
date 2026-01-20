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
  type: string  // backend may return dynamic entity types
  role?: string
}

interface EntitySearchMenuProps {
  open: boolean
  onSelect: (entity: Entity) => void
  onClose: () => void
  searchQuery: string
  anchorRef: HTMLElement | null
  documentId: string
  cursorPosition?: { top: number; left: number } | null
}

export function EntitySearchMenu({
  open,
  onSelect,
  onClose,
  searchQuery,
  anchorRef,
  documentId,
  cursorPosition
}: EntitySearchMenuProps) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [recentEntities, setRecentEntities] = useState<Entity[]>([])
  const [loadingRecent, setLoadingRecent] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)
  const entityService = useEntityService()
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Load recent entities when opened with empty query
  useEffect(() => {
    if (!open) {
      setRecentEntities([])
      return
    }

    // Only load recents if query is empty
    if (searchQuery === '') {
      setLoadingRecent(true)

      const loadRecentEntities = async () => {
        try {
          const response = await entityService.getRecentEntities(10)
          if (response.data?.entities) {
            setRecentEntities(response.data.entities)
          } else {
            setRecentEntities([])
          }
        } catch (error) {
          console.error('Failed to load recent entities:', error)
          setRecentEntities([])
        } finally {
          setLoadingRecent(false)
        }
      }

      loadRecentEntities()
    }
  }, [open, searchQuery === ''])

  // Search entities when query changes
  useEffect(() => {
    if (!open) {
      setEntities([])
      setLoading(false)
      return
    }

    // If query is empty, we use recent entities instead
    if (!searchQuery) {
      setEntities([])
      setLoading(false)
      return
    }

    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }

    setLoading(true)

    // Debounce the search
    searchTimeoutRef.current = setTimeout(async () => {
      try {
        const response = await entityService.searchEntities({
          query: searchQuery,
          documentId: documentId,
          limit: 10
        })

        if (response.data?.entities && response.data.entities.length > 0) {
          const typedEntities = response.data.entities.map(entity => ({
            ...entity
          }))
          setEntities(typedEntities)
        } else {
          setEntities([])
        }
      } catch (error) {
        console.error(`Failed to search entities for query '${searchQuery}':`, error)
        setEntities([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [searchQuery, open, documentId])

  // Determine which entities to display
  const displayEntities = searchQuery ? entities : recentEntities
  const isLoadingDisplay = searchQuery ? loading : loadingRecent

  // Reset selected index when display entities change
  useEffect(() => {
    setSelectedIndex(0)
  }, [entities, recentEntities])

  // Handle keyboard navigation
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (displayEntities.length === 0) return

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex(prev => (prev + 1) % displayEntities.length)
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex(prev => (prev - 1 + displayEntities.length) % displayEntities.length)
          break
        case 'Tab':
        case 'Enter':
          e.preventDefault()
          if (displayEntities[selectedIndex]) {
            onSelect(displayEntities[selectedIndex])
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
  }, [open, displayEntities, selectedIndex, onSelect, onClose])

  if (!anchorRef || !open) return null

  // Calculate positioning for the dropdown
  const rect = anchorRef.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth

  // Determine position based on cursorPosition or fallback to anchor
  let dropdownTop: number
  let dropdownLeft: number
  let dropdownWidth: number

  if (cursorPosition) {
    // Position near the cursor/@ character
    dropdownTop = cursorPosition.top
    dropdownLeft = cursorPosition.left
    dropdownWidth = 280 // Fixed width for mention dropdown
  } else {
    // Fallback: position below the full input
    dropdownTop = rect.bottom + window.scrollY
    dropdownLeft = rect.left + window.scrollX
    dropdownWidth = Math.min(rect.width, 350)
  }

  // Calculate available space
  const spaceBelow = viewportHeight - dropdownTop
  const spaceAbove = dropdownTop

  // Estimate dropdown height (max 6 items * ~48px per item + padding)
  const estimatedDropdownHeight = Math.min(displayEntities.length || 3, 6) * 48 + 60

  // Decide if dropdown should open upward or downward
  const shouldOpenUpward = spaceBelow < estimatedDropdownHeight && spaceAbove > spaceBelow

  // Adjust left position if dropdown would overflow viewport
  const adjustedLeft = Math.min(Math.max(8, dropdownLeft), viewportWidth - dropdownWidth - 8)

  return (
    <div
      className="fixed z-50"
      style={{
        top: shouldOpenUpward
          ? dropdownTop - estimatedDropdownHeight - 4
          : dropdownTop + 4,
        left: adjustedLeft,
        width: dropdownWidth,
        maxHeight: shouldOpenUpward
          ? Math.min(spaceAbove - 8, 300)
          : Math.min(spaceBelow - 8, 300)
      }}
    >
      {open && (
        <Command className="rounded-lg border shadow-md bg-popover">
          <CommandList className="max-h-full overflow-y-auto">
            {isLoadingDisplay ? (
              <CommandEmpty>
                <div className="flex items-center justify-center gap-2">
                  <IconLoader2 className="h-4 w-4 animate-spin" />
                  <span>{searchQuery ? 'Searching...' : 'Loading recent...'}</span>
                </div>
              </CommandEmpty>
            ) : displayEntities.length === 0 ? (
              <CommandEmpty>
                {searchQuery
                  ? `No entities found for "${searchQuery}"`
                  : 'No recent entities'
                }
              </CommandEmpty>
            ) : (
              <CommandGroup heading={searchQuery ? 'Suggested Entities' : 'Recent Entities'}>
                {displayEntities.map((entity, index) => {
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
