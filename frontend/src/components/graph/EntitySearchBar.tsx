'use client'

import { useState, useEffect, useRef } from 'react'
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from '@/components/ui/command'
import { Badge } from '@/components/ui/badge'
import { entitySearchService, type EntityMatch } from '@/lib/services/entity-search.service'
import { ENTITY_TYPE_COLORS } from '@/app/knowledge-graph/components/explainability-theme'

interface EntitySearchBarProps {
  tenantId: string
  onSelect: (entity: EntityMatch) => void
  placeholder?: string
  className?: string
}

export function EntitySearchBar({
  tenantId,
  onSelect,
  placeholder = 'Buscar entidades...',
  className = '',
}: EntitySearchBarProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EntityMatch[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)

    if (query.length < 2) {
      setResults([])
      return
    }

    timerRef.current = setTimeout(async () => {
      setIsLoading(true)
      try {
        const entities = await entitySearchService.search(tenantId, query, 10)
        setResults(entities)
        setIsOpen(true)
      } catch {
        setResults([])
      } finally {
        setIsLoading(false)
      }
    }, 300)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [query, tenantId])

  function handleSelect(entity: EntityMatch) {
    setIsOpen(false)
    setQuery('')
    setResults([])
    onSelect(entity)
  }

  return (
    <div className={`relative ${className}`}>
      <Command shouldFilter={false} className="rounded-lg border border-white/10 bg-slate-900/90 backdrop-blur">
        <CommandInput
          placeholder={placeholder}
          value={query}
          onValueChange={setQuery}
          onFocus={() => results.length > 0 && setIsOpen(true)}
          className="text-sm"
        />
        {isOpen && (
          <CommandList className="max-h-60">
            {isLoading && <CommandEmpty>Buscando...</CommandEmpty>}
            {!isLoading && results.length === 0 && query.length >= 2 && (
              <CommandEmpty>No se encontraron entidades</CommandEmpty>
            )}
            {results.length > 0 && (
              <CommandGroup heading="Entidades">
                {results.map((entity) => (
                  <CommandItem
                    key={entity.entity_uri}
                    value={entity.entity_uri}
                    onSelect={() => handleSelect(entity)}
                    className="flex items-center gap-2"
                  >
                    <span
                      className="h-2 w-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: ENTITY_TYPE_COLORS[entity.entity_type] ?? '#6b7280' }}
                    />
                    <span className="flex-1 truncate">{entity.label}</span>
                    <Badge variant="outline" className="text-[10px] px-1.5">
                      {entity.entity_type}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {Math.round(entity.score * 100)}%
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        )}
      </Command>
    </div>
  )
}
