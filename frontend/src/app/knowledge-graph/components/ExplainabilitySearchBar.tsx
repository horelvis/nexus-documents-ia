'use client'

import { useState, useCallback } from 'react'
import { IconSearch } from '@tabler/icons-react'
import { Input } from '@/components/ui/input'
import type { ExplainNode } from './explainability-theme'

interface ExplainabilitySearchBarProps {
  nodes: ExplainNode[]
  onFilter: (nodeIds: Set<string> | null) => void
  onFocus: (nodeId: string) => void
}

export function ExplainabilitySearchBar({
  nodes,
  onFilter,
  onFocus,
}: ExplainabilitySearchBarProps) {
  const [query, setQuery] = useState('')

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value
      setQuery(value)

      if (!value.trim()) {
        onFilter(null)
        return
      }

      const lower = value.toLowerCase()
      const matched = nodes.filter((n) =>
        n.label.toLowerCase().includes(lower),
      )

      const matchedIds = new Set(matched.map((n) => n.id))
      onFilter(matchedIds)

      if (matched.length === 1) {
        onFocus(matched[0].id)
      }
    },
    [nodes, onFilter, onFocus],
  )

  return (
    <div className="absolute top-4 left-4 z-10 w-56">
      <div className="relative">
        <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <Input
          type="text"
          value={query}
          onChange={handleChange}
          placeholder="Search nodes..."
          className="pl-8 h-8 text-xs bg-background/80 backdrop-blur-sm shadow-md"
        />
      </div>
    </div>
  )
}
